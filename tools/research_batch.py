"""Run an explicit isolated research plan with durable status and child reaping."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('plan',type=Path)
    parser.add_argument('--after-status',type=Path,action='append',default=[])
    args=parser.parse_args()
    plan=json.loads(args.plan.read_text())
    root=args.plan.parent
    state=dict(state='running',pid=os.getpid(),started=time.time(),steps=[],total=len(plan))
    def save():
        tmp=root/'batch-status.tmp'
        tmp.write_text(json.dumps(state,indent=2));tmp.replace(root/'batch-status.json')
    save()
    for dependency in args.after_status:
        state.update(state='waiting',dependency=str(dependency));save()
        while True:
            previous=json.loads(dependency.read_text())
            if previous.get('state') in ('completed','completed-with-failures'):break
            state['updated']=time.time();save();time.sleep(5)
        state.update(state='running');state.pop('dependency',None);save()
    for index,item in enumerate(plan):
        step=dict(name=item['name'],state='running',started=time.time())
        state['steps'].append(step);state['current']=index+1;save()
        try:
            with (root/(item['name']+'.log')).open('x') as log:
                child=subprocess.Popen(item['command'],cwd=root,stdin=subprocess.DEVNULL,
                                       stdout=log,stderr=subprocess.STDOUT)
                step['pid']=child.pid;save()
                while child.poll() is None:
                    state['updated']=time.time();save();time.sleep(2)
                step.update(exit_code=child.returncode,state='passed' if child.returncode==0 else 'failed')
        except Exception as exc:
            step.update(state='failed',error=str(exc))
        step['finished']=time.time();save()
    state.update(state='completed' if all(s['state']=='passed' for s in state['steps']) else 'completed-with-failures',finished=time.time())
    save()


if __name__=='__main__':main()
