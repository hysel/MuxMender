"""Low-priority generated Linux research; no production settings or media writes."""
import base64
import argparse
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames',type=int,default=96)
    parser.add_argument('--width',type=int,default=1280)
    parser.add_argument('--height',type=int,default=720)
    args=parser.parse_args()
    if not 2<=args.frames<=720 or (args.width,args.height) not in ((1280,720),(1920,1080),(3840,2160)):
        parser.error('Use 2..720 frames at bounded 720p/1080p/2160p dimensions')
    jobs=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    job=Job(jobs,'HDR metric workers: generated low-priority comparison')
    remote='/work/hdr-metric-'+uuid.uuid4().hex
    host='muxmender@192.168.1.232';key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519'
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in (ROOT/'python').rglob('*.py'):
            bundle.write(path,'python/'+path.relative_to(ROOT/'python').as_posix())
        bundle.write(ROOT/'tools/research_quality_threads.py','research_quality_threads.py')
    payload='''import base64,io,json,os,pathlib,subprocess,sys,time,zipfile
if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only metric research')
os.nice(19)
root=pathlib.Path(REMOTE);root.mkdir(exist_ok=False)
bundle=zipfile.ZipFile(io.BytesIO(base64.b64decode(ARCHIVE)))
for name in bundle.namelist():
 p=pathlib.PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive')
bundle.extractall(root)
sys.path[:0]=[str(root/'python'),str(root)]
from job_tracking import Job,isolated_progress
job=Job(root/'reports','Generated HDR scoring comparison')
def cleanup():
 for name in ('reference.mkv','candidate.mkv'):
  path=root/name
  if path.is_file() and not path.is_symlink():path.unlink()
try:
 job.save(phase='Generating owned HDR controls')
 for label,crf in [('reference',18),('candidate',30)]:
  command=['ffmpeg','-v','error','-nostdin','-n','-filter_threads','2','-f','lavfi','-i',
   'testsrc2=size=WIDTHxHEIGHT:rate=24:duration=DURATION,format=yuv420p10le,setparams=range=limited:color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc',
   '-c:v','libx264','-threads','2','-preset','ultrafast','-crf',str(crf),'-pix_fmt','yuv420p10le',
   '-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc','-color_range','tv',str(root/(label+'.mkv'))]
  subprocess.run(command,capture_output=True,text=True,check=True,timeout=60)
 job.save(phase='Comparing two/four scoring workers over six balanced rounds')
 import research_quality_threads
 sys.argv=['metric',str(root/'reference.mkv'),str(root/'candidate.mkv'),'--output',str(root/'comparison'),'--frames','FRAMECOUNT','--compare-metric-workers']
 with isolated_progress(lambda values:job.save(**values)):
  research_quality_threads.main()
 result=json.loads((root/'comparison/result.json').read_text())
 cleanup()
 job.save(state='completed',phase='Generated HDR comparison passed',detail=json.dumps(result),finished=time.time())
 print('METRIC_RESULT='+json.dumps(result))
except BaseException as exc:
 job.save(state='failed',phase='HDR metric comparison needs investigation',error=str(exc),finished=time.time());raise
finally:
 cleanup()
'''.replace('REMOTE',repr(remote)).replace('ARCHIVE',repr(base64.b64encode(archive.getvalue()).decode()))
    payload=payload.replace('WIDTH',str(args.width)).replace('HEIGHT',str(args.height)).replace('DURATION',str(args.frames/24)).replace('FRAMECOUNT',str(args.frames))
    config=job.directory/'monitor-config.json'
    config.write_text(json.dumps([dict(id=remote,title='Live HDR metric worker comparison',host=host,key=key,
        command=['sudo','-n','/root/muxmender-research-access'],roots=[remote],kind='tracked')]))
    observer=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),
        '--config',str(config),'--output',str(jobs),'--interval','10'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        job.save(phase='Running generated Linux metric comparison',detail='Low CPU priority; no GPU work or library access')
        run=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
            'sudo -n /root/muxmender-research-access'],input=payload,text=True,capture_output=True,timeout=600)
        (job.directory/'research.log').write_text(run.stdout+run.stderr)
        rows=[line.split('=',1)[1] for line in run.stdout.splitlines() if line.startswith('METRIC_RESULT=')]
        if run.returncode or not rows:raise RuntimeError('Metric comparison failed: '+run.stderr[-1200:])
        report=json.loads(rows[-1]);(job.directory/'result.json').write_text(json.dumps(report,indent=2))
        job.save(state='completed',phase='Generated HDR metric comparison complete',detail=json.dumps(report),finished=time.time())
        print(json.dumps(report))
    except BaseException as exc:
        job.save(state='failed',phase='HDR metric comparison failed',error=str(exc),finished=time.time());raise
    finally:
        try:observer.wait(timeout=20)
        except subprocess.TimeoutExpired:observer.terminate();observer.wait(timeout=5)


if __name__=='__main__':main()
