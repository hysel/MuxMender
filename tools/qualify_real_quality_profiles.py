"""Serial Linux-only real SDR excerpt comparison; never publish source media."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def source_identity(path):
    s=Path(path).stat()
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)


def require_idle():
    state=json.loads(Path('/output/ui-requests/requests.json').read_text())
    if not state.get('paused') or any(j.get('state')=='running' for j in state['jobs']):
        raise RuntimeError('Keep production paused and let active work finish before qualification')


def assess(status,selection,expected,cleanup):
    bound=status.get('quality_policy')==expected and selection.get('quality_policy')==expected
    full=status.get('state')=='validated-copy-awaiting-playback'
    keep=(status.get('state')=='trials-completed' and selection.get('action')=='keep_original'
          and selection.get('reason_code')=='already_efficient_for_settings')
    return dict(passed=bound and (full or keep) and cleanup.get('state')=='cleaned',
        outcome='validated_copy' if full else 'original_kept' if keep else 'needs_attention')


def run(root):
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only real-media qualification')
    import av
    if av.__version__!='19.0.0':raise RuntimeError('This qualification requires the pinned PyAV 19.0.0 runtime')
    from job_tracking import progress
    from media_workflow import automatic_arguments
    from quality_profiles import profile
    require_idle();os.nice(10)
    manifest=json.loads((root/'cases.json').read_text())
    rows=[];total=len(manifest)*3
    for index,case in enumerate(manifest):
        source=Path(case['source']).resolve(strict=True)
        if not source.is_relative_to('/media'):raise ValueError('Source must be inside read-only media mount')
        identity=source_identity(source)
        case_root=root/'cases'/('case-'+str(index));case_root.mkdir(parents=True,exist_ok=False)
        seconds=case.get('seconds',60)
        if type(seconds) is not int or not 30<=seconds<=180:raise ValueError('Excerpt must be 30–180 seconds')
        probe=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(source)],
            capture_output=True,text=True,check=True,timeout=60)
        metadata=json.loads(probe.stdout)
        videos=[s for s in metadata['streams'] if s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic')]
        if len(videos)!=1 or videos[0].get('color_transfer') not in (None,'unknown','bt709') or any('dv_profile' in s for s in videos[0].get('side_data_list',[])):
            raise ValueError('This comparison is SDR-only; HDR transformations require separate qualification')
        if not any(s.get('codec_type')=='audio' for s in metadata['streams']) or not any(s.get('codec_type')=='subtitle' for s in metadata['streams']):
            raise ValueError('Selected case must contain audio and subtitles')
        duration=float(metadata['format']['duration']);start=int(duration*.25)
        if duration-start<seconds:raise ValueError('Source is too short for the requested excerpt')
        inputs=case_root/'inputs';inputs.mkdir()
        progress('Extracting real-video case '+str(index+1),len(rows),total,unit='case/profile comparisons',
            detail='Read-only source; keyframe-aligned excerpt with all tracks')
        with (case_root/'extract.log').open('x') as log:
            subprocess.run(['mkvmerge','-o',str(inputs/'source.mkv'),'--split',f'parts:{start}s-{start+seconds}s',str(source)],
                stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        clips=list(inputs.glob('*.mkv'))
        if len(clips)!=1:raise ValueError('Expected exactly one keyframe-aligned excerpt')
        excerpt=clips[0];baseline=hashlib.sha256(excerpt.read_bytes()).hexdigest()
        for name in ('strict','balanced','space-saver'):
            require_idle()
            progress('Case '+str(index+1)+' · '+name,len(rows),total,unit='case/profile comparisons',
                detail='Serial GPU trials, full excerpt validation, copied audio/subtitles; no replacement')
            expected=profile(name);policy=dict(id=name,mean=expected['mean'],p5=expected['p5'])
            settings=dict(mode='encode',hardware='nvidia',quality='auto',quality_profile=name,
                output_preset='original',hdr_policy='preserve',codecs=['hevc','av1'],
                minimum_savings=10,savings_mode='fixed',timeout_minutes=15)
            output=case_root/name
            command=[sys.executable,'-B',str(root/'python/auto_optimize.py'),
                *automatic_arguments(excerpt,output,settings,min_free_gib=8)]
            started=time.monotonic()
            with (case_root/(name+'.log')).open('x') as log:
                process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=3600)
            files=list(output.glob('auto-*/status.json'))
            def read(filename):
                path=files[0].parent/filename if len(files)==1 else None
                return json.loads(path.read_text()) if path and path.is_file() else {}
            status=read('status.json');selection=read('selection.json');cleanup=read('terminal-cleanup.json')
            unchanged=source_identity(source)==identity and hashlib.sha256(excerpt.read_bytes()).hexdigest()==baseline
            decision=assess(status,selection,policy,cleanup)
            rows.append(dict(case=index,profile=name,**dict(decision,passed=decision['passed'] and process.returncode==0 and unchanged),
                seconds=round(time.monotonic()-started,3),exit_code=process.returncode,
                source_unchanged=unchanged,excerpt_bytes=excerpt.stat().st_size,
                saved_percent=status.get('saved_percent'),quality_policy=status.get('quality_policy'),
                selected=selection.get('selected'),reason=selection.get('reason'),error=status.get('error'),
                audio_codecs=[s.get('codec_name') for s in metadata['streams'] if s.get('codec_type')=='audio'],
                subtitle_codecs=[s.get('codec_name') for s in metadata['streams'] if s.get('codec_type')=='subtitle'],
                cleanup={k:cleanup.get(k) for k in ('state','files','bytes','error')}))
            (root/'result.json').write_text(json.dumps(dict(results=rows,complete=len(rows)==total,
                passed=len(rows)==total and all(r['passed'] for r in rows),publication_authorized=False,
                scope='Real SDR excerpts with audio/subtitles; not full-movie or HDR transformation qualification'),indent=2))
            if not unchanged:raise ValueError('Source or excerpt changed during qualification')
    progress('Real-video profile comparison finished',total,total,unit='case/profile comparisons')
    return 0 if all(row['passed'] for row in rows) else 1


if __name__=='__main__':
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only qualification')
    root=Path(__file__).resolve().parent
    sys.path.insert(0,str(root/'python'))
    from job_tracking import tracked_call
    raise SystemExit(tracked_call(lambda:run(root),'Real-video quality profile comparison',folder=root/'reports'))
