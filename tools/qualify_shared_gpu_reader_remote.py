"""Queue generated shared-engine research after a tracked qualification ends."""
import argparse
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--after-job',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--full-validation',action='store_true')
    args=parser.parse_args()
    receipt=json.loads(args.receipt.read_text())
    jobroot=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    job=Job(jobroot,'Shared GPU reader integration · waiting for serial research')
    remote='/work/shared-reader-'+uuid.uuid4().hex
    key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519';host='muxmender@192.168.1.232'
    binary='/output/hdr-gpu-reader-build-20261002-r3/binary-r3/bin/ffprobe-cuda'
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in (ROOT/'python').rglob('*.py'):
            bundle.write(path,'python/'+path.relative_to(ROOT/'python').as_posix())
        bundle.write(ROOT/'tools/benchmark_shared_gpu_reader.py','benchmark_shared_gpu_reader.py')
        bundle.writestr('qualification.json',json.dumps(receipt))
    payload="""import base64,io,json,pathlib,sys,zipfile
if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only shared reader research')
root=pathlib.Path(REMOTE);root.mkdir(exist_ok=False)
archive=zipfile.ZipFile(io.BytesIO(base64.b64decode(ARCHIVE)))
for name in archive.namelist():
 p=pathlib.PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive')
archive.extractall(root)
sys.path[:0]=[str(root/'python'),str(root)]
from benchmark_shared_gpu_reader import main
sys.argv=['integration','--binary',BINARY,'--receipt',str(root/'qualification.json'),'--output',str(root/'qualification')]
try:code=main()
except Exception as exc:
 print(str(exc),file=sys.stderr);code=1
print('RESEARCH_RESULT='+(root/'qualification/benchmark.json').read_text().replace('\\n',' '),flush=True)
sys.exit(code)
""".replace('REMOTE',repr(remote)).replace('ARCHIVE',repr(base64.b64encode(archive.getvalue()).decode())).replace('BINARY',repr(binary))
    if args.full_validation:
        job.save(title='Shared GPU reader · complete generated conversion checks')
        payload=payload.replace('try:code=main()',"sys.argv+=['--full-validation']\ntry:code=main()")
    config=job.directory/'monitor-config.json'
    config.write_text(json.dumps([dict(id=remote,title='Live shared-engine GPU reader test',host=host,key=key,
        command=['sudo','-n','/root/muxmender-research-access'],roots=[remote],kind='tracked')]))
    observer=None
    try:
        while True:
            predecessor=json.loads((args.after_job/'job.json').read_text())
            if predecessor.get('state')!='running':
                if predecessor.get('state')!='completed':
                    raise ValueError('Preceding qualification did not complete; inspect it before further GPU work')
                break
            job.save(phase='Waiting for the complete HEVC comparison',detail='Serial research avoids contaminating CPU/GPU timings. No production work or media changes.')
            time.sleep(20)
        observer=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),
            '--config',str(config),'--output',str(jobroot),'--interval','10'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        job.save(phase='Testing shared-engine dispatch and complete frame validation')
        result=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
            'sudo -n /root/muxmender-research-access'],input=payload,text=True,capture_output=True,timeout=600)
        (job.directory/'research.log').write_text(result.stdout+result.stderr)
        rows=[line.split('=',1)[1] for line in result.stdout.splitlines() if line.startswith('RESEARCH_RESULT=')]
        if not rows:raise ValueError('Shared integration did not return evidence: '+result.stderr[-1500:])
        report=json.loads(rows[0])
        passed=result.returncode==0 and report.get('shared_engine_passed') is True
        job.save(state='completed' if passed else 'failed',phase='Shared reader integration passed' if passed else 'Shared reader integration needs investigation',detail=json.dumps(report),finished=time.time())
        return 0 if passed else 1
    except BaseException as exc:
        job.save(state='failed',phase='Shared integration unavailable',error=str(exc),finished=time.time())
        raise
    finally:
        if observer:
            try:observer.wait(timeout=20)
            except subprocess.TimeoutExpired:observer.terminate();observer.wait(timeout=5)


if __name__=='__main__':raise SystemExit(main())
