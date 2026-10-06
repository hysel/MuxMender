"""Read-only Linux AV1 library reader qualification; never converts source media."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from fractions import Fraction
from itertools import zip_longest


def discover(job,codec='av1',prefer_short=False):
    candidates=[];hinted=[];visited=0
    for root in (Path('/media/Animation'),Path('/media/Movies'),Path('/media/TV'),Path('/media/TV Movies')):
        for directory,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
            for name in files:
                path=Path(directory)/name
                if path.suffix.lower() not in ('.mkv','.mp4','.avi') or path.is_symlink():continue
                visited+=1
                if len(candidates)<80:candidates.append(path)
                hints=('av1',) if codec=='av1' else ('hevc','h265','h.265','x265','hdr')
                if any(hint in name.lower() for hint in hints) and len(hinted)<80:hinted.append(path)
            if visited>=30000:break
        if visited>=30000:break
    checked=0;fallback=None;hdr=None
    for source in dict.fromkeys(hinted+candidates):
        checked+=1
        job.save(phase='Finding read-only '+codec.upper()+' test source',detail=f'{visited} media entries inventoried; {checked} headers checked. No source changes.')
        result=subprocess.run(['ffprobe','-v','error','-select_streams','V:0','-show_streams','-show_format','-of','json',str(source)],capture_output=True,text=True,timeout=15)
        if result.returncode or result.stderr.strip():continue
        data=json.loads(result.stdout);video=next(iter(data.get('streams',[])),{})
        if video.get('codec_name')!=codec:continue
        if video.get('color_transfer') in ('smpte2084','arib-std-b67'):
            if not prefer_short:return source,data
            duration=float(data.get('format',{}).get('duration',float('inf')))
            if hdr is None or duration<float(hdr[1]['format']['duration']):hdr=(source,data)
            if 60<=duration<=600:return source,data
        if fallback is None:fallback=(source,data)
    if hdr:return hdr
    if fallback:return fallback
    raise ValueError('Bounded library inventory found no readable '+codec.upper()+' source; no files changed')


def mode_for(path):
    from hdr10plus_preserve import frame_records
    from hdr10plus_validation import hdr_metadata
    transfers=set();static=dynamic=False
    for frame in frame_records(path):
        transfers.add(frame.get('color_transfer'))
        for item in hdr_metadata(frame):
            name=item.get('side_data_type','')
            static=static or name=='Mastering display metadata'
            dynamic=dynamic or '2094-40' in name or 'HDR10+' in name
    if transfers=={'smpte2084'}:return 'hdr10plus' if dynamic else 'hdr10' if static else 'pq'
    if transfers=={'arib-std-b67'}:return 'hlg'
    if transfers & {'smpte2084','arib-std-b67'}:raise ValueError('Mixed HDR transfer in source frame evidence')
    return 'sdr'


def compare(cpu,gpu):
    from hdr10plus_preserve import frame_records
    from hdr10plus_validation import validate_frames
    mode=mode_for(cpu)
    if mode!='sdr':
        proof=validate_frames(frame_records(cpu),frame_records(gpu),mode)
        # The ordinary preservation validator allows container rounding. Reader
        # qualification requires exact timestamps, without another manifest pass.
        if proof['frame_timestamps_exact'] is not True:
            raise ValueError('Reader timestamp is not exact')
        return proof
    for a,b in zip_longest(frame_records(cpu),frame_records(gpu)):
        if a is None or b is None:raise ValueError('Reader frame count changed')
        if a.get('chroma_location')!=b.get('chroma_location'):raise ValueError('Reader chroma location changed')
        if Fraction(a['best_effort_timestamp_time'])!=Fraction(b['best_effort_timestamp_time']):
            raise ValueError('Reader timestamp is not exact')
    from auto_optimize import compare_frame_rows
    def rows(path):
        for frame in frame_records(path):
            record=dict(frame)
            for key in ('interlaced_frame','top_field_first','repeat_pict'):
                if key in record:record[key]=str(record[key])
            record['side_data_type']=' '.join(s.get('side_data_type','') for s in record.get('side_data_list',[]))
            yield record
    count=compare_frame_rows(rows(cpu),rows(gpu))
    return dict(mode=mode,frames=count,shared_validation_passed=True,chroma_exact=True,timestamps_exact=True,
        quality_approved=False,replacement_authorized=False)


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Real AV1 reader research runs on Linux only')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--full',action='store_true')
    p.add_argument('--codec',choices=('av1','hevc'),default='av1')
    p.add_argument('--source',type=Path,help='Private explicit read-only /media source instead of inventory selection')
    p.add_argument('--prefer-short',action='store_true',help='Prefer a shorter HDR source from the bounded inventory')
    p.add_argument('--reader-timeout',type=int,default=5400,help='Research-only limit in seconds for each whole-file reader')
    args=p.parse_args()
    if args.reader_timeout<=0:p.error('--reader-timeout must be positive')
    args.output.mkdir(parents=True,exist_ok=False)
    from job_tracking import Job
    from benchmark_native_hdr_reader import probe
    from task_progress import probe_status
    label=args.codec.upper()
    job=Job(args.output/'reports','Real '+label+' GPU reader · read-only qualification')
    report=dict(binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                production_enabled=False,source_changed=False,measurements=[])
    owned=[]
    try:
        if args.source is None:
            source,data=discover(job,args.codec,args.prefer_short)
        else:
            source=args.source.resolve(strict=True)
            if not source.is_relative_to(Path('/media').resolve()) or not source.is_file():
                raise ValueError('Explicit research source must be a read-only /media file')
            header=subprocess.run(['ffprobe','-v','error','-select_streams','V:0','-show_streams','-show_format','-of','json',str(source)],
                                  capture_output=True,text=True,timeout=30)
            if header.returncode or header.stderr.strip():raise ValueError('Explicit source header could not be read cleanly')
            data=json.loads(header.stdout)
            if next(iter(data.get('streams',[])),{}).get('codec_name')!=args.codec:
                raise ValueError('Explicit source codec does not match the requested research scope')
        stat=source.stat()
        identity=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)
        video=data['streams'][0];duration=float(data['format']['duration']);start=float(data['format'].get('start_time',0))
        report['source']=dict(path_token=hashlib.sha256(str(source).encode()).hexdigest(),bytes=stat.st_size,duration=duration,
            **{k:video.get(k) for k in ('codec_name','width','height','pix_fmt','color_transfer')})
        for number,position in enumerate((0,int(duration/2),max(0,int(duration-20)))):
            paths={}
            for mode in (('cpu','cuda') if number%2==0 else ('cuda','cpu')):
                target=args.output/f'excerpt-{number}-{mode}.json';owned.append(target);paths[mode]=target
                job.save(phase='Real '+label+' excerpt: '+mode,stage_percent=None,detail=f'Checking excerpt {number+1} of 3')
                result=probe('ffprobe' if mode=='cpu' else args.binary,source,target,mode=='cuda',start=position,packets=240)
                report['measurements'].append(dict(excerpt=number,mode=mode,**result))
                if not result['strict_success']:raise ValueError('Real AV1 '+mode+' reader failed: '+result['error'])
            report.setdefault('excerpt_proofs',[]).append(compare(paths['cpu'],paths['cuda']))
        report['medians']={mode:statistics.median(r['seconds'] for r in report['measurements'] if r['mode']==mode) for mode in ('cpu','cuda')}
        if args.full:
            paths={}
            for mode in ('cpu','cuda'):
                target=args.output/('full-'+mode+'.json');owned.append(target);paths[mode]=target
                def heartbeat(elapsed,path):
                    percent,detail=probe_status(path,duration,start)
                    job.save(phase='Whole-file real '+label+' inspection: '+mode,stage_percent=percent,
                        stage_eta=elapsed*(100-percent)/percent if percent is not None and 0<percent<100 and elapsed>=5 else None,
                        stage_updated=time.time() if percent is not None else None,detail=detail+f' · {elapsed:.0f}s elapsed; read-only')
                job.save(phase='Whole-file real '+label+' inspection: '+mode,stage_percent=None)
                result=probe('ffprobe' if mode=='cpu' else args.binary,source,target,mode=='cuda',timeout=args.reader_timeout,heartbeat=heartbeat)
                report.setdefault('full_reads',{})[mode]=result
                if not result['strict_success']:raise ValueError('Full real AV1 reader failed: '+mode+' '+result['error'])
            job.save(phase='Comparing every real '+label+' CPU/GPU frame',stage_percent=None)
            report['full_pairwise_proof']=compare(paths['cpu'],paths['cuda'])
            report['full_time_reduction_percent']=100*(1-report['full_reads']['cuda']['seconds']/report['full_reads']['cpu']['seconds'])
        stat=source.stat();report['source_changed']=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)!=identity
        if report['source_changed']:raise ValueError('Source identity changed during read-only research')
        if hashlib.sha256(args.binary.read_bytes()).hexdigest()!=report['binary_sha256']:
            raise ValueError('Reader build changed during qualification')
        report['scope']='Read-only real '+label+' excerpts'+('; full EOF and every-frame CPU/GPU comparison' if args.full else '')+'; not perceptual quality or replacement authorization'
        job.save(state='completed',phase='Real '+label+' reader qualification passed',detail=json.dumps(report),finished=time.time())
        return 0
    except Exception as exc:
        report['error']=str(exc);job.save(state='failed',phase='Real '+label+' reader needs investigation',error=str(exc),detail=json.dumps(report),finished=time.time())
        return 1
    finally:
        removed=0
        for path in owned:
            if path.parent.resolve()==args.output.resolve() and path.is_file() and not path.is_symlink():
                removed+=path.stat().st_size;path.unlink()
        report['metadata_bytes_removed']=removed
        (args.output/'benchmark.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':raise SystemExit(main())
