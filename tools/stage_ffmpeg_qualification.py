"""Stage an isolated stable FFmpeg test, without building or changing the app."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'python')]
from stage_reader_integration import write_context
from job_tracking import Job


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--headers',type=Path,required=True)
    args=parser.parse_args()
    for path,expected in [(args.source,'8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e'),
                          (args.headers,'86d15d1a7c0ac73a0eafdfc57bebfeba7da8264595bf531cf4d8db1c22940116')]:
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Pinned qualification source mismatch')
    destination=Path('E:/MuxMender-TestOutputs/ffmpeg-upgrade-native-20261010-r1')
    remote='/mnt/FR4G/Apps/muxmender/output/'+destination.name
    host='muxmender@192.168.1.232';key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519'
    jobroot=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    job=Job(jobroot,'Stable FFmpeg 9.0.2 qualification — staging')
    try:
        destination.mkdir(exist_ok=False)
        files={'python/'+p.relative_to(ROOT/'python').as_posix():p for p in (ROOT/'python').rglob('*.py')}
        files.update({'tools/qualify_ffmpeg_upgrade.py':ROOT/'tools/qualify_ffmpeg_upgrade.py',
                      'Dockerfile.ffmpeg-qualification':ROOT/'deploy/truenas/Dockerfile.ffmpeg-qualification',
                      'launch-ffmpeg-qualification.sh':ROOT/'deploy/truenas/launch-ffmpeg-qualification.sh',
                      'source/ffmpeg-9.0.2.tar.xz':args.source,
                      'source/nv-codec-headers-n13.0.19.0.tar.gz':args.headers})
        archive=destination/'qualification.tar'
        write_context(archive,files)
        subprocess.run(['ssh','-i',key,'-o','BatchMode=yes',host,'mkdir -- '+remote],check=True)
        subprocess.run(['scp','-i',key,'-o','BatchMode=yes',str(archive),host+':'+remote+'/qualification.tar'],check=True)
        expected=hashlib.sha256(archive.read_bytes()).hexdigest()
        command='cd '+remote+' && echo '+expected+'"  qualification.tar" | sha256sum -c - && tar -xf qualification.tar && sha256sum -c context.sha256'
        subprocess.run(['ssh','-i',key,'-o','BatchMode=yes',host,command],check=True,stdout=subprocess.DEVNULL)
        config=jobroot/'ffmpeg-upgrade-native-r1-monitor.json'
        config.write_text(json.dumps([dict(id='ffmpeg-upgrade-native-r1',title='Stable FFmpeg 9.0.2 / NVENC 13.0 qualification',
            host=host,key=key,command=['sudo','-n','/root/muxmender-research-access'],
            roots=['/output/'+destination.name+'/work/results'],kind='tracked',cross_namespace=True,pending_launch=True)]))
        subprocess.run([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),'--config',str(config),
                        '--output',str(jobroot),'--once'],check=True)
        job.save(state='completed',finished=time.time(),phase='Administrator launch required',
                 detail='Stable source pinned; driver and production dependencies unchanged')
        print('sudo bash '+remote+'/launch-ffmpeg-qualification.sh')
    except BaseException as exc:
        job.save(state='failed',finished=time.time(),error=str(exc));raise


if __name__=='__main__':raise SystemExit(main())
