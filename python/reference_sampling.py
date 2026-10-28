"""Keyframe sample planning and source-identity checks.

Used only as an evidence-verified recovery from excessive sample preroll.
Lossless staging requires exact original decoded pixels and display timing,
unchanged copied-track packets, and original compressed-byte size accounting.
"""
from fractions import Fraction
import json
import math


def align_copy_seek(plan, streams, origin, maximum_seconds):
    """Avoid per-stream rounding of a seek while retaining its absolute end.

    AVI audio and video clocks need not represent the same fractional seek.
    Select a nearby earlier point representable on every copied track clock.
    Keep the existing sampling bound; packet and decoded-picture proof still
    decide whether the resulting reference can be used.
    """
    clocks=[Fraction(stream['time_base']) for stream in streams
            if stream.get('codec_type') in ('video','audio','subtitle')
            and not stream.get('disposition',{}).get('attached_pic')]
    if not clocks or any(clock<=0 for clock in clocks):
        raise ValueError('Copied streams need positive time bases')
    quantum=Fraction(math.lcm(*(clock.numerator for clock in clocks)),
                     math.gcd(*(clock.denominator for clock in clocks)))
    origin=Fraction(origin)
    relative=Fraction(plan['seek'])-origin
    steps=relative//quantum
    aligned=origin+steps*quantum
    adjustment=Fraction(plan['seek'])-aligned
    seconds=Fraction(plan['seconds'])+adjustment
    result=dict(plan)
    if aligned<origin or seconds>Fraction(maximum_seconds):
        return result  # Do not expand an already bounded reference arbitrarily.
    result.update(seek=aligned,seconds=seconds,seek_clock_quantum=quantum,
                  seek_clock_adjustment=adjustment)
    return result


def plan_keyframe(packets, time_base, requested, seconds, source_end, search_span=None, *, excluded_starts=()):
    tick = Fraction(time_base)
    requested, seconds, source_end = map(Fraction, map(str, (requested, seconds, source_end)))
    search_span=seconds if search_span is None else Fraction(str(search_span))
    if tick <= 0 or seconds <= 0 or search_span<seconds or search_span>60 or requested < 0 or source_end <= requested:
        raise ValueError('Invalid sampling bounds')
    choices = []
    excluded={Fraction(value) for value in excluded_starts}
    for packet in packets:
        if 'K' not in packet.get('flags', '') or 'D' in packet.get('flags', ''):
            continue
        if packet.get('pts_time') in (None, 'N/A') or packet.get('dts_time') in (None, 'N/A'):
            continue
        pts, dts = Fraction(packet['pts_time']), Fraction(packet['dts_time'])
        if pts in excluded:continue
        # Keep the selected scene nearby and leave room for the entire sample.
        if max(Fraction(0), requested-2*search_span) <= pts <= requested + search_span and pts + seconds <= source_end and dts >= tick:
            choices.append((pts, dts))
    if not choices:
        raise ValueError('No verified keyframe within sampling bounds')
    pairs=[]
    for pts,dts in choices:
        for packet in packets:
            if 'K' not in packet.get('flags','') or 'D' in packet.get('flags',''):
                continue
            if packet.get('pts_time') in (None,'N/A') or packet.get('dts_time') in (None,'N/A'):
                continue
            end_pts,end_dts=Fraction(packet['pts_time']),Fraction(packet['dts_time'])
            # A preceding GOP is useful only if it includes the requested scene,
            # not merely an easier, unrelated earlier scene. Evaluate complete
            # pairs before choosing: the nearest forward keyframe may be the last.
            if max(pts,requested)+seconds<=end_pts<=min(source_end,pts+2*search_span) and end_dts>dts:
                pairs.append((pts,dts,end_pts,end_dts))
    if not pairs:
        raise ValueError('No complete GOP boundary within sampling bounds')
    pts,dts,end_pts,end_dts=min(pairs,key=lambda pair:
        (pair[0]<requested,abs(pair[0]-requested),pair[2],pair[1]))
    return dict(keyframe_pts=pts,keyframe_dts=dts,seek=dts-tick,seconds=end_dts-dts,
                end_keyframe_pts=end_pts,end_keyframe_dts=end_dts)


