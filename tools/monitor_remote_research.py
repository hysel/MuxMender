"""Mirror read-only remote research progress into the local job dashboard."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import os
import threading
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from job_tracking import Job


def unavailable_status(entry,data,exc):
    if entry.get('pending_launch') is True and not data.get('remote_registered'):
        return dict(state='queued',phase='Waiting for administrator launch',stage_percent=None,
            stage_eta=None,detail='The isolated test has not reported a start. No test progress is claimed.')
    return dict(state='stale',phase='Remote status unavailable',stage_percent=None,
        stage_eta=None,detail=type(exc).__name__+': connection or status read failed; retrying')


REMOTE = '''
import json,time
from pathlib import Path
result=[]
for root_text in ROOTS:
 root=Path(root_text)
 b=json.loads((root/'batch-status.json').read_text())
 jobs=[]
 outcomes=[]
 for p in root.glob('*/auto-*/status.json'):
  try:outcomes.append(json.loads(p.read_text()))
  except (OSError,ValueError):pass
 for p in root.rglob('job.json'):
  try:
   j=json.loads(p.read_text())
   if j.get('state')=='running':jobs.append(j)
  except (OSError,ValueError):pass
 active=max(jobs,key=lambda j:j.get('updated',0),default={})
 steps=b.get('steps',[])
 result.append(dict(state=b.get('state'),started=b.get('started'),
  validated=sum(s.get('state')=='validated-copy-awaiting-playback' for s in outcomes),
  evaluation_errors=sum(s.get('decision',{}).get('reason_code')=='evaluation_inconclusive' for s in outcomes),
  retained=sum((s.get('state')=='full-output-rejected-insufficient-savings' or (s.get('state')=='trials-completed' and s.get('decision',{}).get('action')=='keep_original')) and s.get('decision',{}).get('reason_code')!='evaluation_inconclusive' for s in outcomes),
  finished=b.get('finished'),updated=b.get('updated'),total=b.get('total',0),
  completed=sum(s.get('state') in ('passed','failed') for s in steps),
  failures=sum(s.get('state')=='failed' for s in steps),current=b.get('current'),
  phase=active.get('phase'),stage_percent=active.get('stage_percent'),
  stage_eta=active.get('stage_eta'),stage_updated=active.get('stage_updated'),
  detail=active.get('detail'),workflow_stage=active.get('workflow_stage'),
  stage_identity=[active.get(k) for k in ('pid','started','phase','stage_started')]))
print(json.dumps(result))
'''

# Direct tracked_call jobs use the same heartbeat and stage records as local
# work. Mirror observer PIDs locally, never remote PIDs from another namespace.
REMOTE_TRACKED = '''
import json,time,os,sys
from pathlib import Path
if sys.platform != 'linux':
 raise RuntimeError('Remote research reader is Linux-only; never execute on Windows')
result=[]
seen=set()
for root_text in ROOTS:
 root=Path(root_text)
 jobs=[]
 outcomes=[]
 for p in root.rglob('job.json'):
  if p.is_symlink():continue
  try:jobs.append((p.resolve(),json.loads(p.read_text())))
  except (OSError,ValueError):pass
 for p in root.rglob('auto-*/status.json'):
  try:outcomes.append(json.loads(p.read_text()))
  except (OSError,ValueError):pass
 if not jobs:raise RuntimeError('Tracked development job has not registered')
 # A nested fixture/child may finish while its parent research job still runs.
 # Prefer the outermost tracked scope, then the latest attempt at that scope.
 depth=min(len(path.relative_to(root.resolve()).parts) for path,j in jobs)
 path,j=max((item for item in jobs if len(item[0].relative_to(root.resolve()).parts)==depth),
            key=lambda x:x[1].get('started',0))
 if path in seen:continue
 seen.add(path)
 state=j.get('state')
 done=state in ('completed','failed','cancelled')
 # Parent controls lifecycle; a current nested worker supplies stage progress.
 # Ignore earlier attempts and completed fixtures when choosing the live stage.
 stage=j
 if not done:
  children=[record for child_path,record in jobs
            if len(child_path.relative_to(root.resolve()).parts)>depth
            and record.get('state')=='running'
            and record.get('started',0)>=j.get('started',0)]
  stage=max(children,key=lambda record:record.get('stage_updated') or record.get('updated') or 0,default=j)
 alive=True
 if not done and not globals().get('CROSS_NAMESPACE'):
  try:
   pid=int(j.get('pid',0))
   if globals().get('SERVICE_UNIT'):
    import subprocess
    pid=int(subprocess.check_output(['systemctl','show',SERVICE_UNIT,'--property=MainPID','--value'],text=True,timeout=10).strip())
   proc=Path('/proc',str(pid))
   alive=pid>0 and proc.is_dir() and (proc/'stat').read_text().rsplit(')',1)[1].split()[0] not in ('Z','X')
  except (OSError,TypeError,ValueError,IndexError):alive=False
 result.append(dict(state=('completed-with-failures' if state!='completed' else 'completed') if done else 'running',
 started=j.get('started'),finished=j.get('finished'),updated=(stage.get('updated') or 0) if alive else 0,
 total=1,completed=int(done),failures=int(done and state!='completed'),
 validated=sum(s.get('state')=='validated-copy-awaiting-playback' for s in outcomes),
 evaluation_errors=sum(s.get('decision',{}).get('reason_code')=='evaluation_inconclusive' for s in outcomes),
 retained=sum((s.get('state')=='full-output-rejected-insufficient-savings' or (s.get('state')=='trials-completed' and s.get('decision',{}).get('action')=='keep_original')) and s.get('decision',{}).get('reason_code')!='evaluation_inconclusive' for s in outcomes),
 current=1,phase=stage.get('phase'),stage_percent=stage.get('stage_percent'),stage_eta=stage.get('stage_eta'),
 stage_updated=stage.get('stage_updated'),detail=stage.get('detail'),workflow_stage=stage.get('workflow_stage'),
 stage_identity=[stage.get(k) for k in ('pid','started','phase','stage_started')]))
if not result:raise RuntimeError('Tracked development job has not registered')
print(json.dumps(result))
'''


def entry_key(entry):
    # Host alone merges independent jobs and can hide a failed run.
    return str(entry.get('id') or (entry['host']+'\n'+entry['title']))


class StageEvidenceClock:
    """Old workers lack stage timestamps: only observed progress changes count.

    A first snapshot, heartbeat or repeated percentage is not new stage evidence.
    Phase/worker changes reset observations; never infer completion from 100%.
    """
    def __init__(self):
        self.identity=None
        self.percent=None
        self.observed=None

    def timestamp(self, active, now):
        if not active:
            self.identity=self.percent=self.observed=None
            return None
        percent=active.get('stage_percent')
        if type(percent) not in (int,float) or not math.isfinite(percent) or not 0<=percent<=100:
            self.identity=self.percent=self.observed=None
            return None
        identity=tuple(active.get('stage_identity') or (active.get('started'),active.get('phase')))
        if identity!=self.identity:
            self.identity=identity
            self.percent=percent
            self.observed=None
        elif percent!=self.percent:
            self.percent=percent
            self.observed=now
        stamp=active.get('stage_updated')
        if stamp is not None:
            return stamp if type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<60 else None
        return self.observed if self.observed is not None and 0<=now-self.observed<60 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interval', type=int, default=20)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if len({entry_key(e) for e in config})!=len(config):
        raise ValueError('Research monitor entries require unique identities')
    args.output.mkdir(parents=True, exist_ok=True)
    index_path = args.output/'monitor-index.json'
    saved = json.loads(index_path.read_text()) if index_path.exists() else {}
    jobs = []
    evidence_clocks={}
    for entry in config:
        key=entry_key(entry)
        existing = saved.get(key)
        if not existing and sum(e['host']==entry['host'] for e in config)==1:
            existing=saved.get(entry['host'])
        if existing:
            directory = Path(existing).resolve()
            if not directory.is_relative_to(args.output.resolve()):
                raise ValueError('Saved monitor directory outside output')
            job = Job.__new__(Job)
            job.directory = directory
            job.lock = threading.Lock()
            job.last_timing = time.monotonic()
            job.data = json.loads((directory/'job.json').read_text())
            job.data.update(pid=os.getpid(), title=entry['title'])
        else:
            job = Job(args.output, entry['title'])
        jobs.append((entry, job))
        evidence_clocks[key]=StageEvidenceClock()
        saved[key] = str(job.directory)
    index_path.write_text(json.dumps(saved))
    while True:
        # Research plans can grow without restarting the dashboard or observer.
        refreshed={entry_key(e):e for e in json.loads(args.config.read_text(encoding='utf-8'))}
        terminal = []
        for entry, job in jobs:
            entry=refreshed.get(entry_key(entry),entry)
            try:
                # Container-local PIDs cannot be probed from the observer's
                # container. In that mode only fresh persisted worker evidence
                # establishes liveness; successful SSH alone never does.
                script = 'ROOTS='+repr(entry['roots'])+'\nSERVICE_UNIT='+repr(entry.get('service_unit'))+'\nCROSS_NAMESPACE='+repr(entry.get('cross_namespace') is True)+'\n'+(REMOTE_TRACKED if entry.get('kind')=='tracked' else REMOTE)
                command = ['ssh', '-i', entry['key'], '-o', 'IdentitiesOnly=yes',
                           '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes',
                           '-o', 'ConnectTimeout=10', entry['host'], *entry['command']]
                response = subprocess.run(command, input=script, text=True, encoding='utf-8',
                                          capture_output=True, timeout=30, check=True)
                batches = json.loads(response.stdout)
                if not batches:raise ValueError('No remote research record')
                job.data['remote_registered']=True
                total = sum(b['total'] for b in batches)
                completed = sum(b['completed'] for b in batches)
                failures = sum(b['failures'] for b in batches)
                evaluation_errors = sum(b.get('evaluation_errors',0) for b in batches)
                validated = sum(b['validated'] for b in batches)
                retained = sum(b['retained'] for b in batches)
                active = next((b for b in batches if b['state'] not in
                               ('completed','completed-with-failures')), None)
                done = active is None
                fresh = done or time.time()-float(active.get('updated') or 0) < 90
                state = ('failed' if failures or evaluation_errors else 'completed') if done else ('running' if fresh else 'stale')
                phase = 'Development execution finished — check outcomes' if done else (active.get('phase') or 'Remote test '+str(completed+1)+' of '+str(total))
                detail = f'{completed}/{total} commands finished; {validated} validated test copies (not published); {retained} size/quality keeps; {evaluation_errors} incomplete evaluations; {failures} command failures. Execution completion alone does not mean conversion passed or disk space was reclaimed. Other completed commands may be unsupported-input skips or sample-only tests. Originals retained.'
                if done and evaluation_errors:phase='Evaluation incomplete — investigation required'
                if done and entry.get('completion_note'):
                    detail += ' '+str(entry['completion_note'])
                if active and active.get('detail'):detail += ' '+str(active['detail'])
                if not fresh:detail += ' Remote heartbeat is stale; current progress is unconfirmed.'
                stage_time=evidence_clocks[entry_key(entry)].timestamp(active if fresh else None,time.time())
                stage_fresh=stage_time is not None
                job.save(title=entry['title'],state=state, started=min(b['started'] for b in batches),
                    finished=max((b.get('finished') or 0 for b in batches)) if done else None,
                    phase=phase, progress_kind='structured', completed=completed, total=total,
                    unit='tests', percent=100*completed/total if total else None,
                    stage_percent=active.get('stage_percent') if stage_fresh else None,
                    stage_eta=active.get('stage_eta') if stage_fresh else None,
                    stage_updated=stage_time,
                    workflow_stage=active.get('workflow_stage') if active else None,
                    detail=detail, monitor_scope='Read-only remote status mirror; PID identifies the local observer')
                terminal.append(done)
            except Exception as exc:
                job.save(**unavailable_status(entry,job.data,exc))
                terminal.append(False)
        if all(terminal):break
        time.sleep(max(5,args.interval))


if __name__ == '__main__':
    main()
