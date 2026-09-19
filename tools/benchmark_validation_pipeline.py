"""Compare complete validation paths on generated media; never library files.

The old path uses automatic frame threads and one packet read per copied track.
Both paths retain full decode, metadata/frame/packet comparison and file hashes.
This measures validation, NOT encoding, VMAF trials or replacement throughput.
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import auto_optimize as ao


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--ffprobe',default='ffprobe')
    p.add_argument('--output-root',type=Path,required=True)
    p.add_argument('--seconds',type=int,default=30);p.add_argument('--rounds',type=int,default=3)
    args=p.parse_args()
    if not 5<=args.seconds<=60 or not 1<=args.rounds<=5:p.error('Use 5–60 seconds and 1–5 rounds')
    args.output_root.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='validation-pipeline-',dir=args.output_root));print(root,flush=True)
    subs=root/'generated.srt';subs.write_text('1\n00:00:01,000 --> 00:00:04,000\nGenerated caption\n')
    source=root/'source.mkv';output=root/'encoded.mkv'
    subprocess.run([args.ffmpeg,'-hide_banner','-nostdin','-v','error','-n','-f','lavfi','-i',
        f'testsrc2=size=720x480:rate=24:duration={args.seconds}','-f','lavfi','-i',
        f'sine=frequency=440:sample_rate=48000:duration={args.seconds}','-i',str(subs),
        '-map','0:v','-map','1:a','-map','1:a','-map','1:a','-map','2:s',
        '-vf','setfield=prog','-c:v','libx264','-preset','ultrafast','-threads','2','-crf','18',
        '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
        '-c:a','ac3','-c:s','srt','-t',str(args.seconds),str(source)],check=True,timeout=180)
    subprocess.run([args.ffmpeg,'-hide_banner','-nostdin','-v','error','-n','-copyts','-i',str(source),
        '-map','0','-c','copy','-c:v','libx265','-preset','ultrafast','-crf','23',
        '-x265-params','pools=1:frame-threads=1:log-level=error',
        '-fps_mode:v','passthrough','-avoid_negative_ts','disabled',str(output)],check=True,timeout=180)
    original=ao.digest(source);encoded=ao.digest(output);measurements=[]
    real_probe=ao.run_probe
    for trial in range(args.rounds):
        for mode in (['legacy','current'] if trial%2==0 else ['current','legacy']):
            folder=root/f'{trial}-{mode}';folder.mkdir()
            workflow=ao.Workflow(SimpleNamespace(ffmpeg=args.ffmpeg,ffprobe=args.ffprobe,timeout=180),folder,lambda:None)
            def reader(command,*rest):
                command=list(command)
                if mode=='legacy' and '-threads' in command:
                    i=command.index('-threads');del command[i:i+2]
                return real_probe(command,*rest)
            if mode=='legacy':
                workflow.copied_packets=lambda src,label,indices,metadata,reuse_sample=False: {
                    index:workflow.packet_file(src,label,index) for index in indices}
            started=time.perf_counter()
            with patch.object(ao,'run_probe',side_effect=reader):
                before=workflow.probe(source)
                frames=workflow.frame_file(source,'source',before['format'])
                count=workflow.validate(source,output,before,'hevc','output',frames)
                assert ao.digest(source)==original and ao.digest(output)==encoded
            measurements.append(dict(mode=mode,round=trial,seconds=time.perf_counter()-started,frames=count))
            print(json.dumps(measurements[-1]),flush=True)
    medians={mode:statistics.median(r['seconds'] for r in measurements if r['mode']==mode) for mode in ('legacy','current')}
    result=dict(scope='Complete validation only; generated local fixture, not total job throughput',
        seconds=args.seconds,copied_tracks=4,measurements=measurements,medians=medians,
        time_reduction_percent=100*(1-medians['current']/medians['legacy']),
        source_and_output_hashes_unchanged=True)
    (root/'benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()
