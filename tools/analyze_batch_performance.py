"""Read-only, anonymous production timing summary; never schedules media work."""
import argparse
import json
import math
import re
from pathlib import Path
import sys
from urllib.request import urlopen


def positive(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0


def summarize(controls, catalog, batch_id=None):
    requests=controls.get('jobs',[])
    if batch_id is None:
        dated=[row for row in requests if positive(row.get('created')) and row.get('batch_id')]
        if not dated:raise ValueError('No dated batch available')
        batch_id=max(dated,key=lambda row:row['created'])['batch_id']
    selected=[row for row in requests if row.get('batch_id')==batch_id]
    if not selected:raise ValueError('Batch not found')
    ids={row['id'] for row in selected}
    counts={};saved=0;cleaned=0
    for row in selected:
        state=row.get('state','unknown');counts[state]=counts.get(state,0)+1
        if state=='replaced':
            value=row.get('saved_bytes')
            if positive(value):saved+=value
            cleaned+=row.get('artifact_cleanup',{}).get('state')=='cleaned'
    totals={};measured=0;seen=set()
    for job in catalog.get('jobs',[]):
        match=re.search(r'(?:^|/)request-([0-9a-f]{32})/',str(job.get('directory','')).replace('\\','/'))
        identifier=job.get('id')
        if not match or match[1] not in ids or not identifier or identifier in seen:continue
        seen.add(identifier)
        counters=job.get('performance_seconds',{})
        if not isinstance(counters,dict):continue
        valid={key:value for key,value in counters.items()
               if re.fullmatch(r'[a-z_]{1,40}',key) and positive(value)}
        if valid:measured+=1
        for key,value in valid.items():totals[key]=totals.get(key,0)+value
    total=sum(totals.values())
    return dict(batch_id=batch_id,counts=counts,confirmed_saved_gb=saved/1e9,
                cleaned_replacements=cleaned,measured_records=measured,
                observed_stage_seconds=dict(sorted(totals.items(),key=lambda pair:pair[1],reverse=True)),
                stage_share_percent={key:100*value/total for key,value in totals.items()} if total else {},
                scope='Sum of observed task-stage counters, including waits; not batch wall time or CPU utilization. Active counters and API snapshots may lag.',
                snapshot_stale=controls.get('snapshot_stale'),queue_paused=controls.get('paused'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--batch')
    parser.add_argument('--track-root',type=Path,help='Record this read-only analysis on the development dashboard')
    args=parser.parse_args()
    def get(endpoint):
        with urlopen(args.url.rstrip('/')+endpoint,timeout=20) as response:
            return json.load(response)
    job=None
    if args.track_root:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
        from job_tracking import Job
        job=Job(args.track_root,'Production batch performance review')
        job.save(phase='Reading queue and observed stage counters')
    try:
        result=summarize(get('/api/controls'),get('/api/jobs'),args.batch)
        if job:job.save(state='completed',phase='Read-only batch analysis completed',results=result,
                        detail='Stage counters include waits, not whole-batch elapsed time. No media or queue changes.')
        print(json.dumps(result,indent=2))
    except Exception:
        if job:job.save(state='failed',phase='Batch analysis unavailable',detail='No result inferred from missing API data')
        raise


if __name__=='__main__':main()
