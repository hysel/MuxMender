"""Benchmark old vs combined validation on generated media only, never library sources."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from auto_optimize import Workflow, compare_packets
from packet_validation import collect_packets


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ffmpeg',required=True);p.add_argument('--ffprobe',required=True)
    p.add_argument('--output-root',type=Path,required=True);p.add_argument('--seconds',type=int,default=60)
    p.add_argument('--rounds',type=int,default=3);args=p.parse_args()
    if not 10<=args.seconds<=300 or not 1<=args.rounds<=5:p.error('Use 10–300 seconds and 1–5 rounds')
    args.output_root.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='packet-benchmark-',dir=args.output_root));print(root,flush=True)
    subtitles=root/'generated.srt'
    subtitles.write_text('1\n00:00:01,000 --> 00:00:05,000\nGenerated validation fixture\n\n2\n00:00:06,000 --> 00:00:09,000\nSecond generated caption\n',encoding='utf-8')
    source=root/'generated.mkv';output=root/'remux.mkv'
    subprocess.run([args.ffmpeg,'-hide_banner','-nostdin','-v','error','-n',
                    '-f','lavfi','-i',f'testsrc2=size=720x480:rate=24:duration={args.seconds}',
                    '-f','lavfi','-i',f'sine=frequency=440:sample_rate=48000:duration={args.seconds}',
                    '-i',str(subtitles),'-map','0:v','-map','1:a','-map','1:a','-map','1:a','-map','1:a',
                    '-map','2:s','-map','2:s','-map','2:s','-c:v','libx264','-preset','ultrafast','-threads','2',
                    '-crf','18','-c:a','aac','-c:s','srt','-t',str(args.seconds),str(source)],check=True,timeout=180)
    subprocess.run([args.ffmpeg,'-hide_banner','-nostdin','-v','error','-n','-copyts','-i',str(source),
                    '-map','0','-c','copy','-avoid_negative_ts','disabled',str(output)],check=True,timeout=60)
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    original_hash=sha(source);output_hash=sha(output)
    indices=list(range(1,8));measurements=[]
    for trial in range(args.rounds):
        for mode in (['legacy','combined'] if trial%2==0 else ['combined','legacy']):
            folder=root/f'{trial}-{mode}';folder.mkdir();started=time.perf_counter()
            if mode=='legacy':
                workflow=Workflow(SimpleNamespace(ffprobe=args.ffprobe,timeout=180),folder,lambda:None)
                for index in indices:
                    a=workflow.packet_file(source,'source',index);b=workflow.packet_file(output,'output',index)
                    compare_packets(a,b)
            else:
                a=collect_packets(args.ffprobe,source,folder,'source',indices,180,lambda:None,args.seconds)
                b=collect_packets(args.ffprobe,output,folder,'output',indices,180,lambda:None,args.seconds)
                for index in indices:compare_packets(a[index],b[index])
            elapsed=time.perf_counter()-started
            measurements.append(dict(round=trial,mode=mode,seconds=elapsed));print(json.dumps(measurements[-1]),flush=True)
    assert sha(source)==original_hash and sha(output)==output_hash
    old=statistics.median(x['seconds'] for x in measurements if x['mode']=='legacy')
    new=statistics.median(x['seconds'] for x in measurements if x['mode']=='combined')
    result=dict(generated_media_only=True,source_bytes=source.stat().st_size,duration=args.seconds,copied_tracks=7,
                measurements=measurements,legacy_median_seconds=old,combined_median_seconds=new,
                speedup=old/new,source_and_output_unchanged=True,
                limitation='Packet validation only, local generated fixture; not total encode/validation speedup.')
    (root/'benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
