"""Exercise the automatic HDR validator/metric on an existing isolated test pair.

No input is modified. Exclusively creates a new results directory.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from auto_optimize import Workflow
from task_progress import digest
from job_tracking import tracked_call


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference',type=Path);p.add_argument('encoded',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--ffprobe',default='ffprobe')
    args=p.parse_args();args.output_dir.mkdir(exist_ok=False)
    args.source=args.reference;args.hdr_mode='pq';args.timeout=1800;args.vmaf_mean=args.vmaf_p5=90
    identities={path:digest(path,lambda:None) for path in (args.reference,args.encoded)}
    def work():
        workflow=Workflow(args,args.output_dir,lambda:None)
        before=workflow.probe(args.reference)
        frames=workflow.frame_file(args.reference,'reference',before['format'])
        count=workflow.validate(args.reference,args.encoded,before,'hevc','output',frames)
        duration=float(before['format']['duration'])
        calibration=workflow.quality(args.reference,args.reference,'self',count,duration)
        quality=workflow.quality(args.reference,args.encoded,'encoded',count,duration)
        for path,identity in identities.items():
            if digest(path,lambda:None)!=identity:raise ValueError('Input changed')
        result=dict(frames=count,calibration=calibration,quality=quality,source_unchanged=True)
        (args.output_dir/'smoke.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    return tracked_call(work,'Automatic HDR quality smoke',args.output_dir)


if __name__=='__main__':raise SystemExit(main())
