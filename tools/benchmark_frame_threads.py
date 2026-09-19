"""Read-only frame-reader comparison; writes only a fresh evidence folder."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import tempfile
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    p.add_argument('--ffprobe',required=True);p.add_argument('--output-root',type=Path,required=True)
    args=p.parse_args();args.output_root.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='frame-threads-',dir=args.output_root));results=[]
    for trial in range(3):
        for threads in ([None,2,4] if trial%2==0 else [4,2,None]):
            target=root/f'{trial}-{threads}.txt';started=time.perf_counter()
            command=[args.ffprobe,'-v','error','-select_streams','v:0','-show_frames','-show_entries',
                     'frame=best_effort_timestamp_time,width,height,pix_fmt,sample_aspect_ratio,interlaced_frame,repeat_pict,color_primaries,color_transfer,color_space,color_range',
                     '-of','compact=p=0']
            if threads:command+=['-threads',str(threads)]
            with target.open('xb') as output:subprocess.run([*command,str(args.source)],stdout=output,check=True,timeout=180)
            data=target.read_bytes()
            results.append(dict(round=trial,threads=threads,seconds=time.perf_counter()-started,sha256=hashlib.sha256(data).hexdigest(),lines=len(data.splitlines())))
            print(json.dumps(results[-1]),flush=True)
    result=dict(source=str(args.source),identical_evidence=len({r['sha256'] for r in results})==1,
                medians={str(t):statistics.median(r['seconds'] for r in results if r['threads']==t) for t in (None,2,4)},measurements=results)
    (root/'benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()
