"""Keyframe sample planning and source-identity checks.

Used only as an evidence-verified recovery from excessive sample preroll.
No decoded/re-encoded reference is accepted as ground truth.
"""
from fractions import Fraction
import json


def plan_keyframe(packets, time_base, requested, seconds, source_end, search_span=None):
    tick = Fraction(time_base)
    requested, seconds, source_end = map(Fraction, map(str, (requested, seconds, source_end)))
    search_span=seconds if search_span is None else Fraction(str(search_span))
    if tick <= 0 or seconds <= 0 or search_span<seconds or search_span>60 or requested < 0 or source_end <= requested:
        raise ValueError('Invalid sampling bounds')
    choices = []
    for packet in packets:
        if 'K' not in packet.get('flags', '') or 'D' in packet.get('flags', ''):
            continue
        if packet.get('pts_time') in (None, 'N/A') or packet.get('dts_time') in (None, 'N/A'):
            continue
        pts, dts = Fraction(packet['pts_time']), Fraction(packet['dts_time'])
        # Keep the selected scene nearby and leave room for the entire sample.
        if requested <= pts <= requested + search_span and pts + seconds <= source_end and dts >= tick:
            choices.append((pts, dts))
    if not choices:
        raise ValueError('No verified keyframe within sampling bounds')
    pts, dts = min(choices)
    ends=[]
    for packet in packets:
        if 'K' not in packet.get('flags','') or 'D' in packet.get('flags',''):
            continue
        if packet.get('pts_time') in (None,'N/A') or packet.get('dts_time') in (None,'N/A'):
            continue
        end_pts,end_dts=Fraction(packet['pts_time']),Fraction(packet['dts_time'])
        if pts+seconds<=end_pts<=min(source_end,pts+2*search_span) and end_dts>dts:
            ends.append((end_pts,end_dts))
    if not ends:
        raise ValueError('No complete GOP boundary within sampling bounds')
    end_pts,end_dts=min(ends)
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
    matches = [i for i in range(len(source)-len(sample)+1)
               if all(a['data_hash'] == b['data_hash']
                      for a, b in zip(source[i:i+len(sample)], sample))
               and (expected_shift is None or
                    (source[i].get('pts_time') not in (None,'N/A') and sample[0].get('pts_time') not in (None,'N/A')
                     and abs(Fraction(sample[0]['pts_time'])-Fraction(source[i]['pts_time'])-expected_shift)<=tolerance))]
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


def recover_reference(workflow, source, metadata, position, seconds, label):
    """Bounded recovery for excessive preroll; prove source identity before use."""
    from task_progress import run_probe
    video=next(s for s in metadata['streams'] if s['codec_type']=='video')
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
        command=[workflow.args.ffprobe,'-v','error',*workflow.decoder_options(path),*(input_options if path==source else [])]
        if interval:command+=['-read_intervals',interval]
        command+=['-show_packets','-show_data_hash','sha256','-show_entries',
                  'packet=stream_index,pts_time,dts_time,duration_time,data_hash,flags','-of','json',str(path)]
        run_probe(command,evidence,'Checking sample source packets: '+suffix,
                  workflow.args.timeout,workflow.guard,float(end-begin),float(begin))
        if evidence.with_suffix(evidence.suffix+'.stderr').stat().st_size:
            raise ValueError('Packet reader reported errors during sample recovery')
        return json.loads(evidence.read_text(encoding='utf-8'))['packets']
    original=packets(source,'source',decimal(begin)+'%'+decimal(end))
    selected=[p for p in original if p['stream_index']==video['index']]
    plan=plan_keyframe(selected,video['time_base'],target,span,origin+Fraction(metadata['format']['duration']),search_span)
    if generated_pts:
        # MPEG-4 B pictures preceding the boundary depend on its future I/P
        # picture. Include that boundary packet rather than flushing without it.
        # Exact decoded-source comparison below must still certify every frame.
        plan['seconds']+=Fraction(video['time_base'])
    output=workflow.directory/(label+'.mkv')
    command=[workflow.args.ffmpeg,'-hide_banner','-nostdin','-n',*input_options,'-ss',decimal(plan['seek']-origin),
             '-i',str(source),'-ss','0','-t',decimal(plan['seconds']),'-map','0','-c','copy',
             '-map_chapters','-1','-avoid_negative_ts','make_zero','-progress','pipe:1','-nostats',str(output)]
    workflow.execute(workflow.preserve_covers(command,source,metadata,label),label,float(plan['seconds']))
    copied=packets(output,'sample')
    vcopy=[p for p in copied if p['stream_index']==video['index']]
    if not vcopy:raise ValueError('Recovered reference contains no video')
    if 'K' not in vcopy[0].get('flags',''):
        raise ValueError('Recovered reference does not begin with a keyframe')
    shift=Fraction(vcopy[0]['pts_time'])-plan['keyframe_pts']
    def decoded(path,suffix,is_source=False):
        evidence=workflow.directory/(label+'-'+suffix+'-decoded.md5')
        command=[workflow.args.ffmpeg,'-v','error','-nostdin','-xerror','-copyts']
        if is_source:command+=['-ss',decimal(begin-origin),'-t',decimal(end-begin)]
        command+=[*workflow.decoder_options(path),'-i',str(path),'-map','0:v:0','-an','-sn','-dn','-threads','2',
                  '-fps_mode','passthrough','-enc_time_base','1:1000000','-f','framemd5','-']
        run_probe(command,evidence,'Verifying decoded sample identity: '+suffix,
                  workflow.args.timeout,workflow.guard)
        if evidence.with_suffix(evidence.suffix+'.stderr').stat().st_size:
            raise ValueError('Decoder reported errors during sample recovery')
        return parse_framehash(evidence.read_text(encoding='utf-8'))
    decoded_source=decoded(source,'source',True);decoded_sample=decoded(output,'sample')
    if abs(verify_decoded_slice(decoded_source,decoded_sample,shift,tolerance)-shift)>tolerance:
        raise ValueError('Recovered decoded sample alignment changed')
    checked=[]
    for stream in metadata['streams']:
        if stream['codec_type'] not in ('video','audio','subtitle'):continue
        if stream.get('disposition',{}).get('attached_pic'):continue
        a=[p for p in original if p['stream_index']==stream['index']]
        b=[p for p in copied if p['stream_index']==stream['index']]
        if not b:
            if stream['codec_type']!='subtitle':raise ValueError('Recovered reference lost a moving/audio track')
            if any(p.get('pts_time') not in (None,'N/A') and
                   plan['keyframe_pts']<=Fraction(p['pts_time'])<plan['end_keyframe_pts'] for p in a):
                raise ValueError('Recovered reference lost subtitle events within the scene')
            continue
        extra=dict(decoded_source=decoded_source,decoded_sample=decoded_sample,
                   reorder_depth=video.get('has_b_frames',0)) if stream['codec_type']=='video' else {}
        verify_source_slice(a,b,shift,tolerance=tolerance,**extra)
        checked.append(stream['index'])
    workflow.guard()
    evidence=dict(method='verified-keyframe-boundaries',plan={k:str(v) for k,v in plan.items()},
                  common_timestamp_shift=str(shift),verified_streams=checked,decoded_pictures_exact=True)
    evidence.update(generated_missing_pts=generated_pts,timestamp_tolerance_seconds=str(tolerance))
    (workflow.directory/(label+'-recovery.json')).write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return output,evidence
