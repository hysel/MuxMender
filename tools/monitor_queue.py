"""Read-only configurable queue observer. Records changes; never controls jobs or media."""
import argparse
import json
from pathlib import Path
import time
import os
import urllib.request
from collections import Counter


def snapshot(url):
    with urllib.request.urlopen(url.rstrip('/')+'/api/controls',timeout=20) as response:
        raw=json.load(response)
    jobs=raw.get('jobs')
    if not isinstance(jobs,list):raise ValueError('API did not return a job list')
    # Explicit allowlist: never store csrf_token, passwords or raw API config.
    fields=('id','source','state','reason','finished','started','execution_version','batch_id')
    return dict(version=raw.get('app_version'),paused=raw.get('paused'),
                jobs=[{key:job[key] for key in fields if key in job} for job in jobs])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--interval',type=int,default=900)
    parser.add_argument('--keep-alive',action='store_true',help='Continue observing an empty queue')
    parser.add_argument('--max-checks',type=int,default=0,help='Stop after this many checks; zero is unlimited')
    args=parser.parse_args()
    if args.interval<60:parser.error('Interval must be at least 60 seconds')
    if args.max_checks<0:parser.error('Maximum checks cannot be negative')
    args.output_dir.mkdir(parents=True,exist_ok=False)
    previous={};first=True;checks=0
    while True:
        started=time.monotonic()
        try:
            state=snapshot(args.url)
            jobs={job['id']:job for job in state['jobs']}
            changes=[] if first else [job for key,job in jobs.items() if previous.get(key)!=job]
            counts=dict(Counter(job['state'] for job in jobs.values()))
            event=dict(checked=time.time(),version=state['version'],paused=state['paused'],
                       counts=counts,changes=changes,
                       active=[job for job in jobs.values() if job['state']=='running'])
            finished=counts.get('pending',0)+counts.get('running',0)==0
            event['queue_finished']=finished
            (args.output_dir/'latest.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
            previous=jobs;first=False
        except Exception as exc:
            event=dict(checked=time.time(),error=str(exc),queue_finished=False)
            finished=False
        with (args.output_dir/'events.jsonl').open('a',encoding='utf-8') as log:
            log.write(json.dumps(event)+'\n')
        print(json.dumps(event),flush=True)
        checks+=1
        done=(finished and not args.keep_alive) or (args.max_checks and checks>=args.max_checks)
        (args.output_dir/'monitor.json').write_text(json.dumps(dict(pid=os.getpid(),interval=args.interval,
            checks=checks,max_checks=args.max_checks,state='finished' if done else 'watching',
            last_check=event['checked'],next_check=None if done else time.time()+args.interval,
            automatic_code_fixes=False),indent=2),encoding='utf-8')
        if done:return
        time.sleep(max(0,args.interval-(time.monotonic()-started)))


if __name__=='__main__':main()
