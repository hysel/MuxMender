"""Restore a copied DTS terminal duration from complete source packet evidence.

This restores output metadata, never changes a validation tolerance. Publication
still requires the normal complete metadata, packet, decoded-audio and video tests.
"""
from fractions import Fraction
import json
from pathlib import Path


def terminal_plan(source, output, time_base, sample_rate, frame_samples):
    """Accept only one lost terminal duration with identical bytes and clocks."""
    if not source or len(source)!=len(output):
        raise ValueError('DTS duration restoration requires equal packet inventories')
    # Do not turn this narrowly scoped repair into an extra gate for files
    # whose durations already match. Normal validation remains authoritative.
    if all(a.get('duration_time')==b.get('duration_time') for a,b in zip(source,output)):
        return None
    changes=[]
    for index,(left,right) in enumerate(zip(source,output)):
        for key in ('data_hash','size','flags','side_data_list'):
            if key=='data_hash' and not left.get(key):
                raise ValueError('DTS duration restoration requires packet hashes')
            if left.get(key)!=right.get(key):
                raise ValueError('DTS packet payload or side data changed')
        for key in ('pts_time','dts_time'):
            if left.get(key) is None or right.get(key) is None or Fraction(left[key])!=Fraction(right[key]):
                raise ValueError('DTS packet presentation/decode clock changed')
        a=Fraction(left['duration_time']);b=Fraction(right['duration_time'])
        if a!=b:changes.append((index,a,b))
    if not changes:return None
    if len(changes)!=1 or changes[0][0]!=len(source)-1:
        raise ValueError('DTS duration difference is not exclusively terminal')
    index,expected,observed=changes[0]
    side=source[-1].get('side_data_list',[])
    if len(side)!=1 or side[0].get('side_data_type')!='Skip Samples' or side[0].get('skip_samples',0)!=0:
        raise ValueError('DTS terminal duration lacks unchanged discard-padding evidence')
    padding=side[0].get('discard_padding')
    if (type(sample_rate) is not int or sample_rate<=0 or type(frame_samples) is not int
            or type(padding) is not int or not 0<padding<frame_samples):
        raise ValueError('Invalid decoded DTS frame-size/padding evidence')
    base=Fraction(time_base);ticks=expected/base
    if base<=0 or not 0<expected<observed or ticks.denominator!=1:
        raise ValueError('DTS duration cannot be represented exactly in the output clock')
    # Matroska's integer clock may round the coded frame and padding durations.
    # No tolerance is applied by final validation; this only qualifies a repair.
    if abs(expected-Fraction(frame_samples-padding,sample_rate))>base:
        raise ValueError('DTS terminal duration does not match decoded frame padding')
    if abs(observed-Fraction(frame_samples,sample_rate))>base:
        raise ValueError('DTS output duration is not the complete padded frame')
    return dict(packet=index,duration_ticks=ticks.numerator,frame_samples=frame_samples,
                expected_seconds=str(expected),observed_seconds=str(observed))


