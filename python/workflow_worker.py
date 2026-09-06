"""Owned workflow worker: fixed actions, unique outputs, read-only original media."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import time
import muxmender as mm
import native_pipeline as np
from mux_integrity import conversion_preflight
from library_planner import scan, classify, probe_with_frame_color
from streaming_pipeline import chapter_summary


def save(path,data):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,indent=2),encoding='utf-8')
    temporary.replace(path)  # Only owned metadata, never media.


class Context:
    def __init__(self,directory,parent_pid=None):
        self.directory=Path(directory).resolve()
        self.path=self.directory/'job.json'
        self.data=json.loads(self.path.read_text(encoding='utf-8'))
        self.parent_pid=parent_pid
        self.checked=0
        self.minimum=2*1024**3

    def update(self,phase,percent=None,**more):
        self.data.update(phase=phase,updated=time.time(),**more)
        if percent is not None: self.data['percent']=percent
        save(self.path,self.data)
        if percent is not None: print(f'MUXMENDER_PROGRESS={percent:.1f}',flush=True)

    def guard(self):
        if (self.directory/'STOP').exists(): raise InterruptedError('Cancelled; all files retained')
        now=time.monotonic()
        if now-self.checked>=3:
            self.checked=now
            if self.parent_pid:
                from dashboard import alive
                if alive(self.parent_pid) is False: raise InterruptedError('Controller stopped; all files retained')
            if shutil.disk_usage(self.directory).free < self.minimum:
                raise RuntimeError('Disk-space safety reserve reached; all files retained')
            self.update(self.data.get('phase','Working'))

    def stage(self,command,duration,phase,offset,span):
        self.guard();self.update(phase,offset)
        print('COMMAND: '+mm.command_text(command),flush=True)
        return np.stage(command,duration,offset,span,timeout=14400,stall=120,guard=self.guard)


def video_summary(path,ffprobe):
    data=np.checked_json([ffprobe,'-v','error','-select_streams','v:0','-show_packets','-show_entries',
        'packet=pts_time,size','-of','json',str(path)],timeout=600)
    packets=data.get('packets',[])
    if not packets: raise ValueError('No video packets')
    pts=sorted(float(p['pts_time']) for p in packets)
    if not all(math.isfinite(p) for p in pts): raise ValueError('Invalid frame timestamps')
    return pts,sum(int(p['size']) for p in packets)


def shape(path,ffprobe):
    data=np.checked_json([ffprobe,'-v','error','-select_streams','v:0','-show_streams',
        '-show_entries','stream=sample_aspect_ratio,display_aspect_ratio,field_order:stream_side_data=rotation',
        '-of','json',str(path)])
    return data['streams'][0]


def compare_packets(left,right,infer_audio_duration=False):
    # Container interleaving can change while each individual track is identical.
    # Preserve stream identity and packet order within each track; never sort PTS.
    def tracks(packets):
        grouped={}
        for packet in packets:
            stream=packet.get('stream_index')
            if not isinstance(stream,int):raise ValueError('Missing packet stream identity')
            grouped.setdefault(stream,[]).append(packet)
        return grouped
    a,b=tracks(left),tracks(right)
    if a.keys()!=b.keys():raise ValueError('Audio/subtitle stream identities changed')
    return sum(compare_track_packets(a[key],b[key],infer_audio_duration) for key in a)


def compare_track_packets(left,right,infer_audio_duration=False):
    if len(left)!=len(right):raise ValueError('Audio/subtitle packet count changed')
    inferred=0
    for index,(original,encoded) in enumerate(zip(left,right)):
        a,b=dict(original),dict(encoded)
        if not a.get('data_hash') or a.get('data_hash')!=b.get('data_hash'):
            raise ValueError('Audio/subtitle packet payload changed')
        if infer_audio_duration and ('duration_time' in a)!=('duration_time' in b):
            supplied=a.get('duration_time',b.get('duration_time'))
            following=next((p for p in left[index+1:] if p.get('stream_index')==a.get('stream_index')),None)
            if following and 'pts_time' in a and 'pts_time' in following:
                delta=float(following['pts_time'])-float(a['pts_time'])
                if delta>0 and abs(delta-float(supplied))<=.002:
                    a['duration_time']=b['duration_time']=supplied;inferred+=1
        if a!=b:raise ValueError('Audio/subtitle packet timing or side data changed')
    return inferred


def compare_media_packets(ffprobe,source,output,selector,guard=lambda:None):
    left=np.packet_signatures(ffprobe,source,selector,timeout=600);guard()
    right=np.packet_signatures(ffprobe,output,selector,timeout=600);guard()
    rounded=0
    try:
        inferred=compare_packets(left,right,infer_audio_duration=selector=='a')
    except ValueError as exc:
        if selector!='a' or str(exc)!='Audio/subtitle packet timing or side data changed':raise
        print('Verifying audio rounding against complete decoded sample metadata',flush=True)
        def decoded(path):
            return np.checked_json([ffprobe,'-v','error','-threads','2','-select_streams','a',
                '-show_frames','-show_streams','-show_entries',
                'frame=stream_index,pts_time,nb_samples:stream=index,codec_name,sample_rate,time_base',
                '-of','json',str(path)],timeout=600)
        original_decode=decoded(source);guard()
        output_decode=decoded(output);guard()
        from mux_integrity import normalize_rounding
        left,right,rounded=normalize_rounding(left,right,original_decode,output_decode)
        inferred=compare_packets(left,right,infer_audio_duration=True)
    return dict(packets=len(left),streams=sorted(set(p['stream_index'] for p in left)),
                inferred_duration_fields=inferred,sample_verified_rounded_durations=rounded,verified=True)


def convert(request,ctx):
    source=Path(request['source']).resolve(strict=True)
    # The controller's output location is fixed and cannot be supplied as an FFmpeg argument.
    if source==ctx.directory or ctx.directory in source.parents:
        raise ValueError('Source cannot be inside this job output directory')
    before=source.stat()
    expected=request.get('fingerprint')
    if expected and expected!={'size':before.st_size,'mtime_ns':before.st_mtime_ns}:
        raise ValueError('Source changed since selection; scan again')
    ffmpeg,ffprobe=request['ffmpeg'],request['ffprobe']
    info=probe_with_frame_color(source,ffprobe)
    action,reason=classify(info)
    if action!='preview-candidate': raise ValueError('Not approved for ordinary conversion: '+reason)
    preflight=conversion_preflight(info,ffprobe,mm.run_json)
    if preflight['status']!='passed-sampled-checks': raise ValueError('; '.join(preflight['reasons']))
    geometry=shape(source,ffprobe)
    if geometry.get('field_order') not in ('progressive',):
        raise ValueError('Interlaced/unknown field order needs review')
    if any(float(x.get('rotation',0))!=0 for x in geometry.get('side_data_list',[])):
        raise ValueError('Rotated video needs a dedicated preservation route')
    selection=mm.select_encoder(request['codec'],request['hardware'],mm.ffmpeg_encoder_names(ffmpeg),mm.gpu_vendors())
    if request['hardware']!='cpu' and not selection.hardware: raise ValueError('No silent CPU fallback')
    is_preview=request['kind']=='preview'
    required=(min(before.st_size,512*1024**2)*4 if is_preview else before.st_size*2)+ctx.minimum
    if shutil.disk_usage(ctx.directory).free<required: raise ValueError('Insufficient space for output and reserve')
    ff=[ffmpeg,'-hide_banner','-loglevel','warning','-nostdin','-n']
    progress=['-progress','pipe:1','-nostats']
    reference=source
    result=dict(source=str(source),status='running',preflight=preflight,encoder=selection.label,
                quality='AMD quality QP21/23; other encoders balanced',scope=request['kind'])
    try:
        if is_preview:
            start=float(request.get('start',300));seconds=float(request.get('seconds',30))
            if not math.isfinite(start) or not math.isfinite(seconds) or start<0 or not 1<=seconds<=30 or start>=info.duration_seconds:
                raise ValueError('Preview must be 1..30 seconds and start within the source')
            reference=ctx.directory/'Reference.mkv'
            ctx.stage(ff+['-ss',str(start),'-i',str(source),'-t',str(seconds),'-map','0:v:0','-map','0:a?',
                '-map','0:s?','-map','0:t?','-map_chapters','-1','-c','copy','-avoid_negative_ts','make_zero',*progress,str(reference)],
                seconds,'Extract preview reference',0,10)
            info=probe_with_frame_color(reference,ffprobe)
            if info.duration_seconds>seconds+15: raise ValueError('Reference exceeds bounded preview duration')
            result.update(reference=str(reference),requested_start=start,requested_seconds=seconds)
        output=ctx.directory/'Optimized.mkv'
        opts=mm.encoder_options(request['codec'],'balanced',info,selection.encoder)
        if selection.vendor=='amd': opts[opts.index('-quality')+1]='quality'
        ctx.stage(ff+['-threads','2','-noautorotate','-copyts','-i',str(reference),'-map','0:v:0','-map','0:a?',
            '-map','0:s?','-map','0:t?','-map_metadata','0','-map_chapters','0',*opts,'-fps_mode','passthrough',
            '-c:a','copy','-c:s','copy','-c:t','copy','-avoid_negative_ts','disabled',*progress,str(output)],
            info.duration_seconds,'Encode '+selection.label,10,60)
        ctx.update('Validate streams and frame timing',70)
        actual=probe_with_frame_color(output,ffprobe)
        for key in ('width','height','bit_depth','color_primaries','color_transfer','color_space','color_range','audio_codecs','subtitle_codecs'):
            if getattr(info,key)!=getattr(actual,key): raise ValueError('Output mismatch: '+key)
        if actual.video_codec!=request['codec'] or actual.hdr or actual.dolby_vision: raise ValueError('Unexpected codec/HDR signaling')
        a,a_bytes=video_summary(reference,ffprobe);ctx.guard()
        b,b_bytes=video_summary(output,ffprobe);ctx.guard()
        if len(a)!=len(b) or any(abs(x-y)>.002 for x,y in zip(a,b)): raise ValueError('Video packet count/timing mismatch')
        for key in ('sample_aspect_ratio','display_aspect_ratio'):
            if shape(reference,ffprobe).get(key)!=shape(output,ffprobe).get(key): raise ValueError('Aspect ratio changed')
        for selector in ('a','s'):
            result['packet_validation_'+selector]=compare_media_packets(ffprobe,reference,output,selector,ctx.guard)
            ctx.guard()
        if chapter_summary(ffprobe,reference,600)!=chapter_summary(ffprobe,output,600): raise ValueError('Chapters changed')
        def attachments(path):
            data=np.checked_json([ffprobe,'-v','error','-select_streams','t','-show_streams','-show_data_hash','sha256',
                '-show_entries','stream=codec_name,extradata_hash:stream_tags=filename,mimetype','-of','json',str(path)],timeout=60)
            return data.get('streams',[])
        if attachments(reference)!=attachments(output): raise ValueError('Attachments changed')
        ctx.stage(ff+['-v','error','-xerror','-threads','2','-i',str(output),'-map','0:v:0','-f','null','-',*progress],
                  info.duration_seconds,'Full output decode validation',80,20)
        savings=100*(1-output.stat().st_size/reference.stat().st_size)
        result.update(output=str(output),output_bytes=output.stat().st_size,source_bytes=reference.stat().st_size,
            total_savings_percent=savings,video_savings_percent=100*(1-b_bytes/a_bytes),frames=len(a),
            audio_subtitle_packets_unchanged=True,chapters_unchanged=True,
            quality_note='Lossy encoding; playback review required. Preview savings are not full-file predictions.')
        if savings<float(request.get('min_savings',5)): raise ValueError('Savings below acceptance threshold; all files retained')
        result['status']='verified-'+('preview' if is_preview else 'full-file')+'-awaiting-playback'
        return result
    except BaseException as exc:
        result.update(status='cancelled' if isinstance(exc,InterruptedError) else 'failed',error=str(exc))
        raise
    finally:
        after=source.stat()
        result['original_stat_unchanged']=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
        if not result['original_stat_unchanged']: result.update(status='failed',error='Source stat changed externally')
        with (ctx.directory/'validation.json').open('x',encoding='utf-8') as out: json.dump(result,out,indent=2)
        if not result['original_stat_unchanged']: raise ValueError('Source changed externally during execution')


def work(directory,parent_pid=None):
    if parent_pid:
        # Parent records the owned PID before the worker writes its first status.
        deadline=time.monotonic()+15
        while not (Path(directory)/'READY').exists():
            if time.monotonic()>deadline:raise RuntimeError('Controller launch handshake timed out')
            time.sleep(.05)
    ctx=Context(directory,parent_pid)
    request=json.loads((ctx.directory/'request.json').read_text(encoding='utf-8'))
    ctx.update('Starting',0,state='running',pid=os.getpid(),started=time.time())
    try:
        if request['kind']=='scan':
            result=scan(request['source'],ctx.directory,request['ffprobe'],ctx.guard,ctx.update,
                        excluded=request.get('excluded',[]))
            state='completed' if not result['actions'].get('probe-error') else 'completed-with-errors'
        elif request['kind']=='dependencies':
            args=mm.parse_args(['--check-dependencies','--hardware',request['hardware'],
                '--ffmpeg',request['ffmpeg'],'--ffprobe',request['ffprobe']])
            from runtime_support import check_dependencies
            code=check_dependencies(args)
            state='completed' if code==0 else 'failed'
            result={'status':state,'note':'Encoder listing is not a GPU execution test'}
        elif request['kind'] in ('preview','convert'):
            result=convert(request,ctx);state='verified'
        else: raise ValueError('Unknown action')
        ctx.update(result['status'],100,state=state,result=result,finished=time.time())
        return int(state in ('failed','completed-with-errors'))
    except BaseException as exc:
        state='cancelled' if isinstance(exc,(KeyboardInterrupt,InterruptedError)) else 'failed'
        print(f'{state.upper()}: {exc}; all files retained',flush=True)
        ctx.update(state,state=state,error=str(exc),finished=time.time())
        return 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--parent-pid',type=int)
    args=parser.parse_args()
    raise SystemExit(work(args.directory,args.parent_pid))