def verify_decoded_slice(source, sample, expected_shift=None, tolerance=Fraction(0)):
    """Exact decoded pixels, display order and relative display timestamps."""
    if not sample:
        raise ValueError('Empty decoded reference')
    matches=[i for i in range(len(source)-len(sample)+1)
             if (expected_shift is None or abs(Fraction(sample[0]['pts'])-Fraction(source[i]['pts'])-expected_shift)<=tolerance)
             and all(a['hash']==b['hash'] and a['size']==b['size']
                    for a,b in zip(source[i:i+len(sample)],sample))]
    if len(matches)!=1:
        raise ValueError('Decoded reference differs from source pictures')
    pairs=list(zip(source[matches[0]:],sample))
    shift=Fraction(pairs[0][1]['pts'])-Fraction(pairs[0][0]['pts'])
    if any(abs(Fraction(b['pts'])-Fraction(a['pts'])-shift)>tolerance for a,b in pairs):
        raise ValueError('Decoded reference display timing changed')
    return shift


def parse_framehash(text):
    base=None;frames=[]
    for line in text.splitlines():
        if line.startswith('#tb 0:'):
            base=Fraction(line.split(':',1)[1].strip())
        elif line and not line.startswith('#'):
            fields=[x.strip() for x in line.split(',')]
            if base is None or len(fields)!=6 or fields[0]!='0':
                raise ValueError('Invalid decoded frame hash evidence')
            frames.append(dict(pts=str(int(fields[2])*base),size=int(fields[4]),hash=fields[5]))
    return frames


def verify_source_slice(source, sample, expected_shift=None, *, decoded_source=None,
                        decoded_sample=None, reorder_depth=0, tolerance=Fraction(0)):
    """Require unique contiguous payload identity and a single exact time shift."""
    if not sample:
        raise ValueError('Empty reference stream')
    if any(not p.get('data_hash') for p in source + sample):
        raise ValueError('Missing packet hash')
    payload_matches = [i for i in range(len(source)-len(sample)+1)
                       if all(a['data_hash'] == b['data_hash']
                              for a, b in zip(source[i:i+len(sample)], sample))]
    matches = [i for i in payload_matches if (expected_shift is None or
                    (source[i].get('pts_time') not in (None,'N/A') and sample[0].get('pts_time') not in (None,'N/A')
                     and abs(Fraction(sample[0]['pts_time'])-Fraction(source[i]['pts_time'])-expected_shift)<=tolerance))]
    if payload_matches and not matches:
        raise ValueError('Reference stream timestamp shift differs from the other tracks')
    if len(matches) != 1:
        raise ValueError('Reference is not one unique contiguous source slice')
    shift = expected_shift
    missing_dts=[]
    for number,(a, b) in enumerate(zip(source[matches[0]:], sample)):
        for key in ('pts_time', 'dts_time', 'duration_time'):
            left, right = a.get(key), b.get(key)
            if left in (None, 'N/A') or right in (None, 'N/A'):
                if left != right:
                    if (key=='dts_time' and right in (None,'N/A') and
                            left not in (None,'N/A') and number < reorder_depth):
                        missing_dts.append(number)
                    else:
                        raise ValueError('Reference timestamp availability changed')
                continue
            delta = Fraction(right)-Fraction(left)
            if key == 'duration_time':
                if abs(delta)>tolerance:
                    raise ValueError('Reference packet duration changed')
            else:
                if shift is None:
                    shift = delta
                if abs(shift-delta)>tolerance:
                    raise ValueError('Reference stream alignment changed')
    if shift is None:
        raise ValueError('Reference has no verifiable timestamps')
    if missing_dts:
        if missing_dts!=list(range(len(missing_dts))) or decoded_source is None or decoded_sample is None:
            raise ValueError('Initial DTS reconstruction requires decoded-frame evidence')
        if abs(verify_decoded_slice(decoded_source,decoded_sample,shift,tolerance)-shift)>tolerance:
            raise ValueError('Decoded and packet timestamp shifts disagree')
    return shift


