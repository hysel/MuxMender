"""Read-only source qualification of an already-encoded MPEG-4 AVI candidate."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import auto_optimize as ao
from mpeg4_timing import recover_tail_evidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--tail',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();args.work.mkdir(exist_ok=False)
    plan=json.loads((args.run/'plan.json').read_text())
    source=Path(plan['source']);output=args.run/'full-av1.mkv'
    source_frames=args.run/'full-source-frames.jsonl';output_frames=args.run/'full-frames.jsonl'
    raw=args.tail/'tail.m4v';tail=args.tail/'tail-frames.json'
    inputs=(source,output,source_frames,output_frames,raw,tail)
    for path in inputs:
        if path.is_symlink():raise ValueError('Unexpected symlink input')
    for path in (source_frames,output_frames):
        if path.with_suffix(path.suffix+'.stderr').stat().st_size:raise ValueError('Prior decoder error')
    stamps={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in inputs}
    def guard():
        if any((p.stat().st_size,p.stat().st_mtime_ns)!=stamp for p,stamp in stamps.items()):
            raise ValueError('Qualification input/evidence changed')
    hashes={str(p):ao.digest(p,guard) for p in inputs}
    if hashes[str(source)]!=json.loads((args.run/'trials.json').read_text())['source_id']:
        raise ValueError('Source no longer matches encoded trial')
    recovered=args.work/'source-recovered-frames.jsonl'
    proof=recover_tail_evidence(raw.read_bytes(),json.loads(tail.read_text())['frames'],source_frames,recovered)
    (args.work/'timing-proof.json').write_text(json.dumps(proof,indent=2))
    workflow=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=14400,
                         source=source,resolved_color=plan['color_inspection']['effective']),args.work,guard)
    before=workflow.probe(source)
    def frame_file(path,*unused):
        if path!=output:raise ValueError('Unexpected evidence reuse request')
        return output_frames
    workflow.frame_file=frame_file
    count=workflow.validate(source,output,before,'av1','retained',recovered)
    if any(ao.digest(p,guard)!=hashes[str(p)] for p in inputs):raise ValueError('Input checksum changed')
    result=dict(full_preservation_validation_passed=True,frames=count,timing_recovery=proof,
                input_and_evidence_sha256=hashes,quality_retested=False,publication_authorized=False,
                size_reduction_percent=100*(1-output.stat().st_size/source.stat().st_size))
    (args.work/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()
