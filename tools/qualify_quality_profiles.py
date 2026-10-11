"""Linux-only, generated SDR profile qualification; no library source access."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def comparison_cases(options):
    matrix=options.get('preset_matrix',False)
    if type(matrix) is not bool:raise ValueError('preset_matrix must be boolean')
    presets=('tv1080','mobile720','small480') if matrix else ('original',)
    return [(preset,name) for preset in presets for name in ('strict','balanced','space-saver')]


def require_idle():
    production=json.loads(Path('/output/ui-requests/requests.json').read_text())
    if not production.get('paused') or any(j.get('state')=='running' for j in production['jobs']):
        raise RuntimeError('Keep production paused and idle during serial GPU qualification')


def run():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Run this qualification only in the Linux research environment')
    root=Path(__file__).resolve().parent
    sys.path.insert(0,str(root/'python'))
    from job_tracking import progress
    from media_workflow import automatic_arguments
    from quality_profiles import profile
    options=root/'research-options.json'
    cases=comparison_cases(json.loads(options.read_text()) if options.exists() else {})
    require_idle()
    inputs=root/'generated';inputs.mkdir(exist_ok=False)
    source=inputs/'generated-source.mkv'
    progress('Generating video-only SDR fixture',detail='No library source, audio qualification or replacement')
    subprocess.run(['ffmpeg','-hide_banner','-nostdin','-v','error','-n',
        '-f','lavfi','-i','testsrc2=size=1920x1080:rate=24:duration=12',
        '-vf','setfield=prog','-c:v','libx264','-preset','ultrafast','-crf','0',
        '-threads','2','-g','24','-pix_fmt','yuv420p','-color_primaries','bt709',
        '-color_trc','bt709','-colorspace','bt709','-color_range','tv',str(source)],
        check=True,timeout=180)
    baseline=hashlib.sha256(source.read_bytes()).hexdigest()
    rows=[]
    for index,(preset,name) in enumerate(cases):
        require_idle()
        progress('Qualifying '+preset+' / '+name,index,len(cases),unit='preset/profile combinations',detail='Generated video; serial NVIDIA encoding and full technical validation')
        folder=root/'cases'/preset/name
        settings=dict(mode='encode',hardware='nvidia',quality='auto',quality_profile=name,
            output_preset=preset,hdr_policy='preserve',minimum_savings=10,
            savings_mode='fixed',codecs=['hevc','av1'],timeout_minutes=15)
        command=[sys.executable,'-B',str(root/'python/auto_optimize.py'),
            *automatic_arguments(source,folder,settings,min_free_gib=2)]
        started=time.monotonic()
        with (root/(preset+'-'+name+'.log')).open('x') as log:
            process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        files=list(folder.glob('auto-*/status.json'))
        status=json.loads(files[0].read_text()) if len(files)==1 else {}
        selection=json.loads((files[0].parent/'selection.json').read_text()) if files and (files[0].parent/'selection.json').is_file() else {}
        expected=profile(name)
        policy=dict(id=name,mean=expected['mean'],p5=expected['p5'])
        passed=(process.returncode==0 and status.get('state')=='validated-copy-awaiting-playback'
            and status.get('quality_policy')==policy and selection.get('quality_policy')==policy
            and hashlib.sha256(source.read_bytes()).hexdigest()==baseline)
        cleanup=json.loads((files[0].parent/'terminal-cleanup.json').read_text()) if files and (files[0].parent/'terminal-cleanup.json').is_file() else {}
        passed=passed and cleanup.get('state')=='cleaned'
        rows.append(dict(profile=name,output_preset=preset,passed=passed,exit_code=process.returncode,
            seconds=round(time.monotonic()-started,3),state=status.get('state'),
            error=status.get('error'),quality_policy=status.get('quality_policy'),
            saved_percent=status.get('saved_percent'),selected=selection.get('selected'),cleanup={k:cleanup.get(k) for k in ('state','files','bytes','error')}))
        (root/'result.json').write_text(json.dumps(dict(results=rows,complete=len(rows)==len(cases),passed=len(rows)==len(cases) and all(r['passed'] for r in rows),
            source_unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==baseline,
            publication_authorized=False,scope='Generated video-only SDR; not real-library, audio or HDR qualification'),indent=2))
    progress('Profile qualification finished',len(cases),len(cases),unit='preset/profile combinations')
    return 0 if all(row['passed'] for row in rows) else 1


if __name__=='__main__':
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only qualification')
    root=Path(__file__).resolve().parent
    sys.path.insert(0,str(root/'python'))
    from job_tracking import tracked_call
    raise SystemExit(tracked_call(run,'NVIDIA quality profile qualification',folder=root/'reports'))