def recover_reference(workflow, source, metadata, position, seconds, label, *, excluded_starts=()):
    """Bounded recovery for excessive preroll; prove source identity before use."""
    from task_progress import run_probe
    from auto_optimize import main_video,paired_streams
    video=main_video(metadata)
    generated_pts=(video.get('codec_name')=='mpeg4' and
                   'avi' in metadata['format'].get('format_name','').split(','))
    input_options=['-fflags','+genpts'] if generated_pts else []
    tolerance=Fraction(2,1000) if generated_pts else Fraction(0)
    origin=Fraction(metadata['format'].get('start_time','0'))
    target=origin+Fraction(str(position));span=Fraction(str(seconds))
    search_span=max(span,Fraction(15))
    begin=max(origin,target-search_span);end=min(origin+Fraction(metadata['format']['duration']),target+4*search_span)
    def decimal(value):return format(float(value),'.9f')
    def packets(path,suffix,interval=None):
        evidence=workflow.directory/(label+'-'+suffix+'-packets.json')
        command=[workflow.args.ffprobe,'-v','error',*workflow.reader_input_options(path),*workflow.decoder_options(path),*(input_options if path==source else [])]
        if interval:command+=['-read_intervals',interval]
        command+=['-show_packets','-show_data_hash','sha256','-show_entries',
                  'packet=stream_index,pts,dts,duration,pts_time,dts_time,duration_time,data_hash,flags,size','-of','json',str(path)]
        from artifact_manifest import command_outputs
        with command_outputs(workflow.directory,[*command,str(evidence)]):
            run_probe(command,evidence,'Checking sample source packets: '+suffix,
                      workflow.args.timeout,workflow.guard,float(end-begin),float(begin))
        if evidence.with_suffix(evidence.suffix+'.stderr').stat().st_size:
            raise ValueError('Packet reader reported errors during sample recovery')
        rows=json.loads(evidence.read_text(encoding='utf-8'))['packets']
        bases={s['index']:Fraction(s['time_base']) for s in workflow.probe(path)['streams'] if s.get('time_base')}
        for row in rows:
            base=bases.get(row['stream_index'])
            if base is None:continue
            for field in ('pts','dts','duration'):
                if type(row.get(field)) is int:row[field+'_time']=str(row[field]*base)
        return rows
    original=packets(source,'source',decimal(begin)+'%'+decimal(end))
    selected=[p for p in original if p['stream_index']==video['index']]
    plan=plan_keyframe(selected,video['time_base'],target,span,origin+Fraction(metadata['format']['duration']),search_span,
                       excluded_starts=excluded_starts)
    if generated_pts:
        # Preserve the boundary packet needed by preceding MPEG-4 B pictures.
        plan['seconds']+=Fraction(video['time_base'])
        plan=align_copy_seek(plan,metadata['streams'],origin,2*search_span)
    # ffprobe seeks to an earlier keyframe. If that complete GOP is selected,
    # decode its beginning too rather than trimming the proof at the requested
    # packet-search timestamp.
    proof_begin=max(origin,min(begin,plan['seek']))
    if proof_begin<begin:
        begin=proof_begin
        # Include packets from every copied stream at the newly selected start;
        # audio packets may precede the demuxer's initially returned video GOP.
        original=packets(source,'source-expanded',decimal(begin)+'%'+decimal(end))
    suffix=getattr(workflow,'output_suffix','.mkv')
    if suffix not in ('.mkv','.mp4','.mov'):raise ValueError('Invalid reference container')
    output=workflow.directory/(label+suffix)
    command=[workflow.args.ffmpeg,'-hide_banner','-nostdin','-n',*input_options,'-ss',decimal(plan['seek']-origin),
             '-i',str(source),'-ss','0','-t',decimal(plan['seconds']),'-map','0','-c','copy',
             '-map_chapters','-1','-avoid_negative_ts','make_zero','-progress','pipe:1','-nostats',str(output)]
    if suffix in ('.mp4','.mov'):
        from media_metadata import mp4_clock_options
        # Avoid per-track rounding caused by rebasing the requested fractional
        # seek point. Keep native clocks and use one integral-second offset.
        # Input seeking is rounded upward so demuxing includes the selected RAP,
        # not the previous GOP. Exact packet/picture proof below remains required.
        micros=(plan['keyframe_pts']-origin)*1000000
        seek_us=-(-micros.numerator//micros.denominator)
        offset=plan['keyframe_dts'].numerator//plan['keyframe_dts'].denominator
        command=[workflow.args.ffmpeg,'-hide_banner','-nostdin','-n','-copyts',
                 '-ss',decimal(Fraction(seek_us,1000000)),'-i',str(source),
                 '-t',decimal(plan['end_keyframe_dts']),'-map','0','-c','copy',
                 '-map_chapters','-1','-avoid_negative_ts','disabled','-output_ts_offset',str(-offset),
                 *mp4_clock_options(metadata['streams']),'-progress','pipe:1','-nostats',str(output)]
    workflow.execute(workflow.preserve_covers(command,source,metadata,label),label,float(plan['seconds']))
    copied=packets(output,'sample')
    mapped={a['index']:b['index'] for a,b in paired_streams(metadata,workflow.probe(output))}
    vcopy=[p for p in copied if p['stream_index']==mapped[video['index']]]
    if not vcopy:raise ValueError('Recovered reference contains no video')
    if 'K' not in vcopy[0].get('flags',''):
        raise ValueError('Recovered reference does not begin with a keyframe')
    shift=Fraction(vcopy[0]['pts_time'])-plan['keyframe_pts']
    def decoded(path,suffix,is_source=False):
        evidence=workflow.directory/(label+'-'+suffix+'-decoded.md5')
        command=[workflow.args.ffmpeg,'-v','error','-nostdin','-xerror','-copyts']
        if is_source:command+=['-ss',decimal(begin-origin),'-t',decimal(end-begin)]
        command+=[*workflow.reader_input_options(path),*workflow.decoder_options(path),'-noautorotate','-i',str(path),'-map','0:V:0','-an','-sn','-dn','-threads','2',
                  '-fps_mode','passthrough','-enc_time_base','demux','-f','framemd5','-']
        from artifact_manifest import command_outputs
        with command_outputs(workflow.directory,[*command,str(evidence)]):
            run_probe(command,evidence,'Verifying decoded sample identity: '+suffix,
                      workflow.args.timeout,workflow.guard)
        if evidence.with_suffix(evidence.suffix+'.stderr').stat().st_size:
            raise ValueError('Decoder reported errors during sample recovery')
        return parse_framehash(evidence.read_text(encoding='utf-8'))
    decoded_source=decoded(source,'source',True);decoded_sample=decoded(output,'sample')
    try:
        decoded_shift=verify_decoded_slice(decoded_source,decoded_sample,shift,tolerance)
    except ValueError as error:
        if generated_pts and not workflow.hdr_mode and suffix=='.mkv' and str(error)=='Decoded reference display timing changed':
            return recover_lossless_reference(workflow,source,metadata,plan,label,original,
                                              decoded_source,decoded,packets,tolerance)
        raise
    if abs(decoded_shift-shift)>tolerance:
        raise ValueError('Recovered decoded sample alignment changed')
    checked=[]
    for stream in metadata['streams']:
        if stream['codec_type'] not in ('video','audio','subtitle'):continue
        if stream.get('disposition',{}).get('attached_pic'):continue
        a=[p for p in original if p['stream_index']==stream['index']]
        b=[p for p in copied if p['stream_index']==mapped[stream['index']]]
        if not b:
            if stream['codec_type']!='subtitle':raise ValueError('Recovered reference lost a moving/audio track')
            if any(p.get('pts_time') not in (None,'N/A') and
                   plan['keyframe_pts']<=Fraction(p['pts_time'])<plan['end_keyframe_pts'] for p in a):
                raise ValueError('Recovered reference lost subtitle events within the scene')
            continue
        extra=dict(decoded_source=decoded_source,decoded_sample=decoded_sample,
                   reorder_depth=video.get('has_b_frames',0)) if stream['index']==video['index'] else {}
        verify_source_slice(a,b,shift,tolerance=tolerance,**extra)
        checked.append(stream['index'])
    workflow.guard()
    evidence=dict(method='verified-keyframe-boundaries',plan={k:str(v) for k,v in plan.items()},
                  common_timestamp_shift=str(shift),verified_streams=checked,decoded_pictures_exact=True)
    evidence.update(generated_missing_pts=generated_pts,timestamp_tolerance_seconds=str(tolerance))
    (workflow.directory/(label+'-recovery.json')).write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return output,evidence


def compressed_window_bytes(original, copied, metadata, decoded_source, decoded_sample, shift, tolerance):
    """Conservative original payload budget; never count a lossless staging file."""
    from auto_optimize import main_video
    verify_decoded_slice(decoded_source,decoded_sample,shift,tolerance)
    video=main_video(metadata)
    starts=[i for i in range(len(decoded_source)-len(decoded_sample)+1)
            if all(a['hash']==b['hash'] and a['size']==b['size']
                   for a,b in zip(decoded_source[i:],decoded_sample))
            and abs(Fraction(decoded_sample[0]['pts'])-Fraction(decoded_source[i]['pts'])-shift)<=tolerance]
    if len(starts)!=1:raise ValueError('Lossless reference needs one original picture window')
    first=Fraction(decoded_source[starts[0]]['pts'])
    last=Fraction(decoded_source[starts[0]+len(decoded_sample)-1]['pts'])
    selected=[p for p in original if p['stream_index']==video['index'] and
              p.get('pts_time') not in (None,'N/A') and first<=Fraction(p['pts_time'])<=last]
    if len(selected)!=len(decoded_sample):
        raise ValueError('Original compressed video byte budget does not cover the decoded window')
    for source_index,output_index in copied:
        a=[p for p in original if p['stream_index']==source_index]
        b=copied[(source_index,output_index)]
        if not b:continue
        verify_source_slice(a,b,shift,tolerance=tolerance)
        matches=[i for i in range(len(a)-len(b)+1)
                 if all(x['data_hash']==y['data_hash'] for x,y in zip(a[i:],b)) and
                 abs(Fraction(b[0]['pts_time'])-Fraction(a[i]['pts_time'])-shift)<=tolerance]
        if len(matches)!=1:raise ValueError('Ambiguous original copied-track byte budget')
        selected.extend(a[matches[0]:matches[0]+len(b)])
    sizes=[int(p['size']) for p in selected]
    if not sizes or any(size<=0 for size in sizes):raise ValueError('Missing original compressed packet sizes')
    return sum(sizes)


def recover_lossless_reference(workflow,source,metadata,plan,label,original,decoded_source,decoded,packets,tolerance):
    """Repair only the staging representation, with independent source proof."""
    from auto_optimize import main_video,paired_streams
    from media_metadata import equivalent_ratio
    import legacy_color
    video=main_video(metadata)
    start,end=plan['keyframe_pts'],plan['end_keyframe_pts']
    origin=Fraction(metadata['format'].get('start_time','0'))
    decimal=lambda value:format(float(value),'.9f')
    output=workflow.directory/(label+'-lossless.mkv')
    command=[workflow.args.ffmpeg,'-hide_banner','-nostdin','-n','-xerror','-copyts',
             '-ss',decimal(start-origin),*workflow.reader_input_options(source),*workflow.decoder_options(source),
             '-i',str(source),'-ss',decimal(start),'-t',decimal(end-start),'-map','0','-c','copy',
             '-c:v:0','ffv1','-level:v:0','3','-g:v:0','1','-slicecrc:v:0','1','-threads:v:0','2',
             '-pix_fmt:v:0',video['pix_fmt'],'-fps_mode:v:0','passthrough','-enc_time_base:v:0','demux',
             '-map_chapters','-1','-avoid_negative_ts','disabled','-output_ts_offset','0',
             '-progress','pipe:1','-nostats',str(output)]
    workflow.execute(workflow.preserve_covers(command,source,metadata,label+'-lossless'),
                     'Preparing verified lossless source window',float(end-start))
    after=workflow.probe(output);moving=main_video(after)
    if moving.get('codec_name')!='ffv1':raise ValueError('Lossless source window codec changed')
    for key in ('width','height','pix_fmt',*legacy_color.FIELDS):
        if video.get(key) not in legacy_color.UNKNOWN and video.get(key)!=moving.get(key):
            raise ValueError('Lossless source window changed '+key)
    if not equivalent_ratio(video.get('sample_aspect_ratio','1:1'),moving.get('sample_aspect_ratio','1:1')):
        raise ValueError('Lossless source window changed pixel aspect ratio')
    decoded_sample=decoded(output,'lossless-sample')
    shift=verify_decoded_slice(decoded_source,decoded_sample,-start,tolerance)
    copied=packets(output,'lossless-sample')
    copied_tracks={}
    for a,b in paired_streams(metadata,after):
        if a['index']==video['index']:continue
        if a['codec_type'] not in ('audio','subtitle'):continue
        if a.get('codec_name')!=b.get('codec_name'):raise ValueError('Lossless source window changed copied codec')
        rows=[p for p in copied if p['stream_index']==b['index']]
        if not rows:
            if a['codec_type']!='subtitle':raise ValueError('Lossless source window lost an audio track')
            if any(p['stream_index']==a['index'] and p.get('pts_time') not in (None,'N/A') and
                   start<=Fraction(p['pts_time'])<end for p in original):
                raise ValueError('Lossless source window lost subtitle events')
        copied_tracks[(a['index'],b['index'])]=rows
    budget=compressed_window_bytes(original,copied_tracks,metadata,decoded_source,decoded_sample,shift,tolerance)
    workflow.guard()
    evidence=dict(method='verified-lossless-source-window',plan={k:str(v) for k,v in plan.items()},
                  common_timestamp_shift=str(shift),decoded_pictures_exact=True,decoded_timing_preserved=True,
                  copied_tracks_exact=True,compressed_source_bytes=budget,size_basis='original-compressed-packet-payloads',
                  working_bytes=output.stat().st_size,timestamp_tolerance_seconds=str(tolerance))
    (workflow.directory/(label+'-lossless-recovery.json')).write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return output,evidence
