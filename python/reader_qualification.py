"""First-use GPU inspection checks, using an already required full CPU reference.

This does not approve encodes or replacements. Every media validation gate stays
in the shared workflow. No administrator helper, host mount or external model.
"""
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from job_tracking import progress
from app_version import VERSION as APP_VERSION
from reader_qualification_cache import cache_root,identity,read_record,write_record,exclusive_check,verified_profile,MAXIMUM_PAIRS


class SourceChangedDuringQualification(RuntimeError):
    pass


def fallback_record(exc):
    diagnostic=(str(exc).strip() or type(exc).__name__)[:400]
    if diagnostic=='No measured whole-file speed benefit':reason='CPU inspection was faster in this comparison.'
    elif isinstance(exc,PermissionError) or 'cache' in diagnostic.lower():reason='GPU check results could not be stored securely. Inspection stays on the CPU.'
    elif 'damaged' in diagnostic.lower():reason='The GPU reader did not pass the damaged-clip self-test.'
    elif 'differ' in diagnostic.lower() or 'metadata changed' in diagnostic.lower():reason='GPU inspection did not match the complete CPU reference.'
    else:reason='GPU compatibility checks could not complete. Inspection stays on the CPU.'
    return dict(state='cpu_fallback',reason=reason,diagnostic=diagnostic)


def source_identity(source):
    s=Path(source).stat()
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def eligible(video,mode,duration,container):
    from gpu_frame_reader import NATIVE_DEMUXERS
    if not isinstance(video,dict):return False
    side_data=video.get('side_data_list') or []
    if not isinstance(side_data,list):return False
    pixels=('yuv420p','yuv420p10le') if mode=='sdr' else ('yuv420p10le',)
    return (isinstance(video,dict) and video.get('codec_name') in ('hevc','av1') and
        video.get('pix_fmt') in pixels and mode in ('sdr','hdr10','hdr10plus','pq','hlg') and
        type(duration) in (float,int) and math.isfinite(duration) and duration>=60 and
        isinstance(container,str) and bool(container) and set(container.split(','))<=NATIVE_DEMUXERS and
        not any(any(word in str(s.get('side_data_type','')).lower() for word in ('dovi','dolby','display matrix'))
                for s in side_data if isinstance(s,dict)))


def command(binary,source,mode,decoder_options=(),gpu=False):
    from gpu_frame_reader import SDR_FRAME_FIELDS
    from decoder_context import metadata_reader_options
    args=[str(binary),'-v','error',*(['-err_detect','explode'] if gpu else []),
        *metadata_reader_options(2),'-select_streams','V:0','-show_frames']
    args+=['-show_entries','frame='+SDR_FRAME_FIELDS,'-of','compact=p=0'] if mode=='sdr' else ['-of','json=compact=1']
    return [*args,*decoder_options,str(source)]


def compare(left,right,mode,guard):
    from hdr10plus_preserve import frame_records
    from hdr10plus_validation import validate_frames
    from auto_optimize import compact_rows,compare_frame_rows
    def checked(rows):
        reported=time.monotonic()
        for number,row in enumerate(rows):
            if number%4096==0:
                guard()
                if time.monotonic()-reported>=5:
                    progress('Comparing every CPU/GPU frame',completed=number,unit='frames',
                        detail=f'{number:,} frames checked; all timing and metadata fields must match')
                    reported=time.monotonic()
            yield row
    if mode!='sdr':
        result=validate_frames(checked(frame_records(left)),frame_records(right),mode)
        if result['frame_timestamps_exact'] is not True:raise ValueError('GPU reader timestamps differ')
        return result
    def equal_rows():
        for a,b in itertools.zip_longest(checked(compact_rows(left,'width')),compact_rows(right,'width')):
            if a is None or b is None or a!=b:raise ValueError('GPU reader frame fields differ')
            yield a
    # The exact comparison and ordinary geometry/monotonic-clock checks are both
    # streaming, not a permissive comparison of selected sample frames.
    count=compare_frame_rows(equal_rows(),compact_rows(right,'width'))
    return dict(frames=count,mode='sdr',every_field_exact=True,frame_timestamps_exact=True,
        frame_timing_preserved=True,geometry_color_exact=True,max_timestamp_delta_seconds=0)


