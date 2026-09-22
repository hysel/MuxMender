"""Validate a timing fix on an isolated <=30-second excerpt; never approves replacement."""
import argparse
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
from types import SimpleNamespace
from auto_optimize import Workflow,compact_rows
import muxmender as mm
import legacy_color
from encoder_capabilities import probe_encoder
from task_progress import digest
from job_tracking import tracked_call


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--encoder',choices=('hevc_amf','hevc_nvenc','hevc_qsv'),required=True)
    p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--ffprobe',default='ffprobe')
    args=p.parse_args();args.source=args.source.resolve(strict=True)
    args.output_dir=args.output_dir.resolve()
    if args.source.is_relative_to(args.output_dir):raise ValueError('Keep input outside output directory')
    args.timeout=180
    info=mm.probe(args.source,args.ffprobe)
    if not 0<info.duration_seconds<=30:raise ValueError('Use an isolated excerpt of at most 30 seconds')
    args.output_dir.mkdir(exist_ok=False)
    identity=(args.source.stat().st_size,args.source.stat().st_mtime_ns)
    def guard():
        if identity!=(args.source.stat().st_size,args.source.stat().st_mtime_ns):raise ValueError('Input changed')
    source_hash=digest(args.source,guard)
    def work():
        nonlocal info
        w=Workflow(args,args.output_dir,guard);before=w.probe(args.source)
        video=next(s for s in before['streams'] if s['codec_type']=='video')
        if video.get('codec_name')=='h264' and video.get('color_range') in legacy_color.UNKNOWN:
            evidence=legacy_color.inspect_h264_default_range(args.ffmpeg,args.source,info.duration_seconds)
            if evidence:
                video['color_range']=evidence['value'];args.resolved_color={'color_range':evidence['value']}
                info=replace(info,color_range=evidence['value'])
        support=probe_encoder(args.ffmpeg,args.encoder,video['width'],video['height'],pixel_format=video['pix_fmt'])
        if support['status']!='working':raise ValueError('Requested GPU encoder unavailable: '+str(support))
        frames=w.frame_file(args.source,'reference',before['format'])
        output=args.output_dir/'fixed-timing.mkv'
        w.encode_preserving_color(args.source,output,dict(codec='hevc',encoder=args.encoder,quality='compact'),
                                  info,before,'encode',info.duration_seconds)
        count=w.validate(args.source,output,before,'hevc','validated',frames)
        pairs=list(zip(compact_rows(frames,'width'),compact_rows(args.output_dir/'validated-frames.jsonl','width')))
        delta=max(abs(Fraction(a['best_effort_timestamp_time'])-Fraction(b['best_effort_timestamp_time'])) for a,b in pairs)
        if digest(args.source,guard)!=source_hash:raise ValueError('Input checksum changed')
        result=dict(encoder=args.encoder,frames=count,max_timestamp_delta_seconds=float(delta),
                    native_validation_passed=True,source_unchanged=True,quality_evaluated=False,replacement_authorized=False)
        (args.output_dir/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    return tracked_call(work,'Isolated timing regression',args.output_dir)


if __name__=='__main__':raise SystemExit(main())
