"""Remux and verify an isolated completed DV encode; never repeat the encode."""
import argparse
import json
from pathlib import Path
import uuid
import dv_full_file as full
import dv_preservation_test as dv
import native_pipeline as native
import muxmender as mm
from job_tracking import tracked_call,progress


def run(args):
    previous=json.loads((args.parent/'validation.json').read_text())
    source=Path(previous['source'])
    video=args.parent/'timestamped-dv-video.mkv'
    inputs=(source,video,args.parent/'original.hevc',args.parent/'original-rpu.bin',args.parent/'source-frames.compact')
    stamps={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in inputs}
    def guard():
        if any(p.is_symlink() or (p.stat().st_size,p.stat().st_mtime_ns)!=stamp for p,stamp in stamps.items()):
            raise ValueError('Retained DV inputs changed')
    guard()
    if previous.get('error')!='Ordered mux memory monitoring unavailable; partial retained':
        raise ValueError('This recovery only retries the diagnosed mux-monitoring failure')
    info=mm.probe(source,'ffprobe')
    streams={'streams':dv.stream_info('ffprobe',source)}
    output=args.parent/('recovered-dv-'+uuid.uuid4().hex[:8]+'.mkv')
    command=full.ordered_dv_mux_command('ffmpeg',video,source,output,streams)
    (args.work/'remux-command.json').write_text(json.dumps(command,indent=2))
    progress('Retrying final DV mux with exit-race fix')
    native.stage(command,info.duration_seconds,0,100,timeout=1800,stall=120,guard=guard)
    guard()
    result=full.verify_existing(args.parent,output=output,ffmpeg='ffmpeg',ffprobe='ffprobe',
                                dovi_tool=args.dovi_tool,min_savings=10)
    guard()
    (args.work/'result.json').write_text(json.dumps(dict(exit_code=result,output=str(output),
        source_unchanged=True,encode_reused=True,publication_authorized=False),indent=2))
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--parent',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--dovi-tool',required=True)
    args=parser.parse_args();args.work.mkdir(exist_ok=False)
    return tracked_call(lambda:run(args),'Retained DV mux recovery and full validation',folder=args.work)


if __name__=='__main__':raise SystemExit(main())