def read_frames(binary,source,target,mode,gpu,guard,timeout,duration,decoder_options=(),video=None,negative=False):
    from gpu_frame_reader import reader_environment
    from task_progress import run_probe
    from artifact_manifest import command_outputs
    from gpu_admission import stage_context
    stderr=target.with_suffix(target.suffix+'.stderr')
    options=dict(env=reader_environment()) if gpu else {}
    if negative:options['expected_fixture_rejection']=True
    try:
        with command_outputs(target.parent,[str(target),str(stderr)]),stage_context(video):
            result=run_probe(command(binary,source,mode,decoder_options,gpu),target,
                'Checking GPU compatibility: '+('GPU' if gpu else 'CPU')+' reference',
                timeout,guard,duration,**options)
        return result
    except subprocess.CalledProcessError as exc:
        return dict(strict_success=False,returncode=exc.returncode,error='Decoder rejected input',seconds=0)


def generate(ffmpeg,target,codec,pixels,hdr,guard):
    """Small deterministic, CPU-encoded controls work without NVENC support."""
    if not sys.platform.startswith('linux'):raise RuntimeError('GPU qualification runs inside Linux containers only')
    color=('bt2020','smpte2084','bt2020nc') if hdr else ('bt709','bt709','bt709')
    options=(['-c:v','libx265','-preset','ultrafast','-x265-params',
        'pools=1:frame-threads=1:log-level=error:repeat-headers=1'+
        (':colorprim=9:transfer=16:colormatrix=9:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):max-cll=1000,400' if hdr
         else ':colorprim=1:transfer=1:colormatrix=1')]
        if codec=='hevc' else ['-c:v','libaom-av1','-cpu-used','8','-threads','2','-row-mt','1'])
    args=[ffmpeg,'-v','error','-nostdin','-n','-filter_threads','2','-f','lavfi','-i',
        'testsrc2=size=1280x720:rate=24:duration=2,format='+pixels+
        ',setparams=range=limited:color_primaries='+color[0]+':color_trc='+color[1]+':colorspace='+color[2],
        *options,'-pix_fmt',pixels,'-color_primaries',color[0],'-color_trc',color[1],
        '-colorspace',color[2],'-color_range','tv',str(target)]
    run_generated(args,target,guard)


def run_generated(args,target,guard):
    if not sys.platform.startswith('linux'):raise RuntimeError('GPU controls run on Linux only')
    from validation_resources import validation_slot
    with validation_slot(args,guard,pool='validation'),target.with_suffix(target.suffix+'.log').open('xb') as log:
        child=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=log)
        start=time.monotonic()
        reported=start
        try:
            while child.poll() is None:
                guard()
                if time.monotonic()-start>90:raise TimeoutError('Generated GPU control timed out')
                if time.monotonic()-reported>=5:
                    progress('Generating GPU compatibility controls',detail=f'{int(time.monotonic()-start)} seconds elapsed; original media is unchanged')
                    reported=time.monotonic()
                time.sleep(.1)
            if child.returncode:raise ValueError('Cannot generate GPU compatibility controls')
        except BaseException:
            child.kill();child.wait();raise


