"""Linux-only generated HDR CPU/CUDA evidence benchmark; no production policy change."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time


def normalized_showinfo(text):
    result=[]
    for line in text.splitlines():
        if 'Parsed_showinfo_' not in line: continue
        line=re.sub(r'^.*?\[Parsed_showinfo_\d+ @ [^\]]+\]\s*', '', line)
        # Encoder user-data diagnostics are not HDR validation fields. Keep
        # frame/pixel clocks, geometry/color and complete printed static HDR.
        if not (re.match(r'n:\s*\d+',line) or line.startswith('color_range:') or
                line.startswith('side data -') and 'User Data Unregistered' not in line): continue
        result.append(line.strip())
    return result


def main():
    if not sys.platform.startswith('linux'): raise RuntimeError('Native HDR research is Linux-only')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--size',default='3840x2160');p.add_argument('--seconds',type=int,default=3)
    p.add_argument('--source',type=Path);p.add_argument('--start',type=int,default=600)
    p.add_argument('--rounds',type=int,default=3)
    args=p.parse_args()
    if args.size not in ('1280x720','1920x1080','3840x2160') or not 1<=args.seconds<=30 or not 1<=args.rounds<=3:
        p.error('Use a bounded supported fixture')
    args.output.mkdir(parents=True,exist_ok=False)
    from job_tracking import Job
    job=Job(args.output/'reports','RTX 5050 HDR GPU reader qualification')
    generated=args.source is None
    source=args.output/'generated-hdr.mkv' if generated else args.source
    rows=[];traces={};report={}
    try:
        job.save(phase='Generating bounded 10-bit HDR fixture',stage_percent=None)
        options=('pools=1:frame-threads=1:log-level=error:repeat-headers=1:'
                 'colorprim=9:transfer=16:colormatrix=9:'
                 'master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):max-cll=1000,400')
        if generated:subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i',
            f'testsrc2=size={args.size}:rate=24:duration={args.seconds}',
            '-c:v','libx265','-preset','ultrafast','-pix_fmt','yuv420p10le',
            '-filter_threads','2','-x265-params',options,'-color_primaries','bt2020',
            '-color_trc','smpte2084','-colorspace','bt2020nc','-color_range','tv',str(source)],
            check=True,capture_output=True,timeout=120)
        identity=(source.stat().st_size,source.stat().st_mtime_ns)
        original=hashlib.sha256(source.read_bytes()).hexdigest() if generated else None
        # Preserve the qualified CPU frame metadata baseline for this fixture.
        job.save(phase='Collecting complete CPU HDR frame baseline')
        with (args.output/'cpu-frames.json').open('xb') as out:
            subprocess.run(['ffprobe','-v','error',* ([] if generated else ['-read_intervals',str(args.start)+'%+#'+str(args.seconds*24)]),
                '-threads','4','-thread_type','slice',
                '-select_streams','V:0','-show_frames','-of','json=compact=1',str(source)],
                stdout=out,stderr=subprocess.PIPE,check=True,timeout=120)
        baseline=json.loads((args.output/'cpu-frames.json').read_text())['frames']
        if generated and len(baseline)!=args.seconds*24: raise ValueError('Generated baseline frame count wrong')
        if not all(any(x.get('side_data_type')=='Mastering display metadata' for x in f.get('side_data_list',[]))
                   for f in baseline): raise ValueError('Generated HDR baseline lost mastering metadata')
        for trial in range(args.rounds):
            for mode in (['cpu','cuda'] if trial%2==0 else ['cuda','cpu']):
                job.save(phase='Comparing '+mode+' full HDR decode evidence',
                         completed=len(rows),total=args.rounds*2,stage_percent=None)
                command=['ffmpeg','-hide_banner','-nostdin','-v','info','-xerror',
                         '-err_detect','explode','-copyts','-noautorotate','-threads','4']
                if mode=='cuda': command+=['-hwaccel','cuda','-hwaccel_output_format','cuda']
                else: command+=['-thread_type','slice']
                if not generated: command+=['-ss',str(args.start)]
                # Trim before the evidence filter: encoder EOF may request one
                # extra filter frame beyond -frames:v. Do not compare that
                # scheduling artifact as an emitted-picture count mismatch.
                suffix='trim=end_frame='+str(args.seconds*24)+',showinfo'
                graph=('hwdownload,format=p010le,format=yuv420p10le,'+suffix if mode=='cuda'
                       else 'format=yuv420p10le,'+suffix)
                command+=['-i',str(source),'-map','0:V:0','-an','-sn','-filter_threads','2',
                          '-vf',graph,'-frames:v',str(args.seconds*24),'-fps_mode','passthrough','-f','null','-']
                started=time.perf_counter()
                result=subprocess.run(command,capture_output=True,text=True,timeout=120)
                elapsed=time.perf_counter()-started
                (args.output/f'{trial}-{mode}.log').write_text(result.stderr)
                if result.returncode: raise RuntimeError(mode+' decoder failed: '+result.stderr[-2000:])
                traces[(trial,mode)]=normalized_showinfo(result.stderr)
                frames=sum(bool(re.match(r'n:\s*\d+\s+pts:',line)) for line in traces[(trial,mode)])
                rows.append(dict(round=trial,mode=mode,seconds=elapsed,frames=frames))
                if frames!=args.seconds*24: raise ValueError(mode+' full decoded frame count mismatch')
        equal=all(v==traces[(0,'cpu')] for v in traces.values())
        metadata=all(any('Mastering display metadata' in line for line in v) and
                     any('Content light level metadata' in line for line in v) for v in traces.values())
        without_chroma={k:[re.sub(r' cl:\S+', '',line) for line in v] for k,v in traces.items()}
        pixel_clock_hdr_equal=all(v==without_chroma[(0,'cpu')] for v in without_chroma.values())
        medians={m:statistics.median(r['seconds'] for r in rows if r['mode']==m) for m in ('cpu','cuda')}
        report=dict(state='passed' if equal and metadata else 'evidence-mismatch',generated_only=generated,
            gpu_validation_enabled=False,metadata_and_pixel_trace_equal=equal,
            diagnostic_equal_without_chroma_location=pixel_clock_hdr_equal,
            static_hdr_evidence_present=metadata,medians=medians,
            reduction_percent=100*(1-medians['cuda']/medians['cpu']),measurements=rows,
            source_unchanged=(hashlib.sha256(source.read_bytes()).hexdigest()==original if generated else
                              (source.stat().st_size,source.stat().st_mtime_ns)==identity),
            scope='Complete generated HDR showinfo evidence; not production JSON parity, corruption or full-file certification')
        (args.output/'benchmark.json').write_text(json.dumps(report,indent=2))
        job.save(state='completed',phase='HDR reader comparison finished',detail=json.dumps(report),finished=time.time())
        print(json.dumps(report),flush=True)
        return 0 if equal and metadata else 1
    except BaseException as exc:
        job.save(state='failed',phase='HDR qualification failed',error=str(exc),finished=time.time())
        raise
    finally:
        if generated and source.exists() and source.parent.resolve()==args.output.resolve() and not source.is_symlink():
            source.unlink()  # Exclusively generated fixture; no library input.


if __name__=='__main__': raise SystemExit(main())
