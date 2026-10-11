"""Read-only SSH observer for an admin-launched, isolated release build."""
import argparse
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from job_tracking import Job


def read_command(version):
    if not re.fullmatch(r'\d{8}-v\d+',version):raise ValueError('Invalid release version')
    stage='/mnt/FR4G/Apps/muxmender/release-stage-'+version
    return (f'if [ -f {stage}/result.txt ]; then cat {stage}/result.txt; '
            'else printf "status=awaiting-admin\\n"; fi; '
            f'printf "unit="; systemctl is-active muxmender-build-{version} || true')


def interpret(text,expected_checksum=None):
    record=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    if expected_checksum and record.get('archive_sha256')!=expected_checksum:
        return dict(state='pending',phase='Waiting for revised package build',detail='Previous build status belongs to another package; no current-image qualification claimed'),False
    status=record.get('status')
    if status=='passed':return dict(state='completed',phase='Image smoke tests passed',finished=time.time(),detail='Separate image built; production app and queue unchanged'),True
    if status=='failed':return dict(state='failed',phase='Image build or smoke check failed',finished=time.time(),detail='Exit code: '+record.get('exit_code','unknown')),True
    if status in ('building','running'):
        active=record.get('unit') in ('active','activating')
        return dict(state='running' if active else 'failed',phase=record.get('phase','Building image'),
                    detail='Read-only TrueNAS build observer' if active else 'Build unit is not active; last status is unconfirmed'),not active
    if status=='awaiting-admin':return dict(state='pending',phase='Waiting for admin build command',detail='No Docker image qualification has run yet'),False
    raise ValueError('Unrecognized build status')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--version',required=True)
    parser.add_argument('--host',required=True)
    parser.add_argument('--key',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--checksum',help='Bind progress to the exact staged archive')
    args=parser.parse_args();command=read_command(args.version)
    job=Job(args.output,args.version+' image build and smoke tests')
    job.save(state='pending',phase='Waiting for admin build command',detail='Sources and production queue are not mounted into image tests')
    while True:
        try:
            result=subprocess.run(['ssh','-i',args.key,'-o','BatchMode=yes','-o','ConnectTimeout=5',args.host,command],
                capture_output=True,text=True,timeout=15)
            if result.returncode:raise RuntimeError('Build status connection unavailable')
            status,terminal=interpret(result.stdout,args.checksum)
            job.save(**status)
            if terminal:break
        except Exception as exc:
            job.save(phase='Build status unavailable',detail=str(exc),stage_updated=None)
        time.sleep(10)


if __name__=='__main__':main()
