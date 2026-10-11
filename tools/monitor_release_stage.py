"""Read-only SSH observer for an admin-launched, isolated release build."""
import argparse
import json
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from job_tracking import Job


def read_command(version, public_candidate=False, public_materials=False, candidate_revision='r1'):
    if not re.fullmatch(r'\d{8}-v\d+',version):raise ValueError('Invalid release version')
    if candidate_revision not in ('r1','r2'):raise ValueError('Invalid candidate revision')
    stage='/mnt/FR4G/Apps/muxmender/public-image-20261011-'+candidate_revision if public_candidate else '/mnt/FR4G/Apps/muxmender/release-stage-'+version
    unit='muxmender-public-build-20261011-'+candidate_revision if public_candidate else 'muxmender-build-'+version
    if public_materials:
        stage='/mnt/FR4G/Apps/muxmender/public-materials-20261011-r1'
        unit='muxmender-public-materials-20261011-r1'
    progress=''
    if public_materials:
        # Fixed-stage read-only glob: select the most recently started run.
        progress=(f' latest=$(ls -td {stage}/work-* 2>/dev/null | head -n 1); '
                  'if [ -f "$latest/materials/collection-status.json" ]; then '
                  'printf "source_progress="; cat "$latest/materials/collection-status.json"; printf "\\n"; fi; ')
    return (f'if [ -f {stage}/result.txt ]; then cat {stage}/result.txt; '
            'else printf "status=awaiting-admin\\n"; fi; '
            +progress+
            f'printf "unit="; systemctl is-active {unit} || true')


def interpret(text,expected_checksum=None):
    record=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    if expected_checksum and record.get('status')!='awaiting-admin' and record.get('archive_sha256')!=expected_checksum:
        return dict(state='pending',phase='Waiting for revised package build',detail='Previous build status belongs to another package; no current-image qualification claimed'),False
    status=record.get('status')
    if status=='passed':return dict(state='completed',phase='Image smoke tests passed',finished=time.time(),detail='Separate image built; production app and queue unchanged'),True
    if status=='failed':return dict(state='failed',phase='Image build or smoke check failed',finished=time.time(),detail='Exit code: '+record.get('exit_code','unknown')),True
    if status in ('building','running'):
        active=record.get('unit') in ('active','activating')
        values=dict(state='running' if active else 'failed',phase=record.get('phase','Building image'),
                    detail='Read-only TrueNAS build observer' if active else 'Build unit is not active; last status is unconfirmed')
        if active and record.get('phase')=='Collecting exact Ubuntu sources and license notices' and record.get('source_progress'):
            try:
                progress=json.loads(record['source_progress'])
                done,total=progress['completed'],progress['total']
                if type(done) is int and type(total) is int and 0<=done<=total and total>0:
                    values.update(progress_kind='structured',stage_percent=100*done/total,stage_updated=progress.get('updated'),
                                  detail=f'{done} of {total} Ubuntu source packages checked; completeness still needs review')
            except (ValueError,TypeError,KeyError):
                pass  # A concurrent/partial progress write cannot fail the observer.
        return values,not active
    if status=='awaiting-admin':return dict(state='pending',phase='Waiting for admin build command',detail='No Docker image qualification has run yet'),False
    raise ValueError('Unrecognized build status')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--version',required=True)
    parser.add_argument('--host',required=True)
    parser.add_argument('--key',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--checksum',help='Bind progress to the exact staged archive')
    parser.add_argument('--public-candidate', action='store_true', help='Observe the separate clean-base research candidate')
    parser.add_argument('--public-materials', action='store_true', help='Observe installation checks and source collection')
    parser.add_argument('--candidate-revision', choices=('r1','r2'), default='r1')
    args=parser.parse_args();command=read_command(args.version,args.public_candidate,args.public_materials,args.candidate_revision)
    job=Job(args.output,'Public installation and source materials' if args.public_materials else ('Public clean-base candidate '+args.candidate_revision if args.public_candidate else args.version)+' image build and smoke tests')
    job.save(state='pending',phase='Waiting for admin build command',detail='Sources and production queue are not mounted into image tests')
    while True:
        try:
            result=subprocess.run(['ssh','-i',args.key,'-o','BatchMode=yes','-o','ConnectTimeout=5',args.host,command],
                capture_output=True,text=True,timeout=15)
            if result.returncode:raise RuntimeError('Build status connection unavailable')
            status,terminal=interpret(result.stdout,args.checksum)
            if args.public_materials and status.get('state')=='completed':
                status.update(phase='Installation checks and source collection finished',
                              detail='Separate generated-media checks; source inventory still requires review. Nothing published or deployed.')
            job.save(**status)
            if terminal:break
        except Exception as exc:
            job.save(phase='Build status unavailable',detail=str(exc),stage_updated=None)
        time.sleep(10)


if __name__=='__main__':main()
