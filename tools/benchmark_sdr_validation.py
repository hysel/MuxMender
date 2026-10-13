"""Bounded Linux-only scoring comparison; never approves or publishes media."""
import argparse
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time


def command_for(ffmpeg,reference,candidate,rate,name,frames,mode):
    from auto_optimize import quality_graph,quality_command
    threads=4 if mode.endswith('4') else 2
    graph=quality_graph(name,rate,threads=threads)
    for marker in ('[0:V:0]','[1:V:0]'):
        prefix='hwdownload,format=nv12,format=yuv420p,' if mode.startswith('cuda') else ''
        graph=graph.replace(marker,marker+prefix+f'trim=end_frame={frames},')
    command=quality_command(ffmpeg,candidate,reference,graph)
    command[-1:-1]=['-frames:v',str(frames)]
    if mode.startswith('cuda'):
        for index in reversed([i for i,value in enumerate(command) if value=='-i']):
            command[index:index]=['-hwaccel','cuda','-hwaccel_output_format','cuda']
    return command


def compare(reference,other):
    if len(reference)!=len(other):raise ValueError('Metric frame count changed')
    delta=0.0
    for a,b in zip(reference,other):
        if a['frameNum']!=b['frameNum'] or a['metrics'].keys()!=b['metrics'].keys():
            raise ValueError('Metric frame identity changed')
        for key in a['metrics']:
            x,y=a['metrics'][key],b['metrics'][key]
            if not math.isfinite(x) or not math.isfinite(y):raise ValueError('Nonfinite score')
            delta=max(delta,abs(x-y))
    return delta


def main():
    if sys.platform!='linux':raise RuntimeError('Linux research only')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--controls-status',type=Path,required=True)
    parser.add_argument('--frames',type=int,default=720)
    args=parser.parse_args()
    if not 24<=args.frames<=1440:raise ValueError('Bounded test requires 24..1440 frames')
    args.output.mkdir(parents=True,exist_ok=False)
    from job_tracking import tracked_call,progress
    from task_progress import digest
    def guard():
        state=json.loads(args.controls_status.read_text())
        if (state.get('ready') is not True or not 0<=time.time()-state.get('updated',0)<=12
                or any(state.get('counts',{}).get(k,0) for k in ('running','pending'))):
            raise RuntimeError('Fresh production idle proof unavailable')
    def run():
        report=dict(research_only=True,publication_authorized=False,runs=[])
        try:
            guard()
            hashes=[digest(p,guard) for p in (args.source,args.candidate)]
            for path in (args.source,args.candidate):
                data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)],text=True,timeout=30))
                v=next(s for s in data['streams'] if s['codec_type']=='video')
                if (v['codec_name']!='av1' or v['pix_fmt']!='yuv420p'
                        or v.get('field_order')!='progressive'
                        or v.get('color_transfer') in ('smpte2084','arib-std-b67')):
                    raise ValueError('This experiment requires progressive SDR 8-bit AV1')
            rate=v['avg_frame_rate']
            modes=['cpu2','cpu4','cuda2','cuda4','cuda4','cuda2','cpu4','cpu2']
            baseline=None
            for index,mode in enumerate(modes):
                guard()
                progress('Validation speed comparison',completed=index,total=len(modes),
                         detail=f'Round {index+1}/{len(modes)}: {mode}; same frames and model')
                name=f'{index}-{mode}.json'
                command=command_for('ffmpeg',args.source,args.candidate,rate,name,args.frames,mode)
                started=time.monotonic();peak=0
                with (args.output/f'{index}.log').open('x') as log:
                    child=subprocess.Popen(command,cwd=args.output,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                    try:
                        while child.poll() is None:
                            guard()
                            if time.monotonic()-started>300:raise TimeoutError('Bounded round exceeded five minutes')
                            try:
                                for line in Path(f'/proc/{child.pid}/status').read_text().splitlines():
                                    if line.startswith('VmRSS:'):peak=max(peak,int(line.split()[1])*1024)
                            except FileNotFoundError:pass
                            time.sleep(.2)
                        if child.returncode:raise RuntimeError(f'Round {index} failed; see private log')
                    finally:
                        if child.poll() is None:child.terminate()
                        try:child.wait(timeout=10)
                        except subprocess.TimeoutExpired:child.kill();child.wait()
                frames=json.loads((args.output/name).read_text())['frames']
                if len(frames)!=args.frames:raise ValueError('Unexpected metric frame count')
                if baseline is None:baseline=frames
                delta=compare(baseline,frames)
                report['runs'].append(dict(mode=mode,seconds=time.monotonic()-started,
                                          peak_rss_bytes=peak,max_metric_delta=delta))
                (args.output/'result.json').write_text(json.dumps(report,indent=2))
                if delta>1e-6:raise ValueError('Scoring differs from baseline; not qualified')
            if hashes!=[digest(p,guard) for p in (args.source,args.candidate)]:raise ValueError('Input changed')
            report.update(passed=True,inputs_unchanged=True,frames=args.frames,
                medians={m:statistics.median(r['seconds'] for r in report['runs'] if r['mode']==m) for m in set(modes)})
        except BaseException as exc:
            report.update(passed=False,error=str(exc));raise
        finally:(args.output/'result.json').write_text(json.dumps(report,indent=2))
        return 0
    return tracked_call(run,'SDR validation speed and score equivalence',args.output/'reports')


if __name__=='__main__':raise SystemExit(main())
