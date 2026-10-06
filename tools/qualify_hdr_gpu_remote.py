"""Launch isolated generated HDR research with a live read-only dashboard observer."""
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
    parser.add_argument('--queue-request',help='Private runtime locator; source is read-only')
    parser.add_argument('--real-source-request',help='Private registered source for a full real HEVC pair instead of inventory')
    parser.add_argument('--native',action='store_true',help='Qualify isolated native CUDA JSON reader')
    parser.add_argument('--wait-build',action='store_true',help='Observe the administrator build before qualifying')
    parser.add_argument('--full-native',action='store_true',help='Include isolated whole-file GPU EOF inspection')
    parser.add_argument('--av1-native',action='store_true',help='Probe strict AV1 decoding with a generated control')
    parser.add_argument('--av1-performance',action='store_true',help='Include generated 4K AV1 CPU/GPU timings')
    parser.add_argument('--av1-real',action='store_true',help='Find and qualify a read-only real AV1 source')
    parser.add_argument('--hevc-real',action='store_true',help='Find a shorter read-only HEVC source for complete paired qualification')
    parser.add_argument('--native-r3',action='store_true',help='Use the AV1-capable r3 build for HEVC controls')
    parser.add_argument('--after-job',type=Path,help='Wait for a tracked research job to complete before using the GPU')
    parser.add_argument('--reader-timeout',type=int,default=5400,help='Research-only real AV1 whole-file reader limit in seconds')
    args=parser.parse_args()
    if args.real_source_request and not args.hevc_real:parser.error('--real-source-request requires --hevc-real')
    if args.hevc_real:
        if args.av1_real or args.av1_native or args.queue_request:parser.error('HEVC real inventory must be isolated')
        args.native=True
    if args.reader_timeout<=0:parser.error('--reader-timeout must be positive')
    if args.av1_real:
        if args.av1_native or args.queue_request:parser.error('Real AV1 inventory cannot be combined with generated controls or queue locators')
        args.native=True
    if args.av1_performance and not args.av1_native:parser.error('--av1-performance requires --av1-native')
    if args.av1_native:
        if args.queue_request or args.full_native:parser.error('AV1 control uses generated media only')
        args.native=True
    if args.native and not (args.av1_native or args.av1_real or args.hevc_real) and not args.queue_request:parser.error('--native requires --queue-request')
    if args.full_native and not args.native:parser.error('--full-native requires --native')
    jobroot=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    job=Job(jobroot,('Native GPU HDR reader · whole-file inspection' if args.full_native else 'Native GPU HDR reader · exact metadata qualification') if args.native else 'HDR GPU inspection · isolated RTX 5050 benchmark')
    if args.av1_native:job.save(title='AV1 GPU reader · 4K performance qualification' if args.av1_performance else 'AV1 GPU reader · clean-decode control')
    if args.av1_real:job.save(title='Real AV1 GPU reader · full-file qualification' if args.full_native else 'Real AV1 GPU reader · excerpt qualification')
    if args.hevc_real:job.save(title='Real HEVC GPU reader · full-file qualification' if args.full_native else 'Real HEVC GPU reader · excerpt qualification')
    if args.after_job:
        try:
            while True:
                prior=json.loads((args.after_job/'job.json').read_text())
                if prior.get('state')!='running':
                    if prior.get('state')!='completed':raise ValueError('Preceding research did not complete; further GPU tests were not started')
                    break
                job.save(phase='Waiting for preceding serial research',detail='No GPU work started; preserving isolated measurements')
                time.sleep(20)
        except BaseException as exc:
            job.save(state='failed',phase='Research dependency unavailable',error=str(exc),finished=time.time())
            raise
    remote='/work/hdr-gpu-reader-'+uuid.uuid4().hex
    key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519';host='muxmender@192.168.1.232'
    revision='r3' if args.av1_native or args.av1_real or args.hevc_real or args.native_r3 else 'r2'
    binary='/output/hdr-gpu-reader-build-20261002-'+revision+'/binary-'+revision+'/bin/ffprobe-cuda'
    if args.wait_build:
        if not args.native:parser.error('--wait-build requires --native')
        try:
            deadline=time.monotonic()+900
            while True:
                job.save(phase='Waiting for isolated reader build',detail='Observing administrator build; production unchanged')
                check=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
                    'systemctl show muxmender-hdr-gpu-reader-build-'+revision+' -p ActiveState -p SubState -p Result; '
                    'test -x /mnt/FR4G/Apps/muxmender'+binary+' && echo BINARY_READY'],
                    text=True,capture_output=True,timeout=20)
                if 'BINARY_READY' in check.stdout:break
                if 'ActiveState=failed' in check.stdout or 'ActiveState=inactive' in check.stdout:
                    raise RuntimeError('Build ended without a reader: '+check.stdout+check.stderr)
                if time.monotonic()>=deadline:raise TimeoutError('Build observation timed out; build was not stopped')
                time.sleep(10)
        except BaseException as exc:
            job.save(state='failed',phase='Research build needs investigation',error=str(exc),finished=time.time());raise
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in (ROOT/'python').rglob('*.py'):
            z.write(path,'python/'+path.relative_to(ROOT/'python').as_posix())
        z.write(ROOT/'tools/benchmark_hdr_gpu_reader.py','benchmark_hdr_gpu_reader.py')
        z.write(ROOT/'tools/benchmark_native_hdr_reader.py','benchmark_native_hdr_reader.py')
        z.write(ROOT/'tools/benchmark_native_av1_reader.py','benchmark_native_av1_reader.py')
        z.write(ROOT/'tools/benchmark_real_av1_reader.py','benchmark_real_av1_reader.py')
    payload='''import base64,io,zipfile,pathlib,sys,json
root=pathlib.Path(REMOTE);root.mkdir(exist_ok=False)
archive=zipfile.ZipFile(io.BytesIO(base64.b64decode(ARCHIVE)))
for name in archive.namelist():
 p=pathlib.PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive')
archive.extractall(root)
sys.path[:0]=[str(root/'python'),str(root)]
from benchmark_hdr_gpu_reader import main
sys.argv=['benchmark','--output',str(root/'qualification'),'--size','3840x2160','--seconds','3']
code=main()
print('RESEARCH_RESULT='+ (root/'qualification/benchmark.json').read_text().replace('\\n',' '),flush=True)
sys.exit(code)
'''.replace('REMOTE',repr(remote)).replace('ARCHIVE',repr(base64.b64encode(archive.getvalue()).decode()))
    if args.queue_request:
        setup="s=json.loads(pathlib.Path('/output/ui-requests/requests.json').read_text());source=next(j['source'] for j in s['jobs'] if j['id']=="+repr(args.queue_request)+")\n"
        payload=payload.replace("code=main()",setup+"sys.argv+=['--source',source,'--seconds','10','--rounds','1']\ncode=main()")
    if args.native:
        payload=payload.replace('from benchmark_hdr_gpu_reader import main','from '+('benchmark_real_av1_reader' if args.av1_real or args.hevc_real else 'benchmark_native_av1_reader' if args.av1_native else 'benchmark_native_hdr_reader')+' import main')
        payload=payload.replace("'--size','3840x2160','--seconds','3'", "'--binary',"+repr(binary))
        payload=payload.replace("'--seconds','10','--rounds','1'", "'--start','600','--packets','240','--rounds','3'")
        if args.full_native:payload=payload.replace('code=main()',"sys.argv+=['--full']\ncode=main()")
        if args.av1_real or args.hevc_real:payload=payload.replace('code=main()',"sys.argv+=['--reader-timeout',"+repr(str(args.reader_timeout))+"]\ncode=main()")
        if args.hevc_real:payload=payload.replace('code=main()',"sys.argv+=['--codec','hevc','--prefer-short']\ncode=main()")
        if args.real_source_request:
            setup="s=json.loads(pathlib.Path('/output/ui-requests/requests.json').read_text());source=next(j['source'] for j in s['jobs'] if j['id']=="+repr(args.real_source_request)+")\n"
            payload=payload.replace('code=main()',setup+"sys.argv+=['--source',source]\ncode=main()")
        if args.av1_performance:payload=payload.replace('code=main()',"sys.argv+=['--performance']\ncode=main()")
    payload=payload.replace('code=main()', 'try:\n code=main()\nexcept Exception as exc:\n print(str(exc),file=sys.stderr)\n code=1')
    config=job.directory/'monitor-config.json'
    config.write_text(json.dumps([dict(id=remote,title='Live HEVC GPU inspection research' if args.hevc_real else 'Live AV1 GPU inspection research' if args.av1_native or args.av1_real else 'Live HDR GPU reader research',host=host,key=key,
        command=['sudo','-n','/root/muxmender-research-access'],roots=[remote],kind='tracked')]))
    observer=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),
        '--config',str(config),'--output',str(jobroot),'--interval','10'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        job.save(phase='Benchmarking native HDR CPU/CUDA readers',detail='Read-only metadata and generated error-handling tests; production unchanged')
        command=['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
            'sudo -n /root/muxmender-research-access']
        process=subprocess.Popen(command,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        deadline=time.monotonic()+(2*args.reader_timeout+600 if (args.av1_real or args.hevc_real) and args.full_native else 2400 if args.full_native else 650)
        sent=False
        try:
            while True:
                try:
                    stdout,stderr=process.communicate(input=None if sent else payload,timeout=20)
                    result=subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
                    break
                except subprocess.TimeoutExpired:
                    sent=True
                    job.save(phase='Remote HDR qualification running',detail='Live reader observer shows the current stage. Production unchanged; no source replacement.')
                    if time.monotonic()>=deadline:raise
        except BaseException:
            process.kill();process.communicate();raise
        (job.directory/'research.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        if 'RESEARCH_RESULT=' not in result.stdout:raise RuntimeError(result.stderr[-2000:]+'\n'+result.stdout[-3000:])
        report=json.loads(next(x.split('=',1)[1] for x in result.stdout.splitlines() if x.startswith('RESEARCH_RESULT=')))
        job.save(state='failed' if result.returncode else 'completed',phase='GPU reader qualification needs investigation' if result.returncode else ('Real HEVC reader qualification passed' if args.hevc_real else 'Real AV1 reader qualification passed' if args.av1_real else 'AV1 generated controls passed' if args.av1_native else 'HDR benchmark passed'),detail=json.dumps(report),finished=time.time())
        print(json.dumps(report),flush=True)
    except BaseException as exc:
        job.save(state='failed',phase='HDR benchmark needs investigation',error=str(exc),finished=time.time());raise
    finally:
        try:observer.wait(timeout=20)
        except subprocess.TimeoutExpired:observer.terminate();observer.wait(timeout=5)


if __name__=='__main__':main()
