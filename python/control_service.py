"""Authenticated UI request queue; media browsing and safe-copy jobs only."""
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlparse, parse_qs

from autonomous_queue import EXTENSIONS, read, write, signature
from workspace_history import WorkspaceHistory, decision_evidence
from app_version import VERSION
from codec_selection import EVALUATION_POLICY


def handler(base, controls):
    class Handler(base):
        def reply(self, data, status=200):
            body=json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers();self.wfile.write(body)

        def do_GET(self):
            url=urlparse(self.path)
            if url.path not in ('/api/controls','/api/media','/api/request-log'):return super().do_GET()
            if not self.permitted():return
            try:
                params=parse_qs(url.query)
                if url.path=='/api/request-log':
                    from dashboard import tail
                    identifier=params.get('id',[''])[0]
                    with controls.mutex:
                        job=next((j for j in controls.state['jobs'] if j['id']==identifier),None)
                    if not job or 'output' not in job:raise ValueError('Unknown job')
                    log=Path(job['output'])/'worker.log'
                    if not log.resolve().is_relative_to(controls.root):raise ValueError('Invalid log path')
                    self.reply(dict(text=tail(log)));return
                self.reply(controls.snapshot() if url.path=='/api/controls' else
                           controls.browse(params.get('path',[''])[0],params.get('offset',['0'])[0],
                                           videos=params.get('videos',['false'])[0]=='true',
                                           recursive=params.get('recursive',['true'])[0]=='true'))
            except (ValueError,OSError,TypeError):self.reply(dict(error='Cannot browse this path inside the media mount'),400)

        def do_POST(self):
            if self.path!='/api/control':return super().do_POST()
            if not self.permitted():return
            host=self.headers.get('Host','')
            if self.headers.get('Origin')!='http://'+host or not hmac.compare_digest(self.headers.get('X-MuxMender-CSRF',''),controls.token):
                self.reply(dict(error='Same-origin request and valid control token required'),403);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8192 or self.headers.get('Content-Type')!='application/json':raise ValueError('Invalid request body')
                self.connection.settimeout(10)
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('Expected JSON object')
                self.reply(controls.action(data))
            except (ValueError,OSError,TypeError) as exc:self.reply(dict(error=str(exc)),400)
    return Handler