def damaged_controls(source,root,codec,guard,ffmpeg='ffmpeg'):
    """Copy generated packets; preserve the envelope around distributed damage."""
    if codec=='av1':
        # The muxer correctly refuses invalid AV1 OBUs. Test those bytes through
        # the native OBU demuxer instead, with its own healthy-completeness check.
        raw=root/'healthy.obu'
        run_generated([ffmpeg,'-v','error','-nostdin','-n','-i',str(source),'-map','0:V:0','-c','copy','-f','obu',str(raw)],raw,guard)
        if raw.stat().st_size>32*1024*1024:raise ValueError('GPU control exceeds its generated-data budget')
        data=raw.read_bytes()
        from av1_content_light import obus
        offset=0;frames=[]
        for kind,packet,body in obus(data):
            end=offset+len(packet)
            if kind in (4,6) and len(body)>256:frames.append((end-len(body),end))
            offset=end
        if len(frames)<3:raise ValueError('Insufficient generated AV1 pictures')
        yield 'remux-healthy',raw
        for where,index in (('early',0),('middle',len(frames)//2),('late',len(frames)-1)):
            begin,end=frames[index]
            for part,position in (('header',begin+8),('entropy',begin+(end-begin)*3//4)):
                guard();changed=bytearray(data);stop=min(end,position+128)
                changed[position:stop]=bytes([255])*(stop-position)
                path=root/(where+'-'+part+'.obu');path.write_bytes(changed)
                yield where+'-'+part,path
        begin,end=frames[-1];path=root/'truncated.obu';path.write_bytes(data[:begin+(end-begin)//2])
        yield 'truncated',path
        return
    import av
    with av.open(str(source)) as inp:count=sum(1 for p in inp.demux(video=0) if p.size)
    if count<3:raise ValueError('Insufficient generated control packets')
    variants=[('remux-healthy',None,None)]+[(where+'-'+part,index,part) for where,index in
        (('early',0),('middle',count//2),('late',count-1)) for part in ('header','entropy')]
    variants.append(('truncated',count-1,'truncated'))
    for name,index,part in variants:
        guard();target=root/(name+'.mkv')
        with av.open(str(source)) as inp,av.open(str(target),'w',format='matroska') as out:
            stream=out.add_stream_from_template(inp.streams.video[0],opaque=True)
            stream.time_base=inp.streams.video[0].time_base;number=0
            for original in inp.demux(video=0):
                if not original.size:continue
                data=bytes(original)
                if number==index:
                    if len(data)<256:raise ValueError('Generated control packet is too small')
                    if part=='truncated':data=data[:len(data)//2]
                    elif part=='entropy':
                        start=len(data)*3//4;end=min(len(data),start+128)
                        data=data[:start]+bytes([255])*(end-start)+data[end:]
                    elif codec=='hevc':
                        offset=0
                        while offset+6<=len(data):
                            size=int.from_bytes(data[offset:offset+4],'big')
                            if size<2 or offset+4+size>len(data):raise ValueError('Invalid generated NAL')
                            if ((data[offset+4]>>1)&63)<=31:
                                data=data[:offset+4]+bytes([data[offset+4]|128])+data[offset+5:];break
                            offset+=4+size
                        else:raise ValueError('No generated picture NAL')
                packet=av.Packet(data);packet.pts=original.pts;packet.dts=original.dts
                packet.duration=original.duration;packet.time_base=original.time_base
                packet.is_keyframe=original.is_keyframe;packet.stream=stream
                out.mux(packet);number+=1
        yield name,target


def controls(context,ffmpeg,ffprobe,video,mode,root,guard):
    from auto_optimize import compact_rows
    from hdr10plus_preserve import frame_records
    fixture=root/'healthy.mkv';codec=video['codec_name'];pixels=video['pix_fmt']
    generate(ffmpeg,fixture,codec,pixels,mode!='sdr',guard)
    variants=list(damaged_controls(fixture,root,codec,guard,ffmpeg))
    healthy_source=variants.pop(0)[1]
    testmode='sdr' if mode=='sdr' else 'hdr10' if codec=='hevc' else 'pq'
    control_video=dict(codec_name=codec,pix_fmt=pixels,width=1280,height=720,avg_frame_rate='24/1',
        field_order='progressive',color_transfer='bt709' if mode=='sdr' else 'smpte2084')
    paths={};healthy={}
    for backend,binary in (('cpu',ffprobe),('cuda',context['binary'])):
        path=root/('healthy-'+backend+'-frames.jsonl');paths[backend]=path
        row=read_frames(binary,fixture if codec=='av1' else healthy_source,path,testmode,backend=='cuda',guard,90,2,video=control_video)
        if not row or not row['strict_success']:raise ValueError('Healthy GPU control failed')
        healthy[backend]=dict(row,frames=sum(1 for _ in (compact_rows(path,'width') if testmode=='sdr' else frame_records(path))))
    proof=compare(paths['cpu'],paths['cuda'],testmode,guard)
    if proof['frames']!=48:raise ValueError('Healthy GPU control lost frames')
    if codec=='av1':
        for backend,binary in (('cpu',ffprobe),('cuda',context['binary'])):
            path=root/('raw-healthy-'+backend+'-frames.jsonl')
            row=read_frames(binary,healthy_source,path,testmode,backend=='cuda',guard,90,2,video=control_video)
            records=compact_rows(path,'width') if testmode=='sdr' else frame_records(path)
            count=0
            for frame in records:
                if frame.get('pix_fmt')!=pixels or int(frame['width'])!=1280 or int(frame['height'])!=720:
                    raise ValueError('Healthy elementary-stream control changed geometry')
                count+=1
            if not row['strict_success'] or count!=48:raise ValueError('Healthy elementary-stream GPU control failed')
            healthy[backend]=dict(row,frames=count)
    cases=[]
    for name,source in variants:
        path=root/(name+'-frames.jsonl')
        row=read_frames(context['binary'],source,path,testmode,True,guard,90,2,video=control_video,negative=True)
        if row.get('returncode') not in (0,1):raise ValueError('GPU control terminated abnormally; compatibility is unproven')
        try:frames=sum(1 for _ in (compact_rows(path,'width') if testmode=='sdr' else frame_records(path)))
        except (OSError,ValueError):frames=0
        row=dict(row,frames=frames,decoder_clean=row['strict_success'],
            strict_success=row['strict_success'] and frames==48)
        if row['strict_success']:raise ValueError('Damaged GPU control was not rejected: '+name)
        cases.append(dict(case=name,cuda=row))
    return dict(binary_sha256=context['binding']['binary_sha256'],codec_name=codec,
        pixel_format=pixels,healthy=healthy,healthy_metadata_proof=proof,
        control_passed=True,corruption=cases,false_passes=[])


def qualify(source,reference,video,mode,container,duration,cpu_result,before,workroot,
            ffmpeg,ffprobe,timeout,guard,decoder_options=(),reader_root=None,storage=None):
    """Return computed evidence only; optional acceleration failure keeps CPU work."""
    if not sys.platform.startswith('linux') or not eligible(video,mode,duration,container):return None
    if not isinstance(cpu_result,dict) or cpu_result.get('strict_success') is not True:return None
    from gpu_frame_reader import READER_ROOT,select_reader
    from gpu_reader_receipt import qualified_scope
    if source_identity(source)!=before:raise SourceChangedDuringQualification('Source changed during CPU reference inspection')
    reader_root=READER_ROOT if reader_root is None else Path(reader_root)
    context=identity(reader_root)
    if context is None:return None
    import shutil
    if Path(shutil.which(str(ffprobe)) or str(ffprobe)).resolve()!=Path(context['cpu_binary']).resolve():return None
    storage=cache_root() if storage is None else Path(storage)
    scope_key=hashlib.sha256(json.dumps([video.get('codec_name'),video.get('pix_fmt'),mode,container]).encode()).hexdigest()
    try:
        with exclusive_check(storage) as acquired:
            if not acquired:
                progress('GPU compatibility check already running',detail='Continuing with the completed CPU reference')
                return None
            try:record=read_record(storage,context['key'])
            except (OSError,ValueError):record={}
            try:
                existing=verified_profile(context,record)
                if select_reader(video,duration,mode,existing,container=container)['backend']=='cuda':return existing
            except (ValueError,TypeError,KeyError):pass
            failures=record.get('failures',{})
            failure=failures.get(scope_key,{}) if isinstance(failures,dict) else {}
            failure=failure if isinstance(failure,dict) else {}
            retry=failure.get('retry_after')
            if (failure.get('app_version')==APP_VERSION and type(retry) in (int,float)
                    and math.isfinite(retry) and 0<retry-time.time()<=86400):
                progress('Using CPU inspection',detail='A GPU compatibility check did not pass; it will be retried automatically later',
                    reader_qualification=dict(state='cpu_fallback',reason='Compatibility controls did not pass; automatic retry is scheduled',retry_after=retry))
                return None
            progress('Checking GPU compatibility',detail='One-time check: complete CPU/GPU comparison and generated damaged-input controls. Originals are unchanged.')
            with tempfile.TemporaryDirectory(prefix='reader-check-',dir=workroot) as temporary:
                root=Path(temporary)
                try:damaged=controls(context,ffmpeg,ffprobe,video,mode,root,guard)
                except InterruptedError:raise
                except (OSError,ValueError,subprocess.SubprocessError) as exc:
                    guard()
                    failures=record.get('failures',{})
                    failures=failures if isinstance(failures,dict) else {}
                    record['failures']={**dict(list(failures.items())[-15:]),scope_key:dict(retry_after=time.time()+86400,app_version=APP_VERSION)}
                    write_record(storage,context['key'],record)
                    raise
                target=root/'comparison-frames.jsonl'
                result=read_frames(context['binary'],source,target,mode,True,guard,timeout,duration,decoder_options,video)
                if result['strict_success'] is not True:raise ValueError('Complete GPU comparison failed')
                progress('Comparing every CPU/GPU frame',detail='No sampled frames or relaxed timing tolerances')
                proof=compare(reference,target,mode,guard)
                guard()
                if source_identity(source)!=before:raise SourceChangedDuringQualification('Source changed during GPU qualification')
                current=identity(reader_root)
                if current is None or current['key']!=context['key']:raise ValueError('Reader or GPU changed during compatibility checks')
                real=dict(binary_sha256=context['binding']['binary_sha256'],source_changed=False,
                    source={**{k:video.get(k) for k in ('codec_name','pix_fmt','width','height')},'container':container},
                    full_reads=dict(cpu=cpu_result,cuda=result),full_pairwise_proof=proof)
                scope=qualified_scope(real,damaged)
                # Merge only independently verified old pairs for this same build.
                try:verified_profile(context,record);pairs=record['evidence']['pairs']
                except (ValueError,TypeError,KeyError):pairs=[]
                pairs=[p for p in pairs if (p['real']['source']['codec_name'],p['real']['source']['pix_fmt'],p['real']['full_pairwise_proof']['mode'],p['real']['source'].get('container'))
                    !=(video['codec_name'],video['pix_fmt'],mode,container)][-(MAXIMUM_PAIRS-1):]
                pairs.append(dict(real=real,controls=damaged))
                receipt=dict(schema=1,**context['binding'],scopes=[qualified_scope(p['real'],p['controls']) for p in pairs])
                failures=record.get('failures',{})
                failures={k:v for k,v in failures.items() if k!=scope_key} if isinstance(failures,dict) else {}
                updated=dict(receipt=receipt,evidence=dict(pairs=pairs),failures=failures)
                profile=verified_profile(context,updated)
                write_record(storage,context['key'],updated)
                progress('GPU inspection ready',detail='Full comparison and damaged-input checks passed; qualification saved for matching future jobs',
                    reader_qualification=dict(state='qualified',codec=video['codec_name'],mode=mode,frames=proof['frames']))
                return profile
    except (InterruptedError,SourceChangedDuringQualification):raise
    except Exception as exc:
        guard()
        # A compatibility failure is not a verdict on the media. Retain the
        # already completed CPU reference and every ordinary output check.
        progress('Using CPU inspection',detail='GPU compatibility was not established; complete CPU checks continue',
            reader_qualification=fallback_record(exc))
        return None
