"""Explicit HDR10+ safe-copy finalizer. Never replaces or deletes media.

Input is an original HEVC HDR10+ video and its separately encoded HEVC copy.
Metadata checks are not a perceptual quality score; automatic replacement stays off.
"""
import argparse
import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from fractions import Fraction
from decimal import Decimal

from hdr10plus_validation import preserve_json_pairs, validate_frames
from job_tracking import tracked_call, progress
from task_progress import run_probe
from packet_validation import collect_packets
from auto_optimize import metadata_check, compare_packets, main_video, is_cover, Workflow


def frame_records(path):
    """Stream ffprobe's frames array with repeated HDR10+ keys intact."""
    decoder=json.JSONDecoder(object_pairs_hook=preserve_json_pairs)
    with Path(path).open(encoding='utf-8') as stream:
        buffer='';started=False;need_value=True;seen=False
        while True:
            block=stream.read(65536)
            buffer+=block
            if not started:
                match=re.match(r'\s*\{\s*"frames"\s*:\s*\[',buffer)
                if match:buffer=buffer[match.end():];started=True
                elif not block or len(buffer)>65536:raise ValueError('Invalid frame evidence header')
                else:continue
            while True:
                buffer=buffer.lstrip()
                if buffer.startswith(']'):
                    if need_value and seen:raise ValueError('Trailing comma in frame evidence')
                    tail=buffer[1:]+stream.read(4096)
                    if tail.strip()!='}':raise ValueError('Invalid frame evidence trailer')
                    if stream.read(1):raise ValueError('Extra frame evidence content')
                    return
                if not need_value:
                    if not buffer:break
                    if not buffer.startswith(','):raise ValueError('Invalid frame separator')
                    buffer=buffer[1:].lstrip();need_value=True
                try:item,end=decoder.raw_decode(buffer)
                except json.JSONDecodeError:break
                if not isinstance(item,dict):raise ValueError('Invalid frame record')
                yield item
                buffer=buffer[end:];need_value=False;seen=True
            if not block:raise ValueError('Truncated frame evidence')
            if len(buffer)>4*1024*1024:raise ValueError('Frame evidence exceeds bounded record size')


def write_decoded_timestamps(frames, destination, guard=lambda: None):
    """Assign presentation timestamps to decoded pictures, not encoded packets.

    Cut GOPs may retain non-output/preroll packets. Container timestamp extraction
    includes those packets; applying that list to a fresh encode shifts pictures.
    Full decoded timing validation remains mandatory after muxing.
    """
    previous=None
    count=0
    with Path(destination).open('x',encoding='utf-8') as stream:
        stream.write('# timestamp format v2\n')
        for frame in frames:
            if count%4096==0:guard()
            try:value=Fraction(str(frame['pts_time']))
            except (KeyError,ValueError,ZeroDivisionError) as exc:
                raise ValueError('Decoded frame requires a finite presentation timestamp') from exc
            if previous is not None and value<=previous:
                raise ValueError('Decoded presentation timestamps must increase')
            stream.write(format(Decimal(value.numerator)*1000/Decimal(value.denominator),'.9f')+'\n')
            previous=value;count+=1
        if not count:raise ValueError('No decoded presentation timestamps')
    return count


def preservation_mux_command(mkvmerge, output, track_order, rate, timestamps, options, injected, source):
    # Combined raw-video/copy-audio remuxes can lace audio packets and reconstruct
    # their timestamps. Keep individual packets; never relax validation tolerances.
    return [mkvmerge,'-o',output,'--disable-lacing','--track-order',track_order,
            '--default-duration',f'0:{rate.numerator}/{rate.denominator}fps',
            '--timestamps','0:'+str(timestamps),*options,injected,'--no-video',source]


def preserved_tracks_command(ffmpeg, packaged, source, output, streams):
    """Copy restored video and original non-video packets, including block durations."""
    command=[ffmpeg,'-v','error','-nostdin','-n','-copyts','-i',str(packaged),
             '-i',str(source)]
    for stream in streams:
        moving = stream['codec_type']=='video' and not is_cover(stream)
        command+=['-map','0:v:0' if moving else '1:'+str(stream['index'])]
    command+=['-c','copy','-map_metadata','1','-map_chapters','1','-avoid_negative_ts','disabled']
    for index,stream in enumerate(streams):
        command += [f'-map_metadata:s:{index}',f"1:s:{stream['index']}",
                    f'-disposition:{index}',
                    '+'.join(k for k,v in stream.get('disposition',{}).items() if v) or '0']
    return command+[str(output)]


