"""Finish retained-output validation using completed, isolated frame evidence.

This is a research harness, not a production validation cache. The caller must
identify evidence collected for these exact unchanged inputs in this session.
Frame collection is reused; metadata, frame comparison, all copied packets,
decoded audio fallback and complete output decode run through the shared engine.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import auto_optimize as ao


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=False)
    plan=json.loads((args.run/'plan.json').read_text())
    source=Path(plan['source']);output=args.run/'full-hevc.mkv'
    source_frames=args.evidence/'fresh-source-frames.jsonl'
    output_frames=args.evidence/'retained-frames.jsonl'
    for p in (source_frames,output_frames):
        if p.is_symlink() or p.with_suffix(p.suffix+'.stderr').stat().st_size:
            raise ValueError('Unusable prior frame evidence')
    inputs=(source,output,source_frames,output_frames)
    stamps={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in inputs}
    def guard():
        if any((p.stat().st_size,p.stat().st_mtime_ns)!=s for p,s in stamps.items()):
            raise ValueError('Retained input/evidence changed')
    hashes={str(p):ao.digest(p,guard) for p in inputs}
    if hashes[str(source)]!=json.loads((args.run/'trials.json').read_text())['source_id']:
        raise ValueError('Original differs from original trial content hash')
    workflow=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=14400),args.work,guard)
    before=workflow.probe(source)
    for key,value in (plan.get('color_inspection') or {}).get('effective',{}).items():
        if value is None:before['streams'][0].pop(key,None)
        else:before['streams'][0][key]=value
    def frame_file(path,*unused):
        if path!=output:raise ValueError('Unexpected frame-cache input')
        return output_frames
    workflow.frame_file=frame_file
    count=workflow.validate(source,output,before,'hevc','retained',source_frames)
    if any(ao.digest(p,guard)!=hashes[str(p)] for p in inputs):raise ValueError('Input/evidence checksum changed')
    result=dict(full_preservation_validation_passed=True,frames=count,frame_collection_reused=True,
                evidence_directory=str(args.evidence),input_and_evidence_sha256=hashes,
                quality_retested=False,publication_authorized=False,
                size_reduction_percent=100*(1-output.stat().st_size/source.stat().st_size))
    (args.work/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()
