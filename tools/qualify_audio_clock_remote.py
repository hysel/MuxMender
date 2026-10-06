"""Read-only qualification of a failed source's complete strict audio decode."""
import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from job_tracking import Job


def main():
    jobs=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    job=Job(jobs,'Complete source audio diagnostic clock qualification')
    remote='/work/audio-clock-'+uuid.uuid4().hex
    host='muxmender@192.168.1.232';key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519'
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in (ROOT/'python').rglob('*.py'):
            bundle.write(path,'python/'+path.relative_to(ROOT/'python').as_posix())
    payload='''import base64,io,json,os,pathlib,subprocess,sys,time,zipfile
if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only audio research')
os.nice(19)
root=pathlib.Path(REMOTE);root.mkdir(exist_ok=False)
bundle=zipfile.ZipFile(io.BytesIO(base64.b64decode(ARCHIVE)))
for name in bundle.namelist():
 p=pathlib.PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive')
bundle.extractall(root);sys.path.insert(0,str(root/'python'))
from job_tracking import Job,isolated_progress
from task_progress import digest
from auto_optimize import Workflow
from types import SimpleNamespace
job=Job(root/'reports','Complete source audio diagnostic clock qualification')
try:
 state=json.loads(pathlib.Path('/output/ui-requests/requests.json').read_text())
 request=next(j for j in state['jobs'] if j['id']=='706b7b3d273b4bcb9785c475aefe2f58')
 source=pathlib.Path(request['source']).resolve(strict=True)
 if not source.is_relative_to('/media'):raise ValueError('Source outside read-only media mount')
 job.save(phase='Hashing unchanged source before complete audio test')
 before=digest(source,lambda:None)
 metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(source)],text=True,timeout=30))
 workflow=Workflow(SimpleNamespace(ffmpeg='ffmpeg',timeout=300),root,lambda:None)
 started=time.monotonic()
 with isolated_progress(lambda values:job.save(**values)):
  workflow.preflight_source_audio(source,metadata)
 proof=json.loads((root/'source-audio-preflight.json').read_text())
 job.save(phase='Verifying complete source hash after strict decode')
 if digest(source,lambda:None)!=before:raise ValueError('Source changed')
 if proof.get('state')!='passed' or proof.get('original_clock_retry') is not True:raise ValueError('Expected full strict original-clock retry did not pass')
 result=dict(passed=True,source_unchanged=True,source_sha256=before,complete_audio_decode=True,
  strict_decode=True,tracks=proof['tracks'],original_clock_retry=True,seconds=time.monotonic()-started,
  replacement_authorized=False,scope='Full source audio decode only; candidate timing/packet/quality checks remain mandatory')
 (root/'result.json').write_text(json.dumps(result,indent=2))
 job.save(state='completed',phase='Complete audio clock qualification passed',detail=json.dumps(result),finished=time.time())
 print('AUDIO_RESULT='+json.dumps(result))
except BaseException as exc:
 job.save(state='failed',phase='Complete audio clock qualification failed',error=str(exc),finished=time.time());raise
'''.replace('REMOTE',repr(remote)).replace('ARCHIVE',repr(base64.b64encode(archive.getvalue()).decode()))
    config=job.directory/'monitor-config.json'
    config.write_text(json.dumps([dict(id=remote,title='Live complete source audio qualification',host=host,key=key,
        command=['sudo','-n','/root/muxmender-research-access'],roots=[remote],kind='tracked')]))
    observer=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),
        '--config',str(config),'--output',str(jobs),'--interval','10'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    terminal=False
    try:
        job.save(phase='Full strict audio test on read-only source',detail='Low CPU priority; no GPU use or publication')
        run=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
            'sudo -n /root/muxmender-research-access'],input=payload,text=True,capture_output=True,timeout=600)
        terminal=True
        (job.directory/'research.log').write_text(run.stdout+run.stderr)
        rows=[line.split('=',1)[1] for line in run.stdout.splitlines() if line.startswith('AUDIO_RESULT=')]
        if run.returncode or not rows:raise RuntimeError('Audio qualification failed: '+run.stderr[-1000:])
        report=json.loads(rows[-1]);(job.directory/'result.json').write_text(json.dumps(report,indent=2))
        job.save(state='completed',phase='Full audio retry qualified',detail=json.dumps(report),finished=time.time())
        print(json.dumps(report))
    except BaseException as exc:
        job.save(state='failed' if terminal else 'stale',phase='Audio research needs inspection',error=str(exc),finished=time.time() if terminal else None);raise
    finally:
        if terminal:
            try:observer.wait(timeout=20)
            except subprocess.TimeoutExpired:observer.terminate();observer.wait(timeout=5)


if __name__=='__main__':main()
