"""Qualify an existing bounded reference through the shared encode/validate path."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import time

import auto_optimize as ao
import muxmender as mm


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--codec',choices=('hevc','av1'),required=True)
    parser.add_argument('--hdr',choices=('pq','hlg'))
    args=parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=False)
    source=args.source.resolve(strict=True)
    identity=(source.stat().st_size,source.stat().st_mtime_ns)
    def guard():
        if (source.stat().st_size,source.stat().st_mtime_ns)!=identity:
            raise ValueError('Research source changed')
    workflow=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=3600,hdr_mode=args.hdr),args.work,guard)
    before=workflow.probe(source)
    duration=float(before['format']['duration'])
    if not 0<duration<=35:raise ValueError('Research reference must be at most 35 seconds')
    settings=dict(codec=args.codec,quality='balanced',encoder=args.codec+'_nvenc')
    output=args.work/(args.codec+'.mkv')
    started=time.time()
    frames=workflow.frame_file(source,'source',before['format'])
    workflow.encode_preserving_color(source,output,settings,mm.probe(source),before,'encode',duration)
    count=workflow.validate(source,output,before,args.codec,'validation',frames)
    result=dict(preservation_passed=True,frames=count,source=str(source),output=str(output),
                size_reduction_percent=100*(1-output.stat().st_size/source.stat().st_size),
                preservation_elapsed_seconds=time.time()-started,publication_authorized=False)
    if args.hdr:
        from hdr_auto import measure_prefix_quality
        result['quality']=measure_prefix_quality('ffmpeg',source,output,args.work,count,
                                                ao.main_video(before)['avg_frame_rate'],guard)
    result['elapsed_seconds']=time.time()-started
    (args.work/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
