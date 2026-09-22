"""Isolated Linux comparison of automatic versus bounded quality thread pools."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import time

from auto_optimize import quality_command
from hdr_auto import quality_graph


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('reference',type=Path)
    parser.add_argument('candidate',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--frames',type=int,default=24)
    parser.add_argument('--rate',default='24')
    args=parser.parse_args()
    if not 2<=args.frames<=120:raise ValueError('Use a bounded 2..120-frame diagnostic')
    args.output.mkdir(exist_ok=False)
    identity={str(p):digest(p) for p in (args.reference,args.candidate)}
    rows=[]
    for index,mode in enumerate(('automatic','bounded','bounded','automatic')):
        name=f'{index}-{mode}.json'
        graph=quality_graph(name,args.rate,args.frames)
        command=quality_command('ffmpeg',args.candidate,args.reference,graph)
        if mode=='automatic':
            for option in ('-filter_complex_threads','-threads','-threads'):
                if option in command:
                    i=command.index(option);del command[i:i+2]
        started=time.monotonic();peak=0
        with (args.output/f'{index}.log').open('x') as log:
            child=subprocess.Popen(command,cwd=args.output,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            try:
                while child.poll() is None:
                    if time.monotonic()-started>600:raise TimeoutError('Bounded quality benchmark exceeded 600 seconds')
                    try:
                        for line in Path(f'/proc/{child.pid}/status').read_text().splitlines():
                            if line.startswith('VmRSS:'):peak=max(peak,int(line.split()[1])*1024)
                    except FileNotFoundError:pass
                    time.sleep(.1)
                if child.returncode:raise RuntimeError(f'Quality benchmark failed: {mode}; inspect {index}.log')
            finally:
                if child.poll() is None:child.terminate()
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:child.kill();child.wait()
        scores=json.loads((args.output/name).read_text())['frames']
        if len(scores)!=args.frames:raise ValueError('Metric frame count changed')
        rows.append(dict(mode=mode,seconds=time.monotonic()-started,peak_rss_bytes=peak,frames=scores))
    reference=rows[0]['frames'];delta=0
    for row in rows[1:]:
        for a,b in zip(reference,row['frames']):
            if a['frameNum']!=b['frameNum'] or a['metrics'].keys()!=b['metrics'].keys():
                raise ValueError('Metric frame identity changed')
            if not all(math.isfinite(v) for frame in (a,b) for v in frame['metrics'].values()):
                raise ValueError('Non-finite quality measurement')
            delta=max(delta,max(abs(a['metrics'][k]-b['metrics'][k]) for k in a['metrics']))
    if identity!={str(p):digest(p) for p in (args.reference,args.candidate)}:raise ValueError('Input changed')
    result=dict(passed=delta<=1e-6,frames=args.frames,max_metric_delta=delta,inputs=identity,
        runs=[{k:v for k,v in row.items() if k!='frames'} for row in rows],
        medians={mode:statistics.median(r['seconds'] for r in rows if r['mode']==mode) for mode in ('automatic','bounded')},
        scope='Same bounded HDR metric frames; concurrent-host wall time, not full-workflow speed or native Dolby Vision quality')
    (args.output/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    if not result['passed']:raise ValueError(f'Metric results differ: {delta}')


if __name__=='__main__':main()
