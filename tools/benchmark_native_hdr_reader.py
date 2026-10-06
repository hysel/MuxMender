"""Isolated Linux native CUDA JSON/metadata and corrupt-input qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time


def probe(binary, source, destination, cuda, *, start=None, packets=None, timeout=180, heartbeat=None):
    if not sys.platform.startswith('linux'):raise RuntimeError('Native reader probes run on Linux only')
    env=dict(os.environ, MUXMENDER_RESEARCH_CUDA_READER='1' if cuda else '0')
    command=[str(binary),'-v','error','-err_detect','explode','-threads','4',
             '-thread_type','slice','-select_streams','V:0','-show_frames','-of','json=compact=1']
    if start is not None:command+=['-read_intervals',str(start)+'%+#'+str(packets)]
    command+=[str(source)]
    before=time.perf_counter()
    stderr_path=destination.with_suffix('.stderr')
    with destination.open('xb') as out, stderr_path.open('xb') as err:
        process=subprocess.Popen(command,env=env,stdout=out,stderr=err)
        try:
            while True:
                try:
                    process.communicate(timeout=min(10,max(.1,timeout-(time.perf_counter()-before))))
                    break
                except subprocess.TimeoutExpired:
                    if time.perf_counter()-before>=timeout:raise
                    if heartbeat:heartbeat(time.perf_counter()-before,destination)
        except BaseException:
            process.kill();process.communicate();raise
    error_bytes=stderr_path.stat().st_size
    with stderr_path.open('rb') as err:
        err.seek(max(0,error_bytes-3000));errors=err.read().decode(errors='replace')
    return dict(seconds=time.perf_counter()-before,returncode=process.returncode,
                error=errors,strict_success=process.returncode==0 and error_bytes==0)


def corrupt_variants(payload):
    starts=list(re.finditer(b'\x00\x00(?:\x00)?\x01',payload))
    slices=[]
    for i,match in enumerate(starts):
        begin=match.end();end=starts[i+1].start() if i+1<len(starts) else len(payload)
        if begin+2<end and ((payload[begin]>>1)&63)<32 and end-begin>256:slices.append((begin,end))
    if len(slices)<3:raise ValueError('Generated fixture lacks bounded corruptible slices')
    variants={}
    for label,index in [('early',0),('middle',len(slices)//2),('late',len(slices)-1)]:
        begin,end=slices[index];data=bytearray(payload)
        start=begin+16;stop=min(end,start+256);data[start:stop]=b'\xff'*(stop-start)
        variants[label]=bytes(data)
        data=bytearray(payload)
        start=begin+(end-begin)*3//4;stop=min(end,start+64)
        data[start:stop]=b'\xff'*(stop-start)
        variants[label+'-entropy']=bytes(data)
    begin,end=slices[-1];variants['truncated']=payload[:begin+(end-begin)//2]
    return variants


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Native reader qualification runs on Linux only')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--start',type=int,default=600)
    p.add_argument('--packets',type=int,default=240);p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--full',action='store_true',help='After bounded qualification, read all GPU frames to EOF')
    args=p.parse_args()
    if args.start<0 or not 1<=args.packets<=2400 or not 1<=args.rounds<=5:p.error('Invalid bounded qualification settings')
    args.output.mkdir(exist_ok=False,parents=True)
    from job_tracking import Job
    from hdr10plus_preserve import frame_records
    from hdr10plus_validation import validate_frames,hdr_metadata
    job=Job(args.output/'reports','Native GPU HDR exact-metadata qualification')
    report=dict(binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),codec_name='hevc',
                production_enabled=False,exact_metadata=False,corruption_qualified=False,
                measurements=[],corruption=[])
    owned=[]
    try:
        source_stat=args.source.stat();identity=(source_stat.st_size,source_stat.st_mtime_ns)
        for trial in range(args.rounds):
            paths={}
            for cuda in ([False,True] if trial%2==0 else [True,False]):
                mode='cuda' if cuda else 'cpu';job.save(phase='Exact HDR JSON: '+mode,
                    completed=len(report['measurements']),total=args.rounds*2,stage_percent=None)
                target=args.output/f'{trial}-{mode}.json';paths[mode]=target
                result=probe(args.binary,args.source,target,cuda,start=args.start,packets=args.packets)
                report['measurements'].append(dict(mode=mode,round=trial,**result))
                if not result['strict_success']:raise ValueError(mode+' reader failed: '+result['error'])
            first=next(frame_records(paths['cpu']))
            items=hdr_metadata(first)
            mode='hdr10plus' if any('2094' in x.get('side_data_type','') or 'HDR10+' in x.get('side_data_type','') for x in items) else 'hdr10'
            proof=validate_frames(frame_records(paths['cpu']),frame_records(paths['cuda']),mode)
            report['metadata_proof']=proof
        report['exact_metadata']=True
        job.save(phase='Comparing installed CPU reader baseline',stage_percent=None)
        baseline=args.output/'installed-cpu-baseline.json'
        result=probe('ffprobe',args.source,baseline,False,start=args.start,packets=args.packets)
        report['installed_cpu_baseline']=result
        if not result['strict_success']:raise ValueError('Installed CPU baseline failed')
        report['installed_cpu_metadata_proof']=validate_frames(
            frame_records(baseline),frame_records(paths['cuda']),mode)
        report['medians']={mode:statistics.median(x['seconds'] for x in report['measurements'] if x['mode']==mode) for mode in ('cpu','cuda')}
        report['time_reduction_percent']=100*(1-report['medians']['cuda']/report['medians']['cpu'])
        job.save(phase='Generating malformed-input fixtures',stage_percent=None)
        fixture=args.output/'generated.h265';owned.append(fixture)
        subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i',
            'testsrc2=size=1280x720:rate=24:duration=2','-c:v','libx265','-preset','ultrafast',
            '-filter_threads','2','-pix_fmt','yuv420p10le','-x265-params',
            'pools=1:frame-threads=1:log-level=error:repeat-headers=1:colorprim=9:transfer=16:colormatrix=9:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):max-cll=1000,400',
            '-f','hevc',str(fixture)],check=True,capture_output=True,timeout=60)
        for cuda in (False,True):
            result=probe(args.binary,fixture,args.output/('healthy-'+str(cuda)+'.json'),cuda)
            if not result['strict_success']:raise ValueError('Healthy generated fixture rejected')
            if len(list(frame_records(args.output/('healthy-'+str(cuda)+'.json'))))!=48:
                raise ValueError('Healthy generated frame count wrong')
        report['control_passed']=True
        false_passes=[];cpu_rejections=0
        for name,data in corrupt_variants(fixture.read_bytes()).items():
            damaged=args.output/(name+'.h265');owned.append(damaged);damaged.write_bytes(data)
            job.save(phase='Testing malformed input: '+name,stage_percent=None)
            results={mode:probe(args.binary,damaged,args.output/(name+'-'+mode+'.json'),mode=='cuda')
                     for mode in ('cpu','cuda')}
            for reader in ('cpu','cuda'):
                results[reader]['frames']=len(list(frame_records(args.output/(name+'-'+reader+'.json'))))
            row=dict(case=name,cpu=results['cpu'],cuda=results['cuda'])
            report['corruption'].append(row)
            if not results['cpu']['strict_success']:cpu_rejections+=1
            if not results['cpu']['strict_success'] and results['cuda']['strict_success']:
                false_passes.append(name)
        report['cpu_corruption_rejections']=cpu_rejections
        report['corruption_qualified']=cpu_rejections>0 and not false_passes
        report['false_passes']=false_passes
        if args.full:
            if not report['corruption_qualified']:raise ValueError('Full read blocked by failed malformed-input qualification')
            target=args.output/'full-cuda.json';owned.append(target)
            def heartbeat(elapsed,path):
                job.save(phase='Whole-file GPU HDR inspection',stage_percent=None,
                    detail=f'Read-only decode to EOF: {elapsed:.0f}s elapsed; {path.stat().st_size/1048576:.1f} MiB metadata written. Not a conversion.')
            heartbeat(0,target) if target.exists() else job.save(phase='Whole-file GPU HDR inspection',stage_percent=None)
            full=probe(args.binary,args.source,target,True,timeout=1800,heartbeat=heartbeat)
            report['full_gpu_read']=full
            if not full['strict_success']:raise ValueError('Whole-file GPU reader reported errors: '+full['error'])
            job.save(phase='Checking whole-file GPU frame evidence',stage_percent=None)
            report['full_gpu_frame_consistency']=validate_frames(frame_records(target),frame_records(target),mode)
            expected=list(frame_records(baseline))
            timestamps={f['best_effort_timestamp_time'] for f in expected}
            matching=(f for f in frame_records(target) if f.get('best_effort_timestamp_time') in timestamps)
            report['full_gpu_installed_cpu_excerpt_proof']=validate_frames(iter(expected),matching,mode)
            report['full_metadata_manifest_bytes']=target.stat().st_size
            report['full_cpu_pairwise_qualification']=False
        report['source_stat_unchanged']=(args.source.stat().st_size,args.source.stat().st_mtime_ns)==identity
        report['scope']='Exact CPU/GPU excerpt validation and generated malformed fixtures'+('; whole-file GPU EOF/consistency check, not a full CPU/GPU pairwise comparison' if args.full else '; not full-file certification')
        job.save(state='completed',phase='Native GPU reader tests finished',detail=json.dumps(report),finished=time.time())
        return 0 if report['exact_metadata'] and report['corruption_qualified'] else 1
    except BaseException as exc:
        report['error']=str(exc);job.save(state='failed',phase='Native GPU reader needs investigation',error=str(exc),finished=time.time())
        raise
    finally:
        (args.output/'benchmark.json').write_text(json.dumps(report,indent=2))
        for path in owned:
            if path.parent.resolve()==args.output.resolve() and path.is_file() and not path.is_symlink():path.unlink()


if __name__=='__main__':raise SystemExit(main())
