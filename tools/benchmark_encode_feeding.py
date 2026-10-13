"""Linux-only generated AV1 decode/encode comparison; never qualifies publication."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import urllib.request


def command(binary, source, output, mode, *, pixels=False):
    if mode not in ('cpu2','cpu4','cuda'):raise ValueError('Unknown decode mode')
    args=[binary,'-hide_banner','-nostdin','-v','error','-n','-xerror','-copyts',
          '-filter_threads','2','-threads','4' if mode=='cpu4' else '2']
    if mode=='cuda':args+=['-hwaccel','cuda','-hwaccel_output_format','cuda']
    args+=['-i',str(source),'-map','0:v:0','-an','-sn']
    if mode=='cuda':args+=['-vf','hwdownload,format=nv12,format=yuv420p']
    if pixels:
        args+=['-c:v','rawvideo','-threads:v','2','-pix_fmt','yuv420p','-f','framemd5']
    else:
        args+=['-c:v','av1_nvenc','-preset','p5','-tune','hq','-rc','vbr',
               '-cq','25','-b:v','0','-pix_fmt','yuv420p','-enc_time_base','demux']
    return args+['-fps_mode','passthrough',str(output)]


def records(path):
    return [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith('#')]


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Run native media tests on Linux only')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ffmpeg',default='/opt/ffmpeg9/bin/ffmpeg')
    parser.add_argument('--seconds',type=int,default=20)
    control=parser.add_mutually_exclusive_group(required=True)
    control.add_argument('--controls-url',help='Read-only production controls API')
    control.add_argument('--controls-status',type=Path,help='Fresh read-only queue relay for network-isolated research')
    args=parser.parse_args()
    if not 5<=args.seconds<=30:parser.error('Use 5–30 seconds')
    args.output.mkdir(parents=True,exist_ok=False)
    from job_tracking import Job
    job=Job(args.output/'reports','AV1 encoding input throughput comparison')
    report=dict(generated_only=True,production_enabled=False,quality_approved=False,measurements=[])
    source=args.output/'generated-av1.mkv'
    owned=[]
    def idle():
        if args.controls_status:
            state=json.loads(args.controls_status.read_text())
            age=time.time()-state.get('updated',0)
            if not 0<=age<=12:return False
        else:
            with urllib.request.urlopen(args.controls_url,timeout=5) as response:state=json.load(response)
        counts=state.get('counts')
        if not state.get('ready') or not isinstance(counts,dict):return False
        return not any(counts.get(key,0) for key in ('running','pending'))
    def run(cmd,label):
        if not idle():raise RuntimeError('Production work resumed; research stopped without changing the queue')
        job.save(phase=label,detail='Isolated generated fixture; quality gates unchanged')
        start=time.monotonic()
        with subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as process:
            try:
                while True:
                    try:
                        _,stderr=process.communicate(timeout=2);break
                    except subprocess.TimeoutExpired:
                        if time.monotonic()-start>180:raise RuntimeError('Bounded research stage timeout')
                        if not idle():raise RuntimeError('Production work resumed; research stopped')
                        job.save(detail='Isolated generated fixture; production queue still idle')
                if process.returncode:raise RuntimeError(label+': '+stderr[-2000:])
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.communicate()
        return time.monotonic()-start
    try:
        deadline=time.monotonic()+7200
        while True:
            try:available=idle()
            except (OSError,ValueError):available=False
            if available:break
            if time.monotonic()>deadline:raise RuntimeError('Production never became idle within two hours; no media test started')
            job.save(phase='Waiting for production to finish',detail='No GPU benchmark is running. Production is not paused or changed.')
            time.sleep(5)
        owned.append(source)
        run([args.ffmpeg,'-hide_banner','-nostdin','-v','error','-n','-f','lavfi','-i',
             f'testsrc2=size=1920x1080:rate=24:duration={args.seconds}',
             '-c:v','av1_nvenc','-preset','p5','-cq','20','-b:v','0',
             '-pix_fmt','yuv420p',str(source)],'Generate AV1 fixture')
        source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        baseline=None
        for mode in ('cpu2','cpu4','cuda'):
            path=args.output/(mode+'.framemd5');owned.append(path)
            elapsed=run(command(args.ffmpeg,source,path,mode,pixels=True),'Check exact decoded frames: '+mode)
            frames=records(path)
            if baseline is None:baseline=frames
            if frames!=baseline or len(frames)!=args.seconds*24:
                raise RuntimeError('Decoded pixels or frame timing differ: '+mode)
            report.setdefault('decode_seconds',{})[mode]=elapsed
        for trial,modes in enumerate((('cpu2','cpu4','cuda'),('cuda','cpu4','cpu2'),('cpu4','cpu2','cuda'))):
            for mode in modes:
                path=args.output/f'encode-{trial}-{mode}.mkv';owned.append(path)
                elapsed=run(command(args.ffmpeg,source,path,mode),'Encode comparison '+str(trial+1)+': '+mode)
                report['measurements'].append(dict(mode=mode,seconds=elapsed,bytes=path.stat().st_size))
        if hashlib.sha256(source.read_bytes()).hexdigest()!=source_hash:raise RuntimeError('Generated source changed')
        report['decoded_pixels_and_timing_equal']=True
        report['median_seconds']={mode:statistics.median(r['seconds'] for r in report['measurements'] if r['mode']==mode)
                                  for mode in ('cpu2','cpu4','cuda')}
        report['limits']='Generated AV1 8-bit SDR only; not real-media, corruption, HDR, audio or full validation qualification.'
    except Exception as exc:
        report['error']=str(exc)
    finally:
        removed=0
        for path in owned:
            if path.is_file() and not path.is_symlink() and path.parent==args.output:
                removed+=path.stat().st_size;path.unlink()
        report['temporary_bytes_removed']=removed
        (args.output/'benchmark.json').write_text(json.dumps(report,indent=2))
        job.save(state='failed' if 'error' in report else 'completed',phase='Comparison failed' if 'error' in report else 'Comparison completed',
                 detail=json.dumps(report),finished=time.time())
    return int('error' in report)


if __name__=='__main__':raise SystemExit(main())