def restore(work, source, encoded, before, label, duration):
    """Return a new owned remux only when strict packet evidence requires it."""
    from auto_optimize import paired_streams
    from task_progress import run_probe
    from job_tracking import progress
    source=Path(source);encoded=Path(encoded)
    if not any(s.get('codec_name')=='dts' and s.get('codec_type')=='audio' for s in before['streams']):
        return encoded
    identity=work.audit_identity(source)
    encoded_identity=work.audit_identity(encoded)
    after=work.probe(encoded)
    pairs=paired_streams(before,after)
    def probe(path,name,options):
        evidence=work.directory/(label+'-dts-'+name+'.json')
        run_probe([work.args.ffprobe,'-v','error',*options,'-of','json',str(path)],
                  evidence,'Checking copied DTS terminal duration',work.args.timeout,work.guard)
        if evidence.with_suffix(evidence.suffix+'.stderr').stat().st_size:
            raise ValueError('DTS duration evidence probe reported decoder errors')
        return json.loads(evidence.read_text())
    options=['-select_streams','a','-show_packets','-show_data_hash','sha256']
    original=probe(source,'source-packets',options)['packets']
    copied=probe(encoded,'output-packets',options)['packets']
    frames=None
    plans=[];audio_index=0
    for old,new in pairs:
        if old['codec_type']!='audio':continue
        if old.get('codec_name')=='dts':
            left=[p for p in original if p['stream_index']==old['index']]
            right=[p for p in copied if p['stream_index']==new['index']]
            matching=len(left)==len(right) and all(a.get('duration_time')==b.get('duration_time') for a,b in zip(left,right))
            if not matching:
                # Decode source frame sizes only when a repair might be needed;
                # matching files incur no additional source-decode gate.
                if frames is None:
                    frames=probe(source,'source-frame-sizes',['-read_intervals','%+1','-select_streams','a',
                        '-show_frames','-show_entries','frame=stream_index,nb_samples'])['frames']
                sizes=[int(f['nb_samples']) for f in frames if f.get('stream_index')==old['index'] and f.get('nb_samples')]
                if not sizes:raise ValueError('No decoded source DTS frame-size evidence')
                plan=terminal_plan(left,right,new['time_base'],int(old['sample_rate']),max(sizes))
            else:plan=None
            if plan:plans.append(dict(plan,audio_index=audio_index,source_index=old['index'],output_index=new['index']))
        audio_index+=1
    if identity!=work.audit_identity(source) or encoded_identity!=work.audit_identity(encoded):
        raise ValueError('Media changed during DTS duration evidence collection')
    # MKVToolNix may canonicalize an ISO language spelling while transporting
    # tracks. Preserve the literal source value rather than relaxing metadata
    # comparison (e.g. a terminological versus bibliographic spelling).
    languages=[dict(index=i,value=old.get('tags',{}).get('language'))
               for i,(old,new) in enumerate(pairs)
               if old.get('tags',{}).get('language') is not None and
               old.get('tags',{}).get('language')!=new.get('tags',{}).get('language')]
    if not plans and not languages:return encoded
    fixed=encoded.with_name(encoded.stem+'-original-dts-duration'+encoded.suffix)
    if fixed.exists() or fixed.is_symlink() or fixed.resolve() in (source.resolve(),encoded.resolve()):
        raise ValueError('DTS duration restoration requires a distinct new output')
    progress('Restoring original DTS terminal duration',detail='Packet bytes and clocks unchanged; full validation still required')
    command=[work.args.ffmpeg,'-v','error','-nostdin','-n','-copyts','-i',str(encoded),
             '-map','0','-map_metadata','0','-map_chapters','0','-c','copy','-avoid_negative_ts','disabled']
    for i,(_,stream) in enumerate(pairs):
        command += [f'-disposition:{i}','+'.join(k for k,v in stream.get('disposition',{}).items() if v) or '0']
    for item in languages:
        command += [f"-metadata:s:{item['index']}",'language='+item['value']]
    for plan in plans:
        index=plan['audio_index']
        expression=r'setts=duration=if(eq(N\,'+str(plan['packet'])+r')\,'+str(plan['duration_ticks'])+r'\,DURATION)'
        command += [f'-frame_size:a:{index}',str(plan['frame_samples']),f'-bsf:a:{index}',expression]
    command += ['-progress','pipe:1','-nostats',str(fixed)]
    work.execute(command,label+'-dts-duration-copy',duration)
    if identity!=work.audit_identity(source) or encoded_identity!=work.audit_identity(encoded):
        raise ValueError('Media changed during DTS duration remux')
    (work.directory/(label+'-dts-duration-restoration.json')).write_text(json.dumps(
        dict(plans=plans,restored_source_languages=languages,validation_required=True,
             input_packet_bytes_verified=bool(plans)),indent=2))
    return fixed
