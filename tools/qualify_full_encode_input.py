"""Linux-only full-file A/B research through the shared automatic workflow."""
import argparse
import json
from pathlib import Path
import sys
import time


def full_encode_label(label):
    return 'full-encode' if label=='research-full-encode' else label


def idle_guard(path):
    state=json.loads(path.read_text())
    age=time.time()-state.get('updated',0)
    if (state.get('ready') is not True or not 0<=age<=12
            or any(state.get('counts',{}).get(k,0) for k in ('pending','running'))):
        raise RuntimeError('Fresh production-idle proof unavailable; research stopped')


def main():
    if sys.platform!='linux':raise RuntimeError('Full media research runs only on Linux')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--controls-status',type=Path,required=True)
    args=parser.parse_args()
    from full_conversion_research import require_read_only
    require_read_only(args.source)
    idle_guard(args.controls_status)
    args.output.mkdir(parents=True,exist_ok=False)
    import auto_optimize
    from job_tracking import Job,isolated_progress
    from task_progress import digest
    original=auto_optimize.Workflow
    job=Job(args.output/'reports','Full-video CPU versus GPU decode qualification')
    report=dict(publication_authorized=False,quality_thresholds_unchanged=True,modes={})
    class GuardedWorkflow(original):
        def __init__(self,options,directory,guard):
            def combined():
                idle_guard(args.controls_status)
                guard()
            super().__init__(options,directory,combined)
        def encode_preserving_color(self,source,output,settings,info,before,label,duration):
            # Exercise the production full-encode route, including its narrowly
            # qualified copied-audio recovery; never suppress validation errors.
            label=full_encode_label(label)
            return super().encode_preserving_color(source,output,settings,info,before,label,duration)
    auto_optimize.Workflow=GuardedWorkflow
    try:
        report['source_sha256']=digest(args.source,lambda:idle_guard(args.controls_status))
        report['source_bytes']=args.source.stat().st_size
        for mode in ('cpu','cuda'):
            root=args.output/mode
            argv=[str(args.source),'--output-dir',str(root),'--execute','--encode-best',
                  '--hardware','nvidia','--playback-verified-codecs','av1',
                  '--research-full-av1-cq','25','--quality-profile','balanced',
                  '--vmaf-mean','94','--vmaf-p5','90','--minimum-savings-percent','25',
                  '--savings-mode','size-aware','--timeout','7200','--min-free-gib','12']
            if mode=='cuda':argv+=['--research-gpu-encode-input']
            start=time.monotonic()
            with isolated_progress(lambda values:job.save(**values)):
                rc=auto_optimize.main(argv)
            records=list(root.glob('auto-*/status.json'))
            if len(records)!=1:raise RuntimeError(mode+' did not produce one full-file result')
            state=json.loads(records[0].read_text())
            report['modes'][mode]=dict(seconds=time.monotonic()-start,exit_code=rc,
                state=state.get('state'),preservation_pass=state.get('preservation_pass'),
                quality=state.get('full_quality'),output_bytes=state.get('output_bytes'),
                source_sha256=state.get('source_sha256'),output_sha256=state.get('output_sha256'),
                all_checks_passed=state.get('all_checks_passed'))
            (args.output/'result.json').write_text(json.dumps(report,indent=2))
            if rc or state.get('state')!='research-completed-not-approved':
                raise RuntimeError(mode+' full qualification did not finish')
        report['source_unchanged']=digest(args.source,lambda:idle_guard(args.controls_status))==report['source_sha256']
        if not report['source_unchanged']:raise RuntimeError('Source changed')
        report['total_speed_ratio']=report['modes']['cpu']['seconds']/report['modes']['cuda']['seconds']
    except BaseException as exc:
        report['error']=str(exc)
    finally:
        auto_optimize.Workflow=original
        (args.output/'result.json').write_text(json.dumps(report,indent=2))
        job.save(state='failed' if 'error' in report else 'completed',finished=time.time(),
                 phase='Full-file comparison stopped' if 'error' in report else 'Full-file comparison complete',
                 detail=json.dumps(report))
    return int('error' in report)


if __name__=='__main__':raise SystemExit(main())
