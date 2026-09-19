"""Bounded generated-media CPU/CUDA pixel-equivalence and timing test.

No library inputs, installations, application settings or deletion. Passing this
test alone does NOT enable GPU validation or certify HDR/audio/error equivalence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import tempfile
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-root',type=Path,required=True)
    p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--seconds',type=int,default=30)
    args=p.parse_args()
    if not 5<=args.seconds<=60:p.error('Use 5–60 seconds')
    args.output_root.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='gpu-decode-',dir=args.output_root));print(root,flush=True)
    source=root/'generated-hevc.mkv'
    subprocess.run([args.ffmpeg,'-hide_banner','-nostdin','-v','error','-n',
        '-f','lavfi','-i',f'testsrc2=size=1280x720:rate=24:duration={args.seconds}',
        '-c:v','libx265','-preset','ultrafast','-x265-params','pools=1:frame-threads=1:log-level=error',
        '-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',str(source)],
        check=True,timeout=180)
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest();rows=[];pixels={};failures=[]
    for trial in range(3):
        for mode in (['cpu','cuda'] if trial%2==0 else ['cuda','cpu']):
            output=root/f'{trial}-{mode}.framemd5'
            command=[args.ffmpeg,'-hide_banner','-nostdin','-v','error','-xerror','-n','-threads','2']
            if mode=='cuda':command+=['-hwaccel','cuda','-hwaccel_output_format','cuda']
            command+=['-i',str(source),'-map','0:v:0','-an','-sn']
            if mode=='cuda':command+=['-vf','hwdownload,format=nv12,format=yuv420p']
            command+=['-pix_fmt','yuv420p','-c:v','rawvideo','-threads','2','-fps_mode','passthrough','-f','framemd5',str(output)]
            started=time.perf_counter()
            result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=180)
            (root/f'{trial}-{mode}.stderr').write_text(result.stderr)
            if result.returncode:
                failures.append(dict(mode=mode,round=trial,returncode=result.returncode,error=result.stderr[-4000:]))
                break
            evidence=[line.strip() for line in output.read_text().splitlines() if line.strip() and not line.startswith('#')]
            pixels[(mode,trial)]=evidence
            rows.append(dict(mode=mode,round=trial,seconds=time.perf_counter()-started,frames=len(evidence)))
            print(json.dumps(rows[-1]),flush=True)
        if failures:break
    unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    equal=(not failures and len(pixels)==6 and all(len(v)==args.seconds*24 and v==pixels[('cpu',0)] for v in pixels.values()))
    medians={mode:statistics.median(r['seconds'] for r in rows if r['mode']==mode) for mode in ('cpu','cuda') if any(r['mode']==mode for r in rows)}
    report=dict(generated_media_only=True,pixel_and_timing_equivalence=equal,source_unchanged=unchanged,
        medians=medians,measurements=rows,failures=failures,gpu_validation_enabled=False,
        scope='SDR HEVC decode/download/frame checksums only; not HDR/audio/corruption/full-workflow certification')
    (root/'benchmark.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    return 0 if equal and unchanged else 1


if __name__=='__main__':raise SystemExit(main())
