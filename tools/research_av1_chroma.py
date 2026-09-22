"""Qualification only: source-proven siting on a retained no-resize AV1 encode."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import auto_optimize as ao


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--encoded',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=False)
    identities={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in (args.source,args.encoded)}
    def guard():
        for p,s in identities.items():
            if (p.stat().st_size,p.stat().st_mtime_ns)!=s:raise ValueError('Input changed')
    workflow=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=1800,hdr_mode='pq'),args.work,guard)
    before=workflow.probe(args.source);encoded=workflow.probe(args.encoded)
    v=ao.main_video(before);e=ao.main_video(encoded)
    if v.get('chroma_location')!='topleft' or e.get('chroma_location') not in (None,'unspecified'):
        raise ValueError('Not the qualified missing-siting case')
    if v['pix_fmt']!='yuv420p10le' or e['pix_fmt']!=v['pix_fmt']:
        raise ValueError('Unexpected chroma layout')
    output=args.work/'av1-siting.mkv'
    command=['ffmpeg','-v','error','-nostdin','-n','-copyts','-i',str(args.encoded),
             '-map','0','-c','copy','-map_metadata','0','-map_chapters','0',
             '-avoid_negative_ts','disabled','-bsf:v:0','av1_metadata=chroma_sample_position=colocated']
    for i,s in enumerate(encoded['streams']):
        command += [f'-disposition:{i}','+'.join(k for k,v in s.get('disposition',{}).items() if v) or '0']
    command += ['-progress','pipe:1','-nostats',str(output)]
    workflow.execute(workflow.preserve_covers(command,args.encoded,encoded,'siting'), 'siting',float(before['format']['duration']))
    frames=workflow.frame_file(args.source,'reference',before['format'])
    count=workflow.validate(args.source,output,before,'av1','corrected',frames)
    hashes=[]
    for label,p in [('before',args.encoded),('after',output)]:
        target=args.work/(label+'.framemd5')
        workflow.execute(['ffmpeg','-v','error','-nostdin','-n','-i',str(p),'-map','0:v:0',
                          '-fps_mode','passthrough','-f','framemd5',str(target)],label,float(before['format']['duration']))
        hashes.append([line.split(',')[-1].strip() for line in target.read_text().splitlines() if line and not line.startswith('#')])
    if len(hashes[0])!=count or hashes[0]!=hashes[1]:raise ValueError('Bitstream repair changed decoded pixels')
    result=dict(frames=count,preservation_passed=True,decoded_pixels_unchanged=True,quality_approved=False,
                output=str(output),source=str(args.source))
    (args.work/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
