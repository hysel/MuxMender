"""Re-score an unchanged, previously validated research pair with four workers."""
import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace


def main():
    if sys.platform!='linux':raise RuntimeError('Linux research only')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--controls-status',type=Path,required=True)
    args=parser.parse_args()
    before=json.loads(args.status.read_text())
    if (before.get('state')!='research-completed-not-approved'
            or before.get('preservation_pass') is not True
            or before.get('full_quality',{}).get('passed') is not True):
        raise ValueError('Requires a completed preservation/quality research result')
    old=before['full_quality']
    if old.get('reference_domain')!='original-resolution reference':raise ValueError('Original-resolution comparison required')
    source,candidate=Path(before['source']),Path(before['candidate'])
    args.output.mkdir(parents=True,exist_ok=False)
    from auto_optimize import Workflow,quality_graph,quality_command,quality_summary,main_video
    from task_progress import digest
    from job_tracking import tracked_call
    def guard():
        state=json.loads(args.controls_status.read_text())
        if (state.get('ready') is not True or not 0<=time.time()-state.get('updated',0)<=12
                or any(state.get('counts',{}).get(k,0) for k in ('pending','running'))):
            raise RuntimeError('Fresh production idle proof unavailable')
    def run():
        report=dict(research_only=True,publication_authorized=False,baseline_quality=old)
        try:
            expected=[before['source_sha256'],before['output_sha256']]
            if [digest(p,guard) for p in (source,candidate)]!=expected:raise ValueError('Pair changed since full validation')
            options=SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',source=source,timeout=7200)
            work=Workflow(options,args.output,guard)
            metadata=work.probe(source);video=main_video(metadata)
            if (video.get('codec_name')!='av1' or video.get('pix_fmt')!='yuv420p'
                    or video.get('field_order')!='progressive'
                    or video.get('color_transfer') in ('smpte2084','arib-std-b67')):
                raise ValueError('Qualified progressive SDR AV1 scope required')
            graph=quality_graph('full-four-vmaf.json',video['avg_frame_rate'],threads=4)
            start=time.monotonic()
            work.execute(quality_command('ffmpeg',candidate,source,graph),'Full quality comparison: four scoring threads',float(metadata['format']['duration']))
            report['scoring_seconds']=time.monotonic()-start
            quality=quality_summary(json.loads((args.output/'full-four-vmaf.json').read_text()),
                                    old['frames'],old['thresholds']['mean'],old['thresholds']['p5'])
            report['quality']=quality
            report['score_delta']={key:abs(quality[key]-old[key]) for key in ('mean','p5')}
            report['inputs_unchanged']=[digest(p,guard) for p in (source,candidate)]==expected
            report['passed']=(report['inputs_unchanged'] and quality['passed']==old['passed']
                and quality['frames']==old['frames'] and max(report['score_delta'].values())<=1e-6)
            if not report['passed']:raise ValueError('Full scoring equivalence failed')
        except BaseException as exc:
            report.update(passed=False,error=str(exc));raise
        finally:(args.output/'result.json').write_text(json.dumps(report,indent=2))
        return 0
    return tracked_call(run,'Full-file validation: four scoring threads',args.output/'reports')


if __name__=='__main__':raise SystemExit(main())
