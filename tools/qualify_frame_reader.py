"""Generated-media qualification of bounded FFprobe decoder threads.

Never opens library media. Retains fixtures and evidence in a fresh output folder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from auto_optimize import compare_frames

FIELDS='best_effort_timestamp_time,width,height,pix_fmt,sample_aspect_ratio,interlaced_frame,repeat_pict,color_primaries,color_transfer,color_space,color_range'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ffmpeg',required=True);p.add_argument('--ffprobe',required=True)
    p.add_argument('--output-root',type=Path,required=True)
    args=p.parse_args();args.output_root.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='frame-qualification-',dir=args.output_root))
    results=[]
    variants={
        'h264':['-c:v','libx264','-preset','ultrafast','-threads','2'],
        'hevc':['-c:v','libx265','-preset','ultrafast','-x265-params','pools=1:frame-threads=1:log-level=error'],
        'av1':['-c:v','libaom-av1','-cpu-used','8','-threads','2','-row-mt','1'],
        'hdr':['-c:v','libx265','-preset','ultrafast','-pix_fmt','yuv420p10le','-color_trc','smpte2084',
               '-x265-params','pools=1:frame-threads=1:log-level=error:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):max-cll=1000,400']}
    for name,options in variants.items():
        source=root/(name+'.mkv')
        subprocess.run([args.ffmpeg,'-hide_banner','-nostdin','-v','error','-n','-f','lavfi','-i',
                        'testsrc2=size=720x480:rate=24000/1001','-t','10','-color_primaries','bt709',
                        '-color_trc','bt709','-colorspace','bt709','-color_range','tv',*options,str(source)],check=True,timeout=180)
        before=hashlib.sha256(source.read_bytes()).hexdigest();times={};paths={}
        for trial in range(3):
            for threads in ([None,2] if trial%2==0 else [2,None]):
                path=root/f'{name}-{trial}-{threads}.txt';paths[threads]=path
                command=[args.ffprobe,'-v','error','-select_streams','v:0','-show_frames','-show_entries','frame='+FIELDS,'-of','compact=p=0']
                if threads:command+=['-threads',str(threads)]
                start=time.perf_counter()
                with path.open('xb') as handle:
                    subprocess.run([*command,str(source)],stdout=handle,check=True,timeout=180)
                times.setdefault(str(threads),[]).append(time.perf_counter()-start)
            if name=='hdr':
                for path in paths.values():
                    text=path.read_text()
                    assert 'Mastering display metadata' in text and 'Content light level metadata' in text
                    try:compare_frames(path,path)
                    except ValueError:pass
                    else:raise AssertionError('HDR evidence was accepted')
            else:
                assert compare_frames(paths[None],paths[2])==240
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        results.append(dict(codec=name,frames=240,rejected=name=='hdr',medians={k:statistics.median(v) for k,v in times.items()},measurements=times))
        print(json.dumps(results[-1]),flush=True)
    (root/'qualification.json').write_text(json.dumps(results,indent=2))
    print('PASS:',root)


if __name__=='__main__':main()
