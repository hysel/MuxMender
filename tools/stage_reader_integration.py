"""Stage an isolated reader image test; never build or change the app here."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'python'),str(ROOT/'tools')]
from build_app_release import inspect_gpu_reader_bundle
from job_tracking import Job


def context_files(bundle):
    files={}
    for path in (ROOT/'python').rglob('*.py'):
        if path.is_symlink():raise ValueError('Linked source module')
        files['python/'+path.relative_to(ROOT/'python').as_posix()]=path
    files['tools/benchmark_shared_gpu_reader.py']=ROOT/'tools/benchmark_shared_gpu_reader.py'
    files['Dockerfile.reader-integration']=ROOT/'deploy/truenas/Dockerfile.reader-integration'
    files['launch-reader-integration.sh']=ROOT/'deploy/truenas/launch-reader-integration.sh'
    for name,path in inspect_gpu_reader_bundle(bundle).items():
        files['qualified-reader/'+name.removeprefix('vendor/gpu-reader/')]=path
    return files


def write_context(archive,files,extra=None):
    checks=[]
    with tarfile.open(archive,'x') as output:
        payloads={name:path.read_bytes() for name,path in files.items() if not path.is_symlink()}
        if len(payloads)!=len(files):raise ValueError('Linked context input')
        payloads.update(extra or {})
        for name,data in sorted(payloads.items()):
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('Unsafe context path')
            if name.endswith(('.py','.sh')) or name.startswith('Dockerfile'):
                data=data.replace(b'\r\n',b'\n')
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.uid=info.gid=0
            output.addfile(info,io.BytesIO(data))
            checks.append(hashlib.sha256(data).hexdigest()+'  '+name)
        data=('\n'.join(checks)+'\n').encode()
        info=tarfile.TarInfo('context.sha256');info.size=len(data);info.mode=0o644
        output.addfile(info,io.BytesIO(data))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--dependency-config',type=Path,required=True)
    args=parser.parse_args()
    if args.destination.name not in ('reader-image-qualification-20261002-r3','reader-image-qualification-20261002-r4','reader-image-qualification-20261002-r5','reader-image-qualification-20261003-r6','reader-image-qualification-20261003-r7'):
        parser.error('Use the dedicated isolated qualification destination')
    jobroot=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    job=Job(jobroot,'Installed reader image qualification · staging only')
    try:
        args.destination.mkdir(parents=True,exist_ok=False)
        archive=args.destination/'reader-integration.tar'
        entries=json.loads(args.dependency_config.read_text())
        if len(entries)!=1 or len(entries[0].get('roots',[]))!=1:raise ValueError('Expected one active research dependency')
        dependency=json.dumps(dict(research_root=entries[0]['roots'][0])).encode()
        write_context(archive,context_files(args.bundle),{'research-dependency.json':dependency})
        remote='/mnt/FR4G/Apps/muxmender/output/'+args.destination.name
        host='muxmender@192.168.1.232';key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519'
        job.save(phase='Uploading immutable isolated test context',detail='No image build, media mounts or production changes')
        created=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
            'mkdir -- '+remote],text=True,capture_output=True,timeout=15)
        if created.returncode:raise RuntimeError('Remote stage already exists or is unavailable: '+created.stderr[-1000:])
        copied=subprocess.run(['scp','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',str(archive),host+':'+remote+'/reader-integration.tar'],
                              text=True,capture_output=True,timeout=60)
        if copied.returncode:raise RuntimeError('Context transport failed: '+copied.stderr[-1000:])
        expected=hashlib.sha256(archive.read_bytes()).hexdigest()
        command='cd '+remote+' && echo '+expected+'"  reader-integration.tar" | sha256sum -c - && tar -xf reader-integration.tar && sha256sum -c context.sha256'
        result=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,command],text=True,capture_output=True,timeout=30)
        if result.returncode:raise RuntimeError('Context verification failed: '+result.stderr[-1000:])
        config=job.directory/'monitor-config.json'
        config.write_text(json.dumps([dict(id=remote,title='Live installed reader image qualification',host=host,key=key,
            command=['sudo','-n','/root/muxmender-research-access'],roots=['/output/'+args.destination.name+'/work'],kind='tracked',pending_launch=True)]))
        observer=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),
            '--config',str(config),'--output',str(jobroot),'--interval','10'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        job.save(state='completed',phase='Isolated image test staged; administrator launch required',
            detail=json.dumps(dict(stage=remote,observer_pid=observer.pid,production_enabled=False,
                command='sudo bash '+remote+'/launch-reader-integration.sh',
                prerequisite='Wait until the HDR10+ comparison has completed; keep the production queue paused')),finished=time.time())
        print('Isolated image qualification staged; wait for serial research before administrator launch.')
        return 0
    except BaseException as exc:
        job.save(state='failed',phase='Image qualification stage incomplete',error=str(exc),finished=time.time())
        raise


if __name__=='__main__':raise SystemExit(main())
