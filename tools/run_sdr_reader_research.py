"""Stage generated SDR research through the restricted Linux container.

Refuses to start while production has running/pending jobs. Never starts Docker
or changes the production queue. Native payload executes only over SSH on Linux.
"""
import base64
import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from job_tracking import Job


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codec',choices=('av1','hevc'),default='av1')
    parser.add_argument('--pixel-format',choices=('yuv420p','yuv420p10le'),default='yuv420p10le')
    parser.add_argument('--ffprobe',default='/output/ffmpeg9-runtime-export-20261010-r1/bin/ffprobe')
    parser.add_argument('--research-python-path',default='/work/ffmpeg-comparison-20261010-r5/python',
        help='Existing isolated Linux test dependencies; never installed in production')
    parser.add_argument('--source-plan',help='Existing approved remote job plan for a read-only complete-source comparison')
    parser.add_argument('--workflow',action='store_true',help='Measure generated encoding plus shared validation and quality')
    args=parser.parse_args()
    if args.workflow and args.source_plan:parser.error('Workflow tests use generated fixtures, not library sources')
    with urllib.request.urlopen('http://192.168.1.232:8767/api/controls',timeout=15) as response:
        controls=json.load(response)
    if not controls.get('ready') or not controls.get('paused') or any(controls.get('counts',{}).get(k,0) for k in ('running','pending')):
        raise ValueError('Production must be ready, paused and empty before isolated benchmarking')
    jobroot=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    job=Job(jobroot,('Shared SDR workflow comparison: ' if args.workflow else 'Full-source SDR reader comparison: ' if args.source_plan else 'Generated SDR reader comparison: ')+args.codec+' '+args.pixel_format)
    remote='/work/sdr-reader-'+uuid.uuid4().hex
    key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519';host='muxmender@192.168.1.232'
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in (ROOT/'python').rglob('*.py'):bundle.write(path,'python/'+path.relative_to(ROOT/'python').as_posix())
        for name in ('benchmark_sdr_gpu_reader','benchmark_native_av1_reader','benchmark_native_hdr_reader','benchmark_shared_sdr_reader'):
            bundle.write(ROOT/'tools'/(name+'.py'),'tools/'+name+'.py')
    payload='''import base64,io,json,pathlib,sys,zipfile,subprocess
if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only research')
root=pathlib.Path(REMOTE);root.mkdir(exist_ok=False)
archive=zipfile.ZipFile(io.BytesIO(base64.b64decode(ARCHIVE)))
for name in archive.namelist():
 p=pathlib.PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive')
archive.extractall(root)
sys.path[:0]=[str(root/'python'),str(root/'tools')]
sys.path.append(RESEARCH_PYTHON_PATH)
from BENCHMARK_MODULE import main
sys.argv=['benchmark','--binary','/output/hdr-gpu-reader-build-20261002-r3/binary-r3/bin/ffprobe-cuda','--output',str(root/'qualification')]
sys.argv+=EXTRA_ARGS
code=main()
print('RESEARCH_RESULT='+(root/'qualification/benchmark.json').read_text().replace('\\n',' '),flush=True)
sys.exit(code)
'''.replace('REMOTE',repr(remote)).replace('ARCHIVE',repr(base64.b64encode(archive.getvalue()).decode())).replace('RESEARCH_PYTHON_PATH',repr(args.research_python_path)).replace('BENCHMARK_MODULE','benchmark_shared_sdr_reader' if args.workflow else 'benchmark_sdr_gpu_reader').replace('EXTRA_ARGS',repr(['--codec',args.codec,'--pixel-format',args.pixel_format,'--ffprobe',args.ffprobe]+(['--source-plan',args.source_plan] if args.source_plan else [])))
    config=job.directory/'monitor-config.json'
    config.write_text(json.dumps([dict(id=remote,title='Live SDR reader parity and speed',host=host,key=key,
        command=['sudo','-n','/root/muxmender-research-access'],roots=[remote],kind='tracked')]))
    observer=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),'--config',str(config),
        '--output',str(jobroot),'--interval','10'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        job.save(phase='Running read-only full-source comparison' if args.source_plan else 'Running generated SDR comparison',detail=remote)
        result=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
            'sudo -n /root/muxmender-research-access'],input=payload,text=True,capture_output=True,timeout=21600 if args.source_plan else 1800)
        (job.directory/'research.log').write_text(result.stdout+result.stderr)
        lines=[line.split('=',1)[1] for line in result.stdout.splitlines() if line.startswith('RESEARCH_RESULT=')]
        if not lines:raise RuntimeError('Research result unavailable: '+result.stderr[-1000:])
        report=json.loads(lines[-1]);(job.directory/'benchmark.json').write_text(json.dumps(report,indent=2))
        passed=result.returncode==0 and report.get('controls_passed') is True
        job.save(state='completed' if passed else 'failed',phase='SDR comparison checks passed' if passed else 'SDR qualification needs investigation',detail=json.dumps(report),finished=time.time())
        print(json.dumps(dict(job=str(job.directory),report=report)))
        return 0 if passed else 1
    except BaseException as exc:
        job.save(state='failed',phase='Research observer stopped; inspect remote state before retry',error=str(exc),finished=time.time())
        raise
    finally:
        try:observer.wait(timeout=15)
        except subprocess.TimeoutExpired:observer.terminate();observer.wait(timeout=5)


if __name__=='__main__':raise SystemExit(main())
