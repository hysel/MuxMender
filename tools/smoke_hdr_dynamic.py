"""Read-only-source HDR10+ restoration smoke; strip only an isolated generated bitstream."""
import argparse
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from hdr10plus_preserve import finalize,frame_records
from hdr10plus_validation import validate_frames
from auto_optimize import Workflow
from task_progress import digest
from job_tracking import tracked_call


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--ffprobe',default='ffprobe')
    args=p.parse_args();root=args.output_dir;root.mkdir(exist_ok=False)
    original_identity=(args.source.stat().st_size,args.source.stat().st_mtime_ns)
    def guard():
        if original_identity!=(args.source.stat().st_size,args.source.stat().st_mtime_ns):raise ValueError('Source changed')
    def command(argv):subprocess.run(list(map(str,argv)),capture_output=True,check=True,timeout=180)
    def work():
        reference=root/'reference.mkv'
        command([args.ffmpeg,'-v','error','-nostdin','-n','-ss','120','-i',args.source,'-t','3',
                 '-map','0','-c','copy','-map_chapters','-1','-avoid_negative_ts','make_zero',reference])
        reference_hash=digest(reference,guard)
        command([args.ffmpeg,'-v','error','-nostdin','-n','-i',reference,'-map','0:v:0','-c','copy',
                 '-bsf:v','hevc_mp4toannexb','-f','hevc',root/'with-dynamic.hevc'])
        command(['hdr10plus_tool','remove',root/'with-dynamic.hevc','-o',root/'without-dynamic.hevc'])
        options=SimpleNamespace(source=reference,encoded=root/'without-dynamic.hevc',output_dir=root,
            final_output=root/'restored.mkv',repair_only=True,mode='pq',timeout=180,guard=guard,
            ffmpeg=args.ffmpeg,ffprobe=args.ffprobe,hdr10plus_tool='hdr10plus_tool',
            mkvmerge='mkvmerge',mkvextract='mkvextract',mkvpropedit='mkvpropedit')
        result=finalize(options)
        options.hdr_mode='pq'
        workflow=Workflow(options,root,guard);before=workflow.probe(reference)
        count=workflow.validate(reference,root/'restored.mkv',before,'hevc','restored',Path(result['reference_frames']))
        native=validate_frames(frame_records(result['reference_frames']),frame_records(root/'restored-frames.jsonl'),mode='hdr10plus')
        assert native['hdr10plus_frames']>0
        assert digest(reference,guard)==reference_hash
        guard();native.update(source_unchanged=True,frames=count,quality_test=False)
        (root/'smoke.json').write_text(json.dumps(native,indent=2));print(json.dumps(native,indent=2))
    return tracked_call(work,'Real HDR10+ restoration smoke',root)


if __name__=='__main__':raise SystemExit(main())