def finalize(args):
    mode=getattr(args,'mode','hdr10plus')
    if mode not in ('hdr10','hdr10plus','pq','hlg'):raise ValueError('Unsupported HDR mode')
    source=args.source.resolve(strict=True);encoded=args.encoded.resolve(strict=True)
    root=args.output_dir.resolve()
    if source==encoded or root==source or root==encoded:
        raise ValueError('Source, encoded input and output directory must be distinct')
    for name in ('ffmpeg','ffprobe','hdr10plus_tool','mkvmerge','mkvextract','mkvpropedit'):
        if name=='hdr10plus_tool' and mode in ('hdr10','hlg'):continue
        tool=getattr(args,name)
        resolved=shutil.which(tool)
        if not resolved:raise ValueError('Missing tool: '+tool)
        setattr(args,name,resolved)
    root.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root).free < encoded.stat().st_size*4+1024**3:
        raise ValueError('Insufficient space for isolated bitstreams and output')
    run=root/('hdr10plus-preserve-'+uuid.uuid4().hex[:12]);run.mkdir(exist_ok=False)
    fingerprints={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in (source,encoded)}
    def guard():
        if getattr(args,'guard',None):args.guard()
        for path,identity in fingerprints.items():
            if (path.stat().st_size,path.stat().st_mtime_ns)!=identity:
                raise ValueError('Input changed during preservation')
    def command(argv,label):
        guard();progress(label,directory=run,detail='Preservation test; originals protected')
        with (run/(label+'.log')).open('x',encoding='utf-8') as log:
            child=subprocess.Popen(list(map(str,argv)),stdout=log,stderr=log)
            started=time.monotonic()
            try:
                while True:
                    guard()
                    remaining=args.timeout-(time.monotonic()-started)
                    if remaining<=0:raise subprocess.TimeoutExpired(argv,args.timeout)
                    try:
                        code=child.wait(timeout=min(2,remaining));break
                    except subprocess.TimeoutExpired:pass
                if code:raise subprocess.CalledProcessError(code,argv)
            except BaseException:
                child.kill();child.wait();raise
        guard()
    def probe(path):
        result=subprocess.run([args.ffprobe,'-v','error','-show_streams','-show_format','-show_chapters',
            '-show_data_hash','sha256','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=60)
        return json.loads(result.stdout)
    result_holder={}
    def work():
        before=probe(source);mid=probe(encoded)
        video=main_video(before)
        from auto_optimize import PLANAR_FORMATS
        if video.get('pix_fmt') not in PLANAR_FORMATS or video.get('color_transfer')!=('arib-std-b67' if mode=='hlg' else 'smpte2084'):
            raise ValueError('Requires supported native pixel format and matching HDR transfer')
        if any(s['codec_type'] not in ('video','audio','subtitle','attachment') for s in before['streams']):
            raise ValueError('Additional track types need preservation validation')
        if any(s['codec_type']=='attachment' and not s.get('extradata_hash') for s in before['streams']):
            raise ValueError('Attachment payload hash unavailable')
        if any('dovi' in str(s).lower() or 'dolby vision' in str(s).lower() for s in video.get('side_data_list',[])):
            raise ValueError('Dolby Vision requires a separate workflow')
        encoded_video=main_video(mid)
        if encoded_video['codec_name']!='hevc':
            raise ValueError('Encoded input must contain one HEVC video')
        for key in ('width','height','pix_fmt','color_range','color_space','color_transfer','color_primaries'):
            if video.get(key) is None or video[key]!=encoded_video.get(key):raise ValueError('Encoded video changed '+key)
        rate=Fraction(video['avg_frame_rate'])
        if rate<=0:raise ValueError('Invalid frame rate')
        raw=run/'encoded.hevc';injected=run/'injected.hevc';output=Path(getattr(args,'final_output',run/'preserved.mkv'))
        if output.exists() or output.is_symlink() or output.resolve().parent not in (root,run):
            raise ValueError('Final output must be a new file in the owned output directory')
        duration=float(before['format']['duration'])
        source_frames=getattr(args,'reference_frames',None)
        if source_frames is None:
            source_frames=run/'source-frames.json'
            run_probe([args.ffprobe,'-v','error','-threads','2','-select_streams','v:0','-show_frames','-of','json',str(source)],
                      source_frames,'Checking original HDR metadata',args.timeout,guard,duration)
            if source_frames.with_suffix(source_frames.suffix+'.stderr').stat().st_size:
                raise ValueError('Decoder errors in original HDR evidence')
        from hdr10plus_validation import hdr_metadata
        dynamic=False
        for number,frame in enumerate(frame_records(source_frames)):
            if number%4096==0:guard()
            items=hdr_metadata(frame)
            dynamic=any('2094-40' in item.get('side_data_type','') or 'HDR10+' in item.get('side_data_type','') for item in items) or dynamic
        restore_dynamic=mode=='hdr10plus' or (mode=='pq' and dynamic)
        if restore_dynamic:
            if video.get('codec_name')!='hevc':
                raise ValueError('HDR10+ extraction from this source codec is not implemented')
            command([args.hdr10plus_tool,'extract',source,'-o',run/'hdr10plus.json'],'Extracting HDR10Plus')
        command([args.ffmpeg,'-v','error','-nostdin','-n','-i',encoded,'-map','0:v:0','-c','copy',
                 '-bsf:v','hevc_mp4toannexb','-f','hevc',raw],'Extracting encoded video')
        if restore_dynamic:
            command([args.hdr10plus_tool,'inject','-i',raw,'-j',run/'hdr10plus.json','-o',injected],'Restoring HDR10Plus')
        else:
            injected=raw  # Static metadata must already survive encoding; full validation proves it.
        progress('Restoring decoded presentation timestamps',directory=run)
        write_decoded_timestamps(frame_records(source_frames),run/'timestamps.txt',guard)
        from media_metadata import canonical_tags
        tags=canonical_tags(video.get('tags',{}));disposition=video.get('disposition',{})
        options=['--language','0:'+tags.get('language','und'),'--track-name','0:'+tags.get('title',''),
                 '--default-track-flag','0:'+str(int(bool(disposition.get('default')))),
                 '--forced-display-flag','0:'+str(int(bool(disposition.get('forced'))))]
        track_order=','.join('0:0' if s['codec_type']=='video' else '1:'+str(s['index'])
                             for s in before['streams'] if s['codec_type']!='attachment' and not is_cover(s))
        packaged=run/'packaged-video.mkv'
        command(preservation_mux_command(args.mkvmerge,packaged,track_order,rate,
                 run/'timestamps.txt',options,injected,source),'Packaging preserved copy')
        # Timestamp-file import otherwise infers a rounded millisecond default.
        # Modify only the new generated copy, never either input.
        command([args.mkvpropedit,packaged,'--edit','track:v1','--set',
                 'default-duration='+str(round(Fraction(10**9,1)/rate))],'Preserving nominal frame rate')
        # mkvmerge can reconstruct copied-track timestamps/durations even with
        # lacing disabled. Source packets remain the authority, never a tolerance.
        track_command=preserved_tracks_command(args.ffmpeg,packaged,source,output,before['streams'])
        cover_workflow=Workflow(args,run,guard)
        track_command=cover_workflow.preserve_covers(track_command,source,before,'original-artwork',input_index=1)
        cover_files=[run/('original-artwork-cover-'+str(s['index'])+
                         ('.png' if s['codec_name']=='png' else '.jpg'))
                     for s in before['streams'] if is_cover(s)]
        command(track_command,'Restoring original copied-track timing')
        progress('Checking preserved track and chapter metadata',directory=run)
        after=probe(output);metadata_check(before,after,'hevc')
        if getattr(args,'repair_only',False):
            intermediates={raw,injected,packaged,*cover_files}
            result_holder.update(output=str(output),reference_frames=str(source_frames),validated=False,
                                 intermediates=[str(path) for path in sorted(intermediates)])
            return
        paths=[Path(source_frames)]
        for label,path in [('output',output)]:
            evidence=run/(label+'-frames.json');paths.append(evidence)
            run_probe([args.ffprobe,'-v','error','-select_streams','v:0','-show_frames','-of','json',str(path)],
                      evidence,'Checking HDR frames: '+label,args.timeout,guard,duration)
            # ffprobe can return success despite decoder errors. Do not certify
            # concealed/damaged frames merely because counts happen to match.
            if evidence.with_suffix(evidence.suffix+'.stderr').stat().st_size:
                raise ValueError('Decoder reported errors while reading '+label+' HDR evidence')
        result=validate_frames(frame_records(paths[0]),frame_records(paths[1]),mode=mode)
        indices=[s['index'] for s in before['streams'] if s['codec_type'] in ('audio','subtitle') or is_cover(s)]
        original=collect_packets(args.ffprobe,source,run,'source',indices,args.timeout,guard,duration)
        final=collect_packets(args.ffprobe,output,run,'output',indices,args.timeout,guard,duration)
        for index in indices:
            cover=any(s['index']==index and is_cover(s) for s in before['streams'])
            compare_packets(original[index],final[index],cover=cover)
        command([args.ffmpeg,'-v','error','-nostdin','-xerror','-i',output,'-map','0:v:0','-map','0:a?',
                 '-fps_mode:v','passthrough','-enc_time_base:v','1:1000','-f','null','-'],'Checking complete decode')
        guard()
        result.update(output=str(output),source=str(source),copied_tracks_verified=True,
                      size_reduction_percent=100*(1-output.stat().st_size/source.stat().st_size),
                      note='Preservation verified; picture quality not automatically approved. No replacement performed.')
        (run/'preservation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)
        progress('Preservation verified — quality review required',directory=run,detail=result['note'])
        result_holder.update(result)
    tracked_call(work,('HDR10+ ' if mode=='hdr10plus' else 'HDR10 ')+'preservation validation',folder=run)
    return result_holder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--encoded',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--mode',choices=('hdr10plus','hdr10'),default='hdr10plus')
    for tool in ('ffmpeg','ffprobe','hdr10plus_tool','mkvmerge','mkvextract','mkvpropedit'):
        parser.add_argument('--'+tool.replace('_','-'),dest=tool,default=tool)
    parser.add_argument('--timeout',type=int,default=14400)
    finalize(parser.parse_args())
    return 0


if __name__=='__main__':raise SystemExit(main())
