"""Explicit approval of an existing validated copy; publication stays shared."""
from pathlib import Path
import threading
import secrets
import time
from autonomous_queue import read,signature


class CopyApproval:
    def copy_evidence(self, job):
        self.check_media_access('replace')
        if job['settings']['mode']!='encode' or job.get('publication_authorized') is False:
            raise ValueError('Only publication-qualified full safe copies can be approved')
        source=self.resolve(job['source'])
        if signature(source)!=job['signature'] or not self.identity_matches(job,str(source)):
            raise ValueError('Original changed since this copy was validated')
        folder=self.request_folder(job)
        if str(folder)!=job.get('output') or not folder.is_dir():
            raise ValueError('Validated request folder is missing')
        paths=list(folder.glob('auto-*/status.json'))
        if len(paths)!=1:raise ValueError('Exactly one full validation result is required')
        status_path=paths[0];result=status_path.parent
        if result.is_symlink() or status_path.is_symlink() or not result.resolve().is_relative_to(folder.resolve()):
            raise ValueError('Unsafe validation result path')
        status=read(status_path)
        if (status.get('state')!='validated-copy-awaiting-playback' or status.get('source')!=str(source)
                or status.get('publication_authorized') is False):
            raise ValueError('Copy has not passed publication-qualified full validation')
        from media_workflow import validated_output_container
        candidate=Path(status.get('output',''))
        if (candidate.is_symlink() or not candidate.is_file() or candidate.resolve().parent!=result.resolve()
                or not validated_output_container(status,candidate) or candidate.stat().st_size<=0):
            raise ValueError('Validated copy is missing or unsafe')
        if any((result/name).exists() or (result/name).is_symlink() for name in ('replacement.json','approved-replacement.json')):
            raise ValueError('A publication journal already exists; inspect recovery before replacing')
        selection=read(result/'selection.json');chosen=selection.get('selected') or {}
        if (read(result/'plan.json').get('color_inspection') or {}).get('assumed'):
            raise ValueError('Assumed color cannot authorize replacement')
        if selection.get('action')!='encode_copy' or not any(
                c.get('id')==chosen.get('id') and c.get('rejected_reasons')==[] for c in selection.get('candidates',[])):
            raise ValueError('Copy has no passing selected candidate')
        for key in ('source_sha256','output_sha256'):
            value=status.get(key)
            if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('Full validation hashes are missing')
        from control_service import source_identity
        files=[source,candidate,status_path,result/'selection.json']
        if (result/'plan.json').exists():files.append(result/'plan.json')
        if any(p.is_symlink() for p in files):raise ValueError('Linked publication inputs are not supported')
        from validated_replace import target_for,destination_for
        destination=destination_for(target_for(source,self.media,self.replacement_root),candidate.suffix)
        return dict(result=str(result),source=str(source),copy=str(candidate),target=str(destination),
                    identities={str(p):source_identity(p) for p in files},
                    source_sha256=status['source_sha256'],output_sha256=status['output_sha256'])

    def copy_action(self, data):
        with self.mutex:
            if not self.ready:raise ValueError('Control worker is not ready')
            now=time.time()
            self.copy_drafts={k:v for k,v in self.copy_drafts.items() if v['expires']>now}
            if data['action']=='approve-copy-preview':
                job=next((j for j in self.state['jobs'] if j['id']==data.get('job_id')),None)
                if not job or job['state']!='awaiting-playback':raise ValueError('Choose a finished validated safe copy')
                if any(j['state'] in ('pending','running') and j['source']==job['source'] for j in self.state['jobs']):
                    raise ValueError('This source already has queued or running work')
                evidence=self.copy_evidence(job)
                if len(self.copy_drafts)>=20:raise ValueError('Too many confirmations; try again shortly')
                token=secrets.token_urlsafe(24)
                self.copy_drafts[token]=dict(job_id=job['id'],evidence=evidence,expires=now+120)
                return dict(confirmation_id=token,expires=now+120,source=job['source'],target=evidence['target'],
                            source_bytes=Path(evidence['source']).stat().st_size,copy_bytes=Path(evidence['copy']).stat().st_size,
                            message='Replace the original with this validated copy. No re-encoding. The original is permanently removed only after verified publication.')
            if data.get('confirm') is not True:raise ValueError('Explicit replacement confirmation required')
            token=data.get('confirmation_id')
            if not isinstance(token,str):raise ValueError('Replacement confirmation required')
            draft=self.copy_drafts.get(token)
            if draft is None:raise ValueError('Confirmation expired or already used; review the copy again')
            job=next((j for j in self.state['jobs'] if j['id']==draft['job_id']),None)
            if not job or job['state']!='awaiting-playback':raise ValueError('Copy is no longer awaiting approval')
            if any(j['state'] in ('pending','running') and j['source']==job['source'] for j in self.state['jobs']):
                raise ValueError('This source already has queued or running work')
            if self.copy_evidence(job)!=draft['evidence']:raise ValueError('Original, copy or validation evidence changed; review again')
            empty=not any(j['state'] in ('pending','running') for j in self.state['jobs'])
            before=dict(job);paused=self.state['paused'];origin=self.state.get('pause_origin')
            job.update(state='pending',publication_only=True,approved_copy=draft['evidence'],
                       approved_at=now,copy_finished_at=job.get('finished'),copy_started_at=job.get('started'),
                       reason='Approved copy queued for verified replacement; no re-encoding')
            job.pop('finished',None)
            auto_started=self.state['paused'] and empty and not self.error and self.state.get('pause_origin') not in ('error','restart-recovery')
            if auto_started:self.state['paused']=False;self.state.pop('pause_origin',None)
            try:self.save()
            except Exception:
                job.clear();job.update(before);self.state['paused']=paused
                if origin is None:self.state.pop('pause_origin',None)
                else:self.state['pause_origin']=origin
                raise
            del self.copy_drafts[token]
            return dict(message='Replacement queued. The existing copy will be verified and published without re-encoding.',
                        job_id=job['id'],auto_started=auto_started)

    def step_approved_copy(self, job):
        with self.mutex:
            if job['state']!='pending' or self.stop_event.is_set() or self.state['paused']:return
        blocker=self.busy()
        with self.mutex:
            if job['state']!='pending' or self.stop_event.is_set() or self.state['paused'] or blocker:return
            from validated_replace import readable_destination
            key=str(readable_destination(Path(job['source']))).casefold()
            if any(j is not job and j['state']=='running' and str(readable_destination(Path(j['source']))).casefold()==key for j in self.state['jobs']):return
            self.assignments[threading.get_ident()]=job
            if self.copy_evidence(job)!=job['approved_copy']:
                raise ValueError('Approved publication inputs changed; original retained')
            folder=self.request_folder(job)
            job.update(state='running',started=time.time(),reason='Verifying and publishing the approved copy; no re-encoding')
            self.save()
        state,reason=self.publish_result(job,Path(job['source']),folder,Path(job['approved_copy']['result']))
        with self.mutex:
            job.pop('publishing',None)
            if state!='replaced' and job.get('cancel_requested') and not reason.startswith('Replacement needs attention:'):
                state,reason='cancelled','Cancelled before publication; original and safe copy retained'
            if self.stop_event.is_set() and state=='failed':
                state,reason='interrupted','Service stopped; review the publication journal before retrying'
            job.update(state=state,reason=reason,finished=time.time())
            if job.get('artifact_cleanup',{}).get('state')=='needs-attention':reason+=' Cleanup needs attention; see details';job['reason']=reason
            self.state['failures']=self.state['failures']+1 if state=='failed' else 0
            self.save()
