"""Linux-only generated SDR reader parity, corruption and timing experiment.

Exercises the shared SDR command policy. Does not install a receipt, modify
production, open library media, or authorize replacement. Run with the GPU idle.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))


def file_digest(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def complete_control(result,frames,expected_frames):
    """Report decoder errors separately from known-fixture completeness failures."""
    if type(expected_frames) is not int or expected_frames<=0:
        raise ValueError('Healthy control must establish a nonempty frame count')
    return dict(result,frames=frames,decoder_clean=result['strict_success'],
        complete_frame_count=frames==expected_frames,
        strict_success=result['strict_success'] and frames==expected_frames)


def exact_pair(left,right):
    from auto_optimize import compact_rows,compare_frame_rows
    count=0
    required={'best_effort_timestamp_time','width','height','pix_fmt','interlaced_frame','repeat_pict'}
    for a,b in itertools.zip_longest(compact_rows(left,'width'),compact_rows(right,'width')):
        if a is None or b is None or not required<=a.keys() or a!=b:
            raise ValueError('CPU/GPU frame evidence differs at frame '+str(count+1))
        # Retain the production parser's SDR, scan, color and geometry checks.
        compare_frame_rows(iter([a]),iter([b]))
        count+=1
    if not count:raise ValueError('No decoded frame evidence')
    return dict(frames=count,every_field_exact=True,frame_timestamps_exact=True)


def read(command,options,destination,job,timeout,duration=61,backend=None):
    if not sys.platform.startswith('linux'):raise RuntimeError('Native reader tests run on Linux only')
    from task_progress import run_probe
    from job_tracking import isolated_progress
    started=time.monotonic();error=None
    try:
        with isolated_progress(lambda values:job.save(**values)):
            label='Inspecting complete SDR frames'+(' · '+backend.upper() if backend else '')
            run_probe(command,destination,label,timeout,lambda:None,duration,0,**options)
    except (subprocess.SubprocessError,ValueError,RuntimeError) as exc:error=str(exc)
    errors=destination.with_suffix(destination.suffix+'.stderr')
    error_bytes=errors.stat().st_size if errors.exists() else None
    error_tail=''
    if error_bytes:
        with errors.open('rb') as stream:
            stream.seek(max(0,error_bytes-2000));error_tail=stream.read().decode(errors='replace')
    return dict(seconds=time.monotonic()-started,strict_success=error is None and error_bytes==0,
                error=error,stderr_bytes=error_bytes,stderr_tail=error_tail)


def hevc_container_controls(source,root,owned):
    """Mutate generated coded packets, keeping a valid Matroska envelope."""
    import av
    with av.open(str(source)) as inp:
        packets=[bytes(p) for p in inp.demux(video=0) if p.size]
    if len(packets)<3:raise ValueError('Insufficient generated packets')
    variants=[('healthy',None,None)]
    for name,index in [('early',0),('middle',len(packets)//2),('late',len(packets)-1)]:
        for location in ('header','entropy'):variants.append((name+'-'+location,index,location))
    variants.append(('truncated',len(packets)-1,'truncated'))
    results=[]
    for name,index,location in variants:
        target=root/(name+'.mkv');owned.append(target)
        with av.open(str(source)) as inp,av.open(str(target),'w',format='matroska') as out:
            stream=out.add_stream_from_template(inp.streams.video[0]);number=0
            for original in inp.demux(video=0):
                if not original.size:continue
                data=bytes(original)
                if number==index:
                    if len(data)<256:raise ValueError('Generated packet too small for distributed damage')
                    if location=='truncated':data=data[:len(data)//2]
                    elif location=='header':
                        # Length-prefixed HEVC: corrupt an actual VCL NAL's
                        # forbidden_zero_bit, not an arbitrary byte that could
                        # remain legal coded content or non-picture metadata.
                        offset=0
                        while offset+6<=len(data):
                            size=int.from_bytes(data[offset:offset+4],'big')
                            if size<2 or offset+4+size>len(data):
                                raise ValueError('Invalid generated HEVC NAL framing')
                            if ((data[offset+4]>>1)&63)<=31:
                                data=data[:offset+4]+bytes([data[offset+4]|128])+data[offset+5:]
                                break
                            offset+=4+size
                        else:raise ValueError('Generated packet has no VCL NAL')
                    else:
                        start=len(data)*3//4
                        data=data[:start]+b'\xff'*min(64,len(data)-start)+data[min(start+64,len(data)):]
                packet=av.Packet(data);packet.pts=original.pts;packet.dts=original.dts
                packet.duration=original.duration;packet.time_base=original.time_base;packet.stream=stream
                out.mux(packet);number+=1
        results.append((name,target))
    return results


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('SDR reader research runs on Linux only')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--codec',choices=('av1','hevc'),default='av1')
    p.add_argument('--pixel-format',choices=('yuv420p','yuv420p10le'),default='yuv420p10le')
    p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--ffprobe',default='ffprobe')
    p.add_argument('--source-plan',type=Path,help='Read-only full-source comparison using an existing approved job plan')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    from gpu_frame_reader import sdr_reader_request
    from job_tracking import Job
    from encoder_capabilities import nvidia_adapters
    job=Job(args.output/'reports','Generated SDR GPU reader comparison')
    report=dict(production_enabled=False,qualification_installed=False,scope='Generated SDR controls only',
        binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),codec=args.codec,pixel_format=args.pixel_format,
        adapters=nvidia_adapters(),visibility={k:os.environ.get(k) for k in ('CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER')})
    owned=[];failed=False
    try:
        report['cpu_version']=subprocess.check_output([args.ffprobe,'-version'],text=True,timeout=15).splitlines()[0]
        report['generator_version']=subprocess.check_output([args.ffmpeg,'-version'],text=True,timeout=15).splitlines()[0]
        video=dict(codec_name=args.codec,pix_fmt=args.pixel_format,width=1920,height=1080)
        # Research-only injection, never written as a production qualification.
        profile=dict(binary=str(args.binary.resolve()),scopes=[dict(codec=args.codec,pixel_format=args.pixel_format,
            hdr_modes=['sdr'],full_eof=True,every_frame_cpu_gpu_equal=True,corrupt_controls_rejected=True,time_reduction_percent=1)])
        fixture=args.output/'generated-sdr.mkv';owned.append(fixture)
        job.save(phase='Generating 61-second SDR fixture')
        subprocess.run([args.ffmpeg,'-v','error','-nostdin','-n','-filter_threads','2','-f','lavfi','-i',
            'testsrc2=size=1920x1080:rate=24:duration=61,format='+args.pixel_format,
            '-c:v',args.codec+'_nvenc','-preset','p4','-cq','24','-pix_fmt',args.pixel_format,
            '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',str(fixture)],
            check=True,capture_output=True,timeout=180)
        inspected=fixture;duration=61;container_name='matroska,webm';rounds=3
        if args.source_plan:
            inspected=Path(json.loads(args.source_plan.read_text())['source'])
            if not inspected.is_file():raise ValueError('Approved source is unavailable')
            metadata=json.loads(subprocess.check_output([args.ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(inspected)],text=True,timeout=60))
            from auto_optimize import main_video
            actual=main_video(metadata)
            if actual.get('codec_name')!=args.codec or actual.get('pix_fmt')!=args.pixel_format:
                raise ValueError('Source does not match requested codec/pixel scope')
            if actual.get('color_transfer') in ('smpte2084','arib-std-b67') or actual.get('side_data_list'):
                raise ValueError('Full-source SDR test requires unambiguous SDR without HDR side data')
            video=actual;duration=float(metadata['format']['duration']);container_name=metadata['format']['format_name'];rounds=1
            report['scope']='Read-only complete approved SDR source and generated controls'
            report['source']={k:actual.get(k) for k in ('codec_name','pix_fmt','width','height','color_transfer')}
            report['source_bytes']=inspected.stat().st_size
            report['duration_seconds']=duration
            report['source_container']=container_name
        job.save(phase='Hashing read-only source before comparison')
        source_hash=file_digest(inspected);report['source_sha256_before']=source_hash;report['measurements']=[]
        for trial in range(rounds):
            paths={}
            for backend in (('cpu','cuda') if trial%2==0 else ('cuda','cpu')):
                command,options,plan=sdr_reader_request(args.ffprobe,inspected,video,duration,profile if backend=='cuda' else None,container=container_name)
                if plan['backend']!=backend:raise ValueError('Unexpected backend')
                path=args.output/f'{trial}-{backend}.frames';paths[backend]=path;owned.extend([path,path.with_suffix(path.suffix+'.stderr')])
                job.save(phase=f'Round {trial+1}: {backend} full reader')
                result=read(command,options,path,job,max(180,duration*2),duration,backend)
                report['measurements'].append(dict(trial=trial,backend=backend,**result))
                if not result['strict_success']:raise ValueError('Healthy reader failed: '+backend)
            proof=exact_pair(paths['cpu'],paths['cuda'])
            if not args.source_plan and proof['frames']!=1464:raise ValueError('Generated frame count changed')
            report['exact_pairwise_proof']=proof
        if args.codec=='hevc':
            short=args.output/'short-control.mkv';owned.append(short)
            subprocess.run([args.ffmpeg,'-v','error','-nostdin','-n','-i',str(fixture),'-t','2','-map','0:V:0','-c','copy',str(short)],check=True,capture_output=True,timeout=60)
            controls=hevc_container_controls(short,args.output,owned)
            raw=controls[0][1];damaged_controls=controls[1:];container='matroska,webm'
        else:
            raw=args.output/'generated.obu';owned.append(raw)
            subprocess.run([args.ffmpeg,'-v','error','-nostdin','-n','-i',str(fixture),'-t','2','-map','0:V:0','-c','copy',str(raw)],check=True,capture_output=True,timeout=60)
            from benchmark_native_av1_reader import corrupt_variants
            damaged_controls=[];container='obu'
            for name,payload in corrupt_variants(raw.read_bytes()).items():
                damaged=args.output/(name+'.obu');owned.append(damaged);damaged.write_bytes(payload)
                damaged_controls.append((name,damaged))
        # Healthy elementary-stream controls prevent mistaking unsupported input for corruption rejection.
        report['raw_healthy']={}
        from auto_optimize import compact_rows
        for backend in ('cpu','cuda'):
            command,options,plan=sdr_reader_request(args.ffprobe,raw,video,61,profile if backend=='cuda' else None,container=container)
            if plan['backend']!=backend:raise ValueError('Control did not use requested reader')
            path=args.output/('healthy-'+backend+'.frames');owned.extend([path,path.with_suffix(path.suffix+'.stderr')])
            result=read(command,options,path,job,60)
            result['frames']=sum(1 for _ in compact_rows(path,'width'))
            report['raw_healthy'][backend]=result
            if not result['strict_success'] or result['frames']==0:raise ValueError('Healthy elementary stream failed or emitted no frames: '+backend)
        if report['raw_healthy']['cpu']['frames']!=report['raw_healthy']['cuda']['frames']:
            raise ValueError('Healthy elementary-stream frame counts differ')
        report['corruption']=[]
        for name,damaged in damaged_controls:
            results={}
            for backend in ('cpu','cuda'):
                command,options,plan=sdr_reader_request(args.ffprobe,damaged,video,61,profile if backend=='cuda' else None,container=container)
                if plan['backend']!=backend:raise ValueError('Damaged control did not use requested reader')
                path=args.output/(name+'-'+backend+'.frames');owned.extend([path,path.with_suffix(path.suffix+'.stderr')])
                results[backend]=read(command,options,path,job,60)
                # A decoder can silently discard a malformed terminal packet.
                # Production also checks complete frame/timing evidence; exit
                # status alone must never certify the damaged control.
                results[backend]=complete_control(results[backend],
                    sum(1 for _ in compact_rows(path,'width')),report['raw_healthy'][backend]['frames'])
            report['corruption'].append(dict(case=name,**results))
        report['false_passes']=[c['case'] for c in report['corruption'] if c['cuda']['strict_success']]
        if report['false_passes']:raise ValueError('A damaged input escaped the GPU reader')
        job.save(phase='Verifying read-only source hash after comparison')
        report['source_sha256_after']=file_digest(inspected)
        if report['source_sha256_after']!=source_hash:raise ValueError('Source changed')
        report['source_unchanged']=True
        medians={mode:statistics.median(r['seconds'] for r in report['measurements'] if r['backend']==mode) for mode in ('cpu','cuda')}
        report.update(medians=medians,time_reduction_percent=100*(1-medians['cuda']/medians['cpu']),controls_passed=True)
    except Exception as exc:
        failed=True;report.update(error=str(exc),controls_passed=False)
    finally:
        try:
            # Only exact generated files created by this invocation; no recursive deletion.
            removed=0
            for path in owned:
                if path.parent.resolve()!=args.output.resolve() or path.is_symlink():raise ValueError('Unsafe cleanup target')
                if path.is_file():removed+=path.stat().st_size;path.unlink()
            report['temporary_bytes_removed']=removed
            (args.output/'benchmark.json').write_text(json.dumps(report,indent=2))
        except Exception as exc:failed=True;report['cleanup_error']=str(exc)
        job.save(state='failed' if failed else 'completed',phase='SDR controls need investigation' if failed else 'Generated SDR checks completed',detail=json.dumps(report),finished=time.time())
    return 1 if failed else 0


if __name__=='__main__':raise SystemExit(main())