class Controls(WorkspaceHistory):
    def __init__(self, media, output, readonly, codecs, busy=lambda: False, replacement_root=None):
        self.media, self.output = media.resolve(strict=True), output.resolve(strict=True)
        if self.media == self.output or self.media in self.output.parents or self.output in self.media.parents:
            raise ValueError('Separate media and output mounts required')
        self.readonly, self.codecs, self.busy = readonly, codecs, busy
        self.replacement_root=Path(replacement_root).resolve(strict=True) if replacement_root else None
        if self.replacement_root and (self.replacement_root==self.output or self.output in self.replacement_root.parents or self.replacement_root in self.output.parents):
            raise ValueError('Replacement mount must be separate from output storage')
        self.root = self.output/'ui-requests'
        self.root.mkdir(exist_ok=True)
        self.file = self.root/'requests.json'
        self.token = secrets.token_urlsafe(32)
        self.mutex = threading.RLock()
        self.stop_event = threading.Event()
        self.child = None
        self.children = {}
        self.workers = []
        from resource_governor import Governor
        self.governor=Governor()
        self.assignments={}
        self.thread = None
        self.lease = None
        self.ready = False
        self.drafts = {}
        self.state = read(self.file) or dict(paused=False, failures=0, jobs=[])
        # Additive migration: keep original records and unknown fields intact.
        self.state.setdefault('view', {})
        self.state['schema_version'] = 2
        self.error = None

    def resolve(self, text):
        if not isinstance(text, str) or len(text)>4096 or '\x00' in text:
            raise ValueError('Invalid media path')
        requested = Path(text)
        if '..' in requested.parts: raise ValueError('Parent traversal is not allowed')
        path = requested if requested.is_absolute() else self.media/requested
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self.media): raise ValueError('Choose a path inside the media mount')
        # Exclude every symlink component, not just the final filename.
        cursor = path
        while cursor != self.media and cursor != cursor.parent:
            if cursor.is_symlink(): raise ValueError('Symlink sources are not supported')
            cursor = cursor.parent
        return resolved

    def check_media_access(self, mode):
        readonly=self.readonly(self.media)
        if not readonly and self.replacement_root is None:
            raise ValueError('Writable media requires a configured publication target')
        if mode=='replace' and (self.replacement_root is None or readonly):
            raise ValueError('Replacement requires making the /media mount writable in TrueNAS storage settings')

    def browse(self, text='', offset=0, videos=False, recursive=True):
        path = self.resolve(text)
        if not path.is_dir(): raise ValueError('Choose a directory to browse')
        offset = int(offset)
        if offset<0: raise ValueError('Invalid page')
        entries=[]
        candidates=path.rglob('*') if videos and recursive else path.iterdir()
        for child in candidates:
            if child.is_symlink(): continue
            if (not videos and child.is_dir()) or (child.is_file() and child.suffix.lower() in EXTENSIONS):
                try:self.resolve(str(child))
                except ValueError:continue
                entries.append(dict(name=str(child.relative_to(path)) if videos else child.name,
                                    path=str(child.relative_to(self.media)),directory=child.is_dir()))
        entries.sort(key=lambda row:(not row['directory'],row['name'].casefold()))
        return dict(path=str(path.relative_to(self.media)),parent=str(path.parent.relative_to(self.media)) if path!=self.media else None,
                    entries=entries[offset:offset+100],next_offset=offset+100 if len(entries)>offset+100 else None)

    def settings(self, data):
        if not isinstance(data,dict) or set(data)-{'path','mode','codec','hardware','quality','minimum_savings','recursive','recheck','legacy_color','history_mode','age_unit','age_value'}:
            raise ValueError('Unknown setting')
        mode=data.get('mode','analyze');codec=data.get('codec','auto')
        hardware=data.get('hardware','auto');quality=data.get('quality','auto')
        if mode not in ('analyze','test','encode','replace','keep') or codec not in ('auto','hevc','av1'):
            raise ValueError('Unsupported operation or codec')
        if hardware not in ('auto','nvidia','amd','intel') or quality not in ('auto','transparent','balanced','compact'):
            raise ValueError('Unsupported hardware or quality preset')
        savings=data.get('minimum_savings',0)
        if type(savings) not in (int,float) or not 0<=savings<=90: raise ValueError('Savings must be 0–90 percent; outputs must always be smaller')
        recursive=data.get('recursive',True)
        if type(recursive) is not bool: raise ValueError('Invalid recursion setting')
        recheck=data.get('recheck',False)
        if type(recheck) is not bool: raise ValueError('Invalid recheck setting')
        history_mode=data.get('history_mode','all' if recheck else 'reuse')
        if history_mode not in ('reuse','retry','all'):raise ValueError('Invalid history selection')
        if recheck and history_mode!='all':raise ValueError('Conflicting history settings')
        legacy_color=data.get('legacy_color','inspect')
        if legacy_color not in ('inspect','bt709-limited'):raise ValueError('Invalid legacy color setting')
        if legacy_color!='inspect' and mode not in ('analyze','test'):
            raise ValueError('Color assumptions are allowed only for inspection or sample tests; not full conversion/replacement')
        codecs=[c for c in self.codecs if c in ('hevc','av1')] if codec=='auto' else [codec]
        if mode=='replace' and self.replacement_root is None:raise ValueError('Replacement is not enabled in app settings')
        if mode in ('test','encode','replace') and (not codecs or any(c not in self.codecs for c in codecs)):
            raise ValueError('Selected codec must be playback-verified in app settings')
        from media_workflow import file_age_settings
        age=file_age_settings(data.get('age_unit','all'),data.get('age_value'))
        return dict(mode=mode,codec=codec,hardware=hardware,quality=quality,**age,
                    minimum_savings=savings,recursive=recursive,codecs=codecs,recheck=history_mode=='all',
                    history_mode=history_mode,legacy_color=legacy_color)

    def history_index(self):
        """Transient per-operation index; durable matching rules remain below."""
        index={}
        for job in self.state['jobs']:
            for path in {job['source'],job.get('published_path')} - {None}:
                index.setdefault(path,[]).append(job)
        return index

    def history_match(self, path, fingerprint, settings, exclude=None, candidates=None):
        """Durable requests are the ledger; never infer success from a failed run."""
        records=self.state['jobs'] if candidates is None else candidates
        if settings.get('history_mode')=='retry':
            related=[j for j in records if j['id']!=exclude and
                     path in (j['source'],j.get('published_path'))]
            # Active claims and successful conversion/explicit keep decisions win
            # over failures from later redundant runs, including manual publication.
            protected=next((j for j in reversed(related) if j['state'] in
                            ('pending','running','replaced','awaiting-playback','kept-original')),None)
            if protected:return protected
            latest=next((j for j in reversed(related) if j['signature']==fingerprint),None)
            if latest and latest['state'] in ('skipped','failed','interrupted'):
                return None
            return dict(id=None,state='not-selected',reason='Retry only: no skipped, failed or interrupted result for this file version')
        for previous in reversed(records):
            if previous['id']==exclude: continue
            state=previous['state']
            current=previous.get('published_path') if state=='replaced' else previous['source']
            stamp=previous.get('published_signature') if state=='replaced' else previous['signature']
            if current!=path or stamp!=fingerprint: continue
            if state in ('pending','running'):
                return previous
            if state=='skipped' and (previous.get('history_decision') or
                    previous.get('decision_code')=='already_efficient_for_settings' or
                    previous.get('reason','').startswith(('Unsupported input:','Full output did not save enough space'))):
                # Automatic conclusions apply to their measured policy/settings,
                # unlike an explicit keep or a completed replacement.
                if previous.get('evaluation_policy')!=EVALUATION_POLICY:continue
                keys=('codec','hardware','quality','minimum_savings','codecs','legacy_color')
                if any(previous['settings'].get(k)!=settings.get(k) for k in keys):continue
            if (state=='skipped' and previous.get('reason','').startswith('Unsupported input:')
                    and previous.get('execution_version',previous.get('app_version'))!=VERSION):
                # Old admission failures are not evidence against a newly
                # implemented route. Successful copies/replacements stay protected.
                continue
            if settings.get('recheck'): continue
            if state in ('kept-original','replaced'): return previous
            if state=='awaiting-playback' and settings['mode']!='replace': return previous
            if state=='skipped' and (previous.get('history_decision') or
                    previous.get('reason','').startswith(('Unsupported input:', 'Full output did not save enough space'))):
                return previous
            if state=='skipped':
                # Older requests predate the explicit decision marker. Import only
                # an actual completed trial decision, not collisions or failures.
                folder=self.root/('request-'+previous['id'])
                if folder.resolve().is_relative_to(self.root):
                    for report in folder.glob('auto-*/status.json'):
                        if not report.resolve().is_relative_to(self.root):continue
                        result=read(report)
                        decision=result.get('decision',{})
                        policy=read(report.parent/'plan.json').get('evaluation_policy')
                        keys=('codec','hardware','quality','minimum_savings','codecs','legacy_color')
                        same_settings=all(previous['settings'].get(k)==settings.get(k) for k in keys)
                        if (result.get('state')=='trials-completed' and decision.get('cacheable') is True
                                and decision.get('action')=='keep_original' and policy==EVALUATION_POLICY and same_settings):
                            return previous
            if state in ('analyzed','tested') and settings['mode']==previous['settings']['mode']:
                return previous
        return None

    def preview(self, data):
        from media_workflow import file_age_match
        settings=self.settings(data)
        source=self.resolve(data.get('path',''))
        self.check_media_access(settings['mode'])
        files=[]
        age_counts=dict(outside_age_window=0,creation_date_unavailable=0)
        age_checked_at=time.time()
        with self.mutex:index=self.history_index()
        candidates=source.rglob('*') if source.is_dir() and settings['recursive'] else source.iterdir() if source.is_dir() else [source]
        for candidate in candidates:
            if candidate.suffix.lower() not in EXTENSIONS or not candidate.is_file(): continue
            path=self.resolve(str(candidate))
            selected,reason=file_age_match(path,settings,age_checked_at)
            if not selected:
                age_counts[reason]+=1
                continue
            if settings['mode']=='replace':
                from validated_replace import target_for
                target_for(path,self.media,self.replacement_root)
            stamp=signature(path)
            with self.mutex: previous=self.history_match(str(path),stamp,settings,candidates=index.get(str(path),[]))
            files.append(dict(path=str(path),signature=stamp,
                              history_reason=('Already recorded: '+previous['state']+'. '+previous.get('reason','')) if previous else None))
        if not files:
            raise ValueError('No supported video files match this selection. '+
                f"{age_counts['outside_age_window']} outside age window; {age_counts['creation_date_unavailable']} with unavailable creation date.")
        files.sort(key=lambda row:row['path'])
        now=time.time()
        with self.mutex:
            self.drafts={k:v for k,v in self.drafts.items() if v['expires']>now}
            if len(self.drafts)>=20: raise ValueError('Too many previews; wait for old previews to expire')
            token=uuid.uuid4().hex
            draft=dict(settings=settings,files=files,expires=now+600,folder=str(source if source.is_dir() else source.parent))
            self.drafts[token]=draft
        return dict(preview_id=token,files=files,settings=settings,expires=draft['expires'],
                    age_filter=dict(**age_counts,checked_at=age_checked_at),
                    original_policy='Replace originals after full validation. Old originals are permanently removed.' if settings['mode']=='replace' else 'Keep originals. No replacement or deletion.',
                    note='Preview lists files only. Analysis tests encoders against source geometry and metadata. HDR uses native preservation plus a common rendered-view quality metric. Dolby Vision, including combined Dolby Vision + HDR10+, is temporarily skipped; originals are retained.')

    def save(self):
        write(self.file,self.state)

    def submit(self, token, confirm_replace=False):
        with self.mutex:
            if not self.ready: raise ValueError('Control worker is not ready')
            draft=self.drafts.get(token)
            if draft is None or draft['expires']<time.time(): raise ValueError('Preview expired or already submitted')
            if draft.get('retry_of'):
                previous=next(j for j in self.state['jobs'] if j['id']==draft['retry_of'])
                if not self.recovery_info(previous)['retry_allowed']:
                    raise ValueError('Retry now requires publication recovery; preview again after resolving it')
            if draft['settings']['mode']=='replace' and confirm_replace is not True:raise ValueError('Explicit replacement confirmation required')
            self.check_media_access(draft['settings']['mode'])
            for row in draft['files']:
                if signature(self.resolve(row['path']))!=row['signature']: raise ValueError('Source changed; preview again')
            ids=[];skipped=[];batch_id=uuid.uuid4().hex
            index=self.history_index()
            for row in draft['files']:
                previous=self.history_match(row['path'],row['signature'],draft['settings'],candidates=index.get(row['path'],[]))
                if previous:
                    skipped.append(dict(path=row['path'],job_id=previous['id'],state=previous['state'],reason=previous.get('reason','')))
                    continue
                identifier=uuid.uuid4().hex
                self.state['jobs'].append(dict(id=identifier,source=row['path'],signature=row['signature'],
                    settings=draft['settings'],state='kept-original' if draft['settings']['mode']=='keep' else 'pending',created=time.time(),
                    batch_id=batch_id,batch_folder=draft.get('folder'),app_version=VERSION,
                    **({'finished':time.time()} if draft['settings']['mode']=='keep' else {})))
                index.setdefault(row['path'],[]).append(self.state['jobs'][-1])
                ids.append(identifier)
            self.save()
            del self.drafts[token]
            return dict(queued=len(ids),ids=ids,history_skipped=skipped,message='Request recorded; originals protected')

    def snapshot(self):
        with self.mutex:
            counts={}
            for job in self.state['jobs']: counts[job['state']]=counts.get(job['state'],0)+1
            active=[j for j in self.state['jobs'] if j['state'] in ('pending','running')]
            finished=[j for j in self.state['jobs'] if j['state'] not in ('pending','running')]
            jobs=[dict(j) for j in active+finished]
            # Explain historical failures without rewriting history or retrying jobs.
            from dashboard import tail
            for job in jobs:
                if job.get('reason')=='Worker failed; see worker.log':
                    path=self.root/('request-'+job['id'])/'worker.log'
                    if path.resolve().is_relative_to(self.root):
                        log=tail(path)
                        if 'ValueError: Only progressive 8-bit 4:2:0 SDR is supported by measured auto mode' in log:
                            job['reason']='Unsupported input: this workflow requires progressive 8-bit SDR video. Original retained.'
            pause_reason='Queue paused. Resume when ready.' if self.state['paused'] else None
            wait_reason=pause_reason or self.error
            if counts.get('pending') and not wait_reason:
                if not self.ready:wait_reason='Waiting for the queue worker to become ready'
                else:
                    blocker=self.busy()
                    if blocker:wait_reason=blocker if isinstance(blocker,str) else 'Waiting for standalone work to finish'
                    else:
                        resource_reason=self.governor.status.get('reason')
                        wait_reason=resource_reason if resource_reason and resource_reason!='Resources available' else 'Waiting for the next worker slot and admission check'
            return dict(enabled=True,ready=self.ready,csrf_token=self.token,paused=self.state['paused'],pause_reason=pause_reason,error=self.error,
                        wait_reason=wait_reason,
                        counts=counts,playback_codecs=self.codecs,replacement_enabled=self.replacement_root is not None and not self.readonly(self.media),
                        total_replaced_saved_bytes=sum(j.get('saved_bytes',0) for j in self.state['jobs'] if j['state']=='replaced'),
                        lifetime_savings=self.lifetime_savings(),resources=dict(self.governor.status),
                        resource_profile=self.state.get('resource_profile','shared'),jobs=jobs,
                        app_version=VERSION,view=dict(self.state.get('view',{})),server_time=time.time())

    def lifetime_savings(self):
        """Count confirmed publications only, including retained manual receipts."""
        entries={}
        for job in self.state['jobs']:
            if job['state']=='replaced':
                key=job['id']
                entries[key]=(job.get('original_bytes',0),job.get('output_bytes',0),job.get('saved_bytes',0))
        for path in self.root.glob('request-*/auto-*/approved-replacement.json'):
            if not path.resolve().is_relative_to(self.root):continue
            receipt=read(path)
            old,new=receipt.get('old_bytes'),receipt.get('new_bytes')
            key=receipt.get('output_sha256')
            if (receipt.get('original_removed') is True and isinstance(key,str) and len(key)==64
                    and type(old) is int and type(new) is int and old>new>0):
                entries.setdefault(path.parent.parent.name.removeprefix('request-'),(old,new,old-new))
        original=sum(x[0] for x in entries.values());saved=sum(x[2] for x in entries.values())
        return dict(saved_bytes=saved,original_bytes=original,replaced_files=len(entries),
                    percent=100*saved/original if original else None)

    def action(self, data):
        action=data.get('action')
        if action in ('archive-results','undo-archive','view-preferences'):return self.view_action(data)
        if action in ('inspect-recovery','retry-preview','cleanup-preview','cleanup-confirm'):return self.history_action(data)
        if action=='preview': return self.preview(data.get('settings'))
        if action=='submit': return self.submit(data.get('preview_id'),data.get('confirm_replace',False))
        if action=='resource-profile':
            from resource_governor import PROFILES
            profile=data.get('profile')
            if profile not in PROFILES:raise ValueError('Unknown resource profile')
            with self.mutex:
                if not self.ready:raise ValueError('Control worker is not ready; settings are read-only')
                self.state['resource_profile']=profile;self.save()
            return dict(message='Resource profile saved. Active jobs finish normally; new admissions use '+profile+'.')
        if action not in ('pause','resume'): raise ValueError('Unknown control action')
        with self.mutex:
            if not self.ready:raise ValueError('Control worker is not ready')
            self.state['paused']=action=='pause'
            if action=='resume': self.state['failures']=0
            self.save()
        return dict(message='Paused after current job' if action=='pause' else 'Queue resumed')

    def build_command(self, job, folder):
        from media_workflow import automatic_arguments
        return [sys.executable,'-B','-m','auto_optimize',
                *automatic_arguments(job['source'],folder,job['settings'],
                                     capability_cache_dir=self.output/'.gpu-capabilities')]

    def step(self):
        with self.mutex:
            if self.stop_event.is_set() or self.state['paused'] or self.busy():return
            job=next((j for j in self.state['jobs'] if j['state']=='pending'),None)
            if job is None:return
            running=[j for j in self.state['jobs'] if j['state']=='running']
            # Conservatively reserve full scratch estimates for every active job.
            reserved=sum(j['signature'][0]*3 for j in running)
            if shutil.disk_usage(self.output).free<max(12*1024**3,job['signature'][0]*3+reserved):
                self.error='Waiting for output space: at least 12 GiB and three times source size';return
            self.error=None
            self.assignments[threading.get_ident()]=job
            source=self.resolve(job['source'])
            # Serialize jobs which could publish to the same path, even when
            # source containers differ. This claim covers encoding + publication.
            from validated_replace import readable_destination
            target_key=str(readable_destination(source)).casefold()
            if any(str(readable_destination(Path(j['source']))).casefold()==target_key for j in running):return
            self.check_media_access(job['settings']['mode'])
            if signature(source)!=job['signature']:
                raise ValueError('Source changed; preview again')
            previous=self.history_match(job['source'],job['signature'],job['settings'],exclude=job['id'])
            if previous and previous['state'] not in ('pending','running'):
                job.update(state='skipped',reason='Already processed in job '+previous['id'],finished=time.time())
                self.save();return
            if job['settings']['mode']=='replace':
                from validated_replace import target_for, destination_for, DestinationConflict
                try:destination_for(target_for(source,self.media,self.replacement_root))
                except DestinationConflict as exc:
                    job.update(state='skipped',reason=str(exc),finished=time.time())
                    self.state['failures']=0;self.save();return
            folder=self.root/('request-'+job['id'])
            folder.mkdir(exist_ok=False)
            job.update(state='running',output=str(folder),started=time.time(),execution_version=VERSION,
                       evaluation_policy=EVALUATION_POLICY);self.save()
            self.assignments[threading.get_ident()]=job
        with (folder/'worker.log').open('xb') as log:
            with self.mutex:
                if self.stop_event.is_set():
                    job.update(state='interrupted',reason='Service stopped before encoding');self.save();return
                command=self.build_command(job,folder)
                if os.name=='posix' and shutil.which('nice'):command=['nice','-n','10',*command]
                child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                self.children[job['id']]=child
            code=child.wait()
            with self.mutex:self.children.pop(job['id'],None)
        state,reason='failed','Worker failed; see worker.log'
        results=list(folder.glob('auto-*/status.json'))
        if code and len(results)==1:
            recorded_error=read(results[0]).get('error')
            if isinstance(recorded_error,str) and recorded_error:
                reason=recorded_error[:4096]
        eligibility=read(folder/'eligibility.json')
        if code==0:
            if eligibility.get('state')=='unsupported':
                prefix='' if eligibility.get('reason_code')=='dolby_vision_temporarily_disabled' else 'Unsupported input: '
                state,reason='skipped',prefix+eligibility['reason']
                job['history_decision']=True
            elif job['settings']['mode']=='analyze':state,reason='analyzed','Read-only analysis complete; see worker.log for plan'
            else:
                results=list(folder.glob('auto-*/status.json'))
                if len(results)==1:
                    result=read(results[0]);stage=result.get('state')
                    selection=read(results[0].parent/'selection.json') or result.get('decision',{})
                    job['evidence']=decision_evidence(results[0].parent,selection)
                    if stage=='validated-copy-awaiting-playback':
                        candidate=Path(result.get('output',''))
                        hashes=[result.get(k) for k in ('source_sha256','output_sha256')]
                        valid_hashes=all(isinstance(h,str) and len(h)==64 and all(c in '0123456789abcdef' for c in h) for h in hashes)
                        if (not candidate.is_file() or candidate.is_symlink() or
                                candidate.resolve().parent!=results[0].parent.resolve() or
                                not candidate.resolve().is_relative_to(folder.resolve()) or
                                candidate.suffix.lower()!='.mkv' or candidate.stat().st_size<=0 or
                                result.get('source')!=job['source'] or not valid_hashes):
                            state,reason='failed','Validated-copy record is incomplete or its output is missing/unsafe; original retained'
                        else:
                            state,reason='awaiting-playback','Validated safe copy; original retained'
                            job['original_bytes']=job['signature'][0]
                            job['output_bytes']=candidate.stat().st_size
                    elif stage=='trials-completed':
                        decision=result.get('decision',{})
                        state='tested' if decision.get('action')=='encode_copy' else 'skipped'
                        reason=decision.get('reason','Sample testing complete')
                        job['decision_code']=decision.get('reason_code')
                        if decision.get('reason_code')=='evaluation_inconclusive':state='failed'
                        if state=='skipped':job['history_decision']=True
                    elif stage=='full-output-rejected-insufficient-savings':
                        state,reason='skipped','Full output did not save enough space'
                        job['history_decision']=True
                        job['decision_code']='full_output_insufficient_savings'
                        job['evidence']['full_size']={key:result[key] for key in
                            ('saved_percent','source_bytes','output_bytes','minimum_savings_percent','full_validation_performed')
                            if key in result}
        if state=='awaiting-playback' and job['settings']['mode']=='replace':
            from validated_replace import replace_validated, DestinationConflict
            try:
                with (folder/'publication.log').open('xb') as log:
                    with self.mutex:
                        if self.stop_event.is_set():raise RuntimeError('Service stopping; publication not started')
                        command=[sys.executable,'-B','-m','publish_worker','--source',str(source),'--media',str(self.media),
                                 '--writable',str(self.replacement_root),'--result',str(results[0].parent),'--folder',str(folder),
                                 '--minimum',str(job['settings']['minimum_savings']),'--job',job['id']]
                        if os.name=='posix' and shutil.which('nice'):command=['nice','-n','10',*command]
                        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                        self.children[job['id']]=child
                    code=child.wait()
                    with self.mutex:self.children.pop(job['id'],None)
                    if code:raise RuntimeError('Publication interrupted or failed; see publication.log and recovery journal')
                receipt=read(results[0].parent/'replacement.json')
                if receipt.get('state')!='replaced':raise RuntimeError('Missing confirmed replacement receipt')
                state,reason='replaced','Original replaced after full validation and verified publication.'
                job['saved_bytes']=receipt['saved_bytes']
                job['published_path']=receipt['target']
                job['published_signature']=signature(Path(receipt['target']))
                job['published_sha256']=receipt['output_sha256']
            except DestinationConflict as exc:
                state,reason='skipped',str(exc)
            except Exception as exc:
                state,reason='failed','Replacement needs attention: '+str(exc)
        with self.mutex:
            if self.stop_event.is_set() and state=='failed':
                state,reason='interrupted','Service stopped; review retained outputs/recovery journal before retrying'
            job.update(state=state,reason=reason,finished=time.time())
            self.state['failures']=self.state['failures']+1 if state=='failed' else 0
            # A failed video is terminal for that request, not for the queue.
            self.save()

    def worker_step(self):
        try:self.step()
        except BaseException as exc:
            with self.mutex:
                job=self.assignments.get(threading.get_ident())
                if job and job['state'] in ('pending','running'):
                    job.update(state='interrupted' if self.stop_event.is_set() else 'failed',reason=str(exc),finished=time.time())
                    self.state['failures']+=1
                else:self.state['paused']=True
                self.error=str(exc);self.save()
        finally:
            with self.mutex:self.assignments.pop(threading.get_ident(),None)

    def loop(self):
        try:
            import fcntl
            self.lease=(self.root/'worker.lock').open('a')
            fcntl.flock(self.lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.mutex:
                for job in self.state['jobs']:
                    if job['state']=='running':
                        job.update(state='interrupted',reason='Interrupted during restart; review before resubmitting',finished=time.time())
                        self.state['paused']=True
                self.save();self.ready=True
            while not self.stop_event.is_set():
                self.workers=[w for w in self.workers if w.is_alive()]
                allowed=self.governor.admit(self.state.get('resource_profile','shared'),len(self.workers))
                with self.mutex:
                    if allowed and not self.state['paused'] and any(j['state']=='pending' for j in self.state['jobs']) and not self.busy():
                        worker=threading.Thread(target=self.worker_step,daemon=True,name='media-job')
                        self.workers.append(worker);worker.start();self.governor.last_launch=time.monotonic()
                self.stop_event.wait(5)
        except Exception as exc:
            self.error=str(exc)
        finally:
            self.ready=False
            for worker in self.workers:worker.join()
            if self.lease:self.lease.close()

    def start(self):
        self.thread=threading.Thread(target=self.loop,daemon=True,name='ui-safe-copy-worker');self.thread.start()

    def stop(self):
        self.stop_event.set()
        with self.mutex:children=list(self.children.values())
        for child in children:
            if child.poll() is None:
                try:os.killpg(child.pid,signal.SIGINT)
                except ProcessLookupError:pass
        for child in children:
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        if self.thread:self.thread.join(timeout=20)
