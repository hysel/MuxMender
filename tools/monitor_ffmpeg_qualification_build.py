"""Read-only SSH build observer. Runs no media or Linux signal code locally."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from job_tracking import Job


def parse_properties(text):
    return dict(line.split('=',1) for line in text.splitlines() if '=' in line)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--unit',required=True)
    parser.add_argument('--results',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'muxmender-[a-z0-9-]+',args.unit):raise ValueError('Unsafe unit name')
    if not re.fullmatch(r'/mnt/FR4G/Apps/muxmender/output/[a-z0-9-]+/work/results',args.results):
        raise ValueError('Unsafe isolated results path')
    job=Job(args.output,'FFmpeg 9 qualification — isolated image build')
    ssh=['ssh','-i','C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519',
         '-o','BatchMode=yes','-o','ConnectTimeout=5','muxmender@192.168.1.232']
    def remote(command):
        return subprocess.run(ssh+[command],capture_output=True,text=True,timeout=15)
    deadline=time.monotonic()+3600
    while time.monotonic()<deadline:
        try:
            registered=remote('test -d '+args.results)
            if registered.returncode==0:
                job.save(state='completed',finished=time.time(),phase='Image built; qualification started',
                         detail='Build completion only. Follow the separate runtime test entry; no deployment approval.')
                return 0
            status=remote('systemctl show '+args.unit+
                ' --property=LoadState --property=ActiveState --property=SubState --property=Result --property=ExecMainStatus')
            props=parse_properties(status.stdout)
            if status.returncode or props.get('LoadState')=='not-found':
                job.save(state='stale',phase='Build status unavailable',
                         detail='No test registration or readable service result. Administrator build logs are needed.')
            elif props.get('Result') not in (None,'success'):
                job.save(state='failed',finished=time.time(),phase='Isolated image build failed',
                         detail='Service result: '+props['Result']+'; exit '+props.get('ExecMainStatus','unknown'))
                return 1
            elif props.get('ActiveState')=='active':
                processes=remote('ps -C apt-get -C dpkg -C cc1 -C cc1plus -C ninja -C make -o comm=')
                names=set(processes.stdout.split())
                phase=('Installing test-image dependencies' if names & {'apt-get','dpkg'}
                       else 'Compiling isolated FFmpeg and reader' if names & {'cc1','cc1plus','make','ninja'}
                       else 'Preparing isolated test image')
                job.save(state='running',phase=phase,stage_percent=None,stage_eta=None,
                         detail='Read-only service/process observation. No numeric build progress or ETA is claimed.')
            else:
                job.save(state='stale',phase='Waiting for qualification registration',
                         detail='Service is no longer active; test start has not been verified.')
        except (OSError,subprocess.TimeoutExpired) as exc:
            job.save(state='stale',phase='Build observation unavailable',detail=type(exc).__name__)
        time.sleep(20)
    job.save(state='stale',phase='Build observation window ended',
             detail='No completion inferred. Build service and test records require another check.')
    return 1


if __name__=='__main__':raise SystemExit(main())
