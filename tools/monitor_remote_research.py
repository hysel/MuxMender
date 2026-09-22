"""Mirror read-only remote research progress into the local job dashboard."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import os
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from job_tracking import Job


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
  try:outcomes.append(json.loads(p.read_text()).get('state'))
  except (OSError,ValueError):pass
 for p in root.rglob('job.json'):
  try:
   j=json.loads(p.read_text())
   if j.get('state')=='running':jobs.append(j)
  except (OSError,ValueError):pass
 active=max(jobs,key=lambda j:j.get('updated',0),default={})
 steps=b.get('steps',[])
 result.append(dict(state=b.get('state'),started=b.get('started'),
  validated=outcomes.count('validated-copy-awaiting-playback'),
  retained=sum(s in ('trials-completed','full-output-rejected-insufficient-savings') for s in outcomes),
  finished=b.get('finished'),updated=b.get('updated'),total=b.get('total',0),
  completed=sum(s.get('state') in ('passed','failed') for s in steps),
  failures=sum(s.get('state')=='failed' for s in steps),current=b.get('current'),
  phase=active.get('phase'),stage_percent=active.get('stage_percent'),
  stage_eta=active.get('stage_eta'),stage_updated=active.get('stage_updated'),
  detail=active.get('detail'),workflow_stage=active.get('workflow_stage')))
print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interval', type=int, default=20)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=True)
    index_path = args.output/'monitor-index.json'
    saved = json.loads(index_path.read_text()) if index_path.exists() else {}
    jobs = []
    for entry in config:
        existing = saved.get(entry['host'])
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
        saved[entry['host']] = str(job.directory)
    index_path.write_text(json.dumps(saved))
    while True:
        # Research plans can grow without restarting the dashboard or observer.
        refreshed={e['host']:e for e in json.loads(args.config.read_text(encoding='utf-8'))}
        terminal = []
        for entry, job in jobs:
            entry=refreshed.get(entry['host'],entry)
            try:
                script = 'ROOTS='+repr(entry['roots'])+'\n'+REMOTE
                command = ['ssh', '-i', entry['key'], '-o', 'IdentitiesOnly=yes',
                           '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes',
                           '-o', 'ConnectTimeout=10', entry['host'], *entry['command']]
                response = subprocess.run(command, input=script, text=True,
                                          capture_output=True, timeout=30, check=True)
                batches = json.loads(response.stdout)
                total = sum(b['total'] for b in batches)
                completed = sum(b['completed'] for b in batches)
                failures = sum(b['failures'] for b in batches)
                validated = sum(b['validated'] for b in batches)
                retained = sum(b['retained'] for b in batches)
                active = next((b for b in batches if b['state'] not in
                               ('completed','completed-with-failures')), None)
                done = active is None
                fresh = done or time.time()-float(active.get('updated') or 0) < 90
                state = ('failed' if failures else 'completed') if done else ('running' if fresh else 'stale')
                phase = 'Research batch finished' if done else (active.get('phase') or 'Remote test '+str(completed+1)+' of '+str(total))
                detail = f'{completed}/{total} commands finished; {validated} validated copies; {retained} size/quality keeps; {failures} command failures. Other completed commands may be unsupported-input skips. Originals retained.'
                if active and active.get('detail'):detail += ' '+str(active['detail'])
                if not fresh:detail += ' Remote heartbeat is stale; current progress is unconfirmed.'
                stage_fresh = active and time.time()-float(active.get('stage_updated') or 0) < 60
                job.save(state=state, started=min(b['started'] for b in batches),
                    finished=max((b.get('finished') or 0 for b in batches)) if done else None,
                    phase=phase, progress_kind='structured', completed=completed, total=total,
                    unit='tests', percent=100*completed/total if total else None,
                    stage_percent=active.get('stage_percent') if stage_fresh else None,
                    stage_eta=active.get('stage_eta') if stage_fresh else None,
                    workflow_stage=active.get('workflow_stage') if active else None,
                    detail=detail, monitor_scope='Read-only remote status mirror; PID identifies the local observer')
                terminal.append(done)
            except Exception as exc:
                job.save(state='stale', phase='Remote status unavailable', stage_percent=None,
                         stage_eta=None, detail=type(exc).__name__+': connection or status read failed; retrying')
                terminal.append(False)
        if all(terminal):break
        time.sleep(max(5,args.interval))


if __name__ == '__main__':
    main()
