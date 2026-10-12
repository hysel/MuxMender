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


def read_command(version, public_candidate=False, public_materials=False, candidate_revision='r1',public_scan=False,public_copy=False,public_cancel=False):
    if sum(map(bool,(public_candidate,public_materials,public_scan,public_copy,public_cancel)))>1:
        raise ValueError('Choose one isolated release task')
    if not re.fullmatch(r'\d{8}-v\d+',version):raise ValueError('Invalid release version')
    if candidate_revision not in ('r1','r2'):raise ValueError('Invalid candidate revision')
    stage='/mnt/FR4G/Apps/muxmender/public-image-20261011-'+candidate_revision if public_candidate else '/mnt/FR4G/Apps/muxmender/release-stage-'+version
    unit='muxmender-public-build-20261011-'+candidate_revision if public_candidate else 'muxmender-build-'+version
    if public_materials:
        stage='/mnt/FR4G/Apps/muxmender/public-materials-20261011-r1'
        unit='muxmender-public-materials-20261011-r1'
    if public_scan:
        stage='/mnt/FR4G/Apps/muxmender/public-security-20261011-r1'
        unit='muxmender-public-security-20261011-r1'
    if public_copy:
        stage='/mnt/FR4G/Apps/muxmender/public-copy-lifecycle-20261011-r1'
        unit='muxmender-public-copy-lifecycle-20261011-r1'
    if public_cancel:
        stage='/mnt/FR4G/Apps/muxmender/public-cancellation-20261012-r1'
        unit='muxmender-public-cancellation-20261012-r1'
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


def interpret(text,expected_checksum=None,waiting_phase='Waiting for admin build command'):
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
    if status=='awaiting-admin':return dict(state='pending',phase=waiting_phase,detail='This isolated task has not started; no result claimed'),False
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
    parser.add_argument('--public-scan',action='store_true',help='Observe the isolated candidate software/security scan')
    parser.add_argument('--public-copy',action='store_true',help='Observe generated-media safe-copy lifecycle checks')
    parser.add_argument('--public-cancel',action='store_true',help='Observe generated native-stage cancellation checks')
    args=parser.parse_args();command=read_command(args.version,args.public_candidate,args.public_materials,args.candidate_revision,args.public_scan,args.public_copy,args.public_cancel)
    title=('Public generated cancellation lifecycle' if args.public_cancel else
           'Public generated safe-copy lifecycle' if args.public_copy else
           'Public candidate software and security scan' if args.public_scan else
           'Public installation and source materials' if args.public_materials else
           ('Public clean-base candidate '+args.candidate_revision if args.public_candidate else args.version)+' image build and smoke tests')
    job=Job(args.output,title)
    waiting_phase=('Waiting for administrator to start cancellation checks' if args.public_cancel else
                   'Waiting for administrator to start safe-copy checks' if args.public_copy else
                   'Waiting for administrator to start security scan' if args.public_scan else
                   'Waiting for administrator to collect source materials' if args.public_materials else
                   'Waiting for admin build command')
    job.save(state='pending',phase=waiting_phase,detail='Sources and production queue are not mounted into image tests')
    while True:
        try:
            result=subprocess.run(['ssh','-i',args.key,'-o','BatchMode=yes','-o','ConnectTimeout=5',args.host,command],
                capture_output=True,text=True,timeout=15)
            if result.returncode:raise RuntimeError('Build status connection unavailable')
            status,terminal=interpret(result.stdout,args.checksum,waiting_phase)
            if args.public_materials and status.get('state')=='completed':
                status.update(phase='Installation checks and source collection finished',
                              detail='Separate generated-media checks; source inventory still requires review. Nothing published or deployed.')
            if args.public_scan and status.get('state')=='completed':
                status.update(phase='Security scan completed; findings need review',
                              detail='Scan completion does not mean zero vulnerabilities. No deployment or publication.')
            if args.public_copy and status.get('state')=='completed':
                status.update(phase='Generated safe-copy lifecycle checks passed',
                              detail='Normal quality gates retained; generated sources unchanged. No real-file or public-install certification claimed.')
            if args.public_cancel and status.get('state')=='completed':
                status.update(phase='Generated cancellation lifecycle checks passed',
                              detail='Observed native stage stopped; cancelled history persisted. No publication or production changes.')
            job.save(**status)
            if terminal:break
        except Exception as exc:
            job.save(phase='Build status unavailable',detail=str(exc),stage_updated=None)
        time.sleep(10)


if __name__=='__main__':main()
