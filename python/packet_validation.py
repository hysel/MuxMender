"""Bounded-memory, complete per-track packet evidence.

Small track sets use selected reads to avoid hashing re-encoded video. Larger
sets retain one combined pass to bound storage rereads. Track interleaving may
change in a remux, so comparisons remain ordered *per stream*. The separate
complete duration-header proof is unaffected.
"""
from contextlib import ExitStack,closing
import re
from pathlib import Path
from task_progress import run_probe
from job_tracking import progress
from fractions import Fraction
from itertools import zip_longest
import sqlite3
import tempfile


def packet_rows(path):
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield dict(item.split('=',1) for item in line.strip().split('|') if '=' in item)


def nearest_tick(value):
    """FFmpeg's nearest-tick rescaling, with half ticks away from zero."""
    sign=-1 if value<0 else 1
    value=abs(value)
    return sign*((2*value.numerator+value.denominator)//(2*value.denominator))


def native_packet_ticks(packet,key,base):
    """Resolve an integer clock, checking its serialized microsecond witness."""
    value=Fraction(packet[key+'_time'])
    raw=packet.get(key)
    if raw is None:
        # Older retained evidence has only six-decimal timestamps. Recover an
        # integer only when its native tick is larger than that uncertainty.
        if base<=Fraction(1,1000000):raise ValueError('Integer packet clock evidence required')
        ticks=nearest_tick(value/base)
    else:
        if not re.fullmatch(r'-?\d+',raw):raise ValueError('Invalid integer packet clock')
        ticks=int(raw)
    if abs(ticks*base-value)>Fraction(1,2000000):
        raise ValueError('Packet clock and serialized timestamp disagree')
    return ticks


def native_video_clock_evidence(source,output,before,after,count,guard):
    """Compare every video clock after exact integer rescaling; no tolerance."""
    source_base=Fraction(str(before.get('time_base','0')));target_base=Fraction(str(after.get('time_base','0')))
    if not 0<source_base<target_base<=Fraction(1,500):
        raise ValueError('Not a finer-to-coarser video clock representation')
    progress('Verifying exact video packet clocks',
        detail='Comparing every packet on the output clock; timestamps and durations must match exactly after rescaling')
    def clocks(path,video,project):
        base=source_base if project else target_base
        for packet in packet_rows(path):
            guard()
            if int(packet['stream_index'])!=video['index']:continue
            pts=native_packet_ticks(packet,'pts',base)
            duration=native_packet_ticks(packet,'duration',base)
            if project:
                pts=nearest_tick(pts*base/target_base)
                duration=(duration*base/target_base).__floor__()
            if duration<=0:raise ValueError('Video packet duration is unresolved')
            yield pts,duration
    checked=0
    # Codec decoder delay is not a bound on packet reorder depth. Compare in
    # presentation order using a small disk-backed index, not a whole-film list
    # or a guessed GOP window. Only generated packet evidence is indexed.
    from artifact_manifest import command_outputs
    with ExitStack() as contexts:
        scratch=contexts.enter_context(tempfile.TemporaryDirectory(prefix='.packet-clock-',dir=Path(output).parent))
        index=Path(scratch)/'clocks.sqlite'
        contexts.enter_context(command_outputs(Path(output).parent,[str(index),str(index)+'-journal']))
        db=contexts.enter_context(closing(sqlite3.connect(str(index))))
        db.execute('PRAGMA cache_size=-2048')
        db.execute('CREATE TABLE clocks (side INTEGER, pts INTEGER, duration INTEGER, PRIMARY KEY(side,pts)) WITHOUT ROWID')
        for side,(path,video) in enumerate(((source,before),(output,after))):
            batch=[]
            try:
                for pts,duration in clocks(path,video,side==0):
                    batch.append((side,pts,duration))
                    if len(batch)>=2048:db.executemany('INSERT INTO clocks VALUES(?,?,?)',batch);batch=[]
                if batch:db.executemany('INSERT INTO clocks VALUES(?,?,?)',batch)
            except sqlite3.IntegrityError as exc:
                raise ValueError('Video presentation timestamps are not unique') from exc
        for left,right in zip_longest(db.execute('SELECT pts,duration FROM clocks WHERE side=0 ORDER BY pts'),
                                     db.execute('SELECT pts,duration FROM clocks WHERE side=1 ORDER BY pts')):
            guard()
            if left is None or right is None or left!=right:
                raise ValueError('Video packet clocks do not project exactly')
            checked+=1
    if checked!=count:raise ValueError('Video packets and verified decoded frame count differ')
    return dict(method='exact-native-video-clock-rescaling',source_index=before['index'],output_index=after['index'],
                source_time_base=before['time_base'],output_time_base=after['time_base'],
                packets=checked,verified_decoded_frames=count,all_packet_clocks_exact=True,
                pts_rounding='nearest-tick-half-away-from-zero',duration_rounding='whole-output-ticks')


def duration_header_evidence(before, after, reference, output, guard=lambda: None, *, verified_frame_count=None):
    """Prove an elapsed-length versus absolute-end header representation case.

    Copied streams retain exact spans/counts. A re-encoded video's clock can
    instead be proved by exact rescaling after its full decoded frame audit.
    Neither route replaces decoded frame or copied-packet comparisons.
    """
    from auto_optimize import paired_streams, is_cover
    pairs=[(a,b) for a,b in paired_streams(before,after)
           if a.get('codec_type')!='attachment' and not is_cover(a)]
    if not pairs:raise ValueError('No timed streams for duration proof')
    def spans(path, indices):
        result={index:None for index in indices}
        for packet in packet_rows(path):
            guard()
            index=int(packet['stream_index'])
            if index not in result:continue
            start=Fraction(packet['pts_time']);duration=Fraction(packet['duration_time'])
            if duration<=0:raise ValueError('Packet duration is unresolved')
            old=result[index]
            result[index]=(1,start,start+duration) if old is None else (
                old[0]+1,min(start,old[1]),max(start+duration,old[2]))
        if any(value is None for value in result.values()):raise ValueError('Incomplete packet duration inventory')
        return result
    left=spans(reference,[a['index'] for a,b in pairs])
    right=spans(output,[b['index'] for a,b in pairs])
    projection=None
    for a,b in pairs:
        if left[a['index']]!=right[b['index']]:
            if (projection is not None or a.get('codec_type')!='video' or
                    type(verified_frame_count) is not int or verified_frame_count<=0 or
                    left[a['index']][0]!=right[b['index']][0] or left[a['index']][0]!=verified_frame_count):
                raise ValueError('Timed stream packet extent or count changed')
            projection=native_video_clock_evidence(reference,output,a,b,verified_frame_count,guard)
    spans=[(min(row[1] for row in values.values()),max(row[2] for row in values.values())) for values in (left,right)]
    start,end=spans[0];elapsed=end-start
    if start==0 or elapsed<=0:raise ValueError('Not an offset duration-header case')
    # No widened timing tolerance: allow only the serialized microsecond tick.
    tick=Fraction(1,1000000)
    modes=[]
    for data,(native_start,native_end) in zip((before,after),spans):
        header=Fraction(str(data['format']['duration']))
        declared_start=Fraction(str(data['format']['start_time']))
        if abs(declared_start-native_start)>tick:raise ValueError('Declared start differs from packet evidence')
        mode=next((name for name,value in [('elapsed',native_end-native_start),('absolute-end',native_end)] if abs(header-value)<=tick),None)
        if mode is None:raise ValueError('Duration header matches neither packet span nor endpoint')
        modes.append(mode)
    if modes[0]==modes[1]:raise ValueError('Not a duration representation difference')
    return dict(kind='elapsed-versus-absolute-end',headers=[str(data['format']['duration']) for data in (before,after)],
                starts=[str(data['format']['start_time']) for data in (before,after)],
                packet_start=str(start),packet_end=str(end),elapsed=str(elapsed),
                streams=len(pairs),complete_packet_spans_equal=projection is None,
                **(dict(native_video_clock_projection=projection,copied_stream_spans_equal=True,
                        output_packet_start=str(spans[1][0]),output_packet_end=str(spans[1][1])) if projection else {}))


def aac_initialization_timestamp_case(reference, output, *, missing_initial_duration=False):
    """Recognize one anomalous initial AAC PTS, with all packet bytes intact.

    This is not approval. Full decoded PCM and presentation timing must pass.
    PTS repair additionally requires proof that the first packet emits no audio;
    a missing first duration alone does not imply a non-output packet.
    """
    first=[];count=0
    try:
        for index,pair in enumerate(zip_longest(packet_rows(reference),packet_rows(output))):
            a,b=pair
            if a is None or b is None or a['data_hash']!=b['data_hash']:return False
            if index<2:first.append((a,b))
            for key in ('pts_time','dts_time','duration_time'):
                if index==0 and key==('duration_time' if missing_initial_duration else 'pts_time'):continue
                if abs(Fraction(a[key])-Fraction(b[key]))>Fraction(1,500):return False
            count+=1
        if count<2:return False
        a,b=first[0];next_a,next_b=first[1]
        if missing_initial_duration:
            return (b.get('duration_time') in (None,'N/A') and
                    Fraction(a['duration_time'])>0 and
                    Fraction(next_a['pts_time'])>Fraction(a['pts_time']) and
                    Fraction(next_b['pts_time'])>Fraction(b['pts_time']))
        pts,dts,duration=(Fraction(a[k]) for k in ('pts_time','dts_time','duration_time'))
        return (duration>0 and pts-dts==duration and
                pts==Fraction(next_a['pts_time']) and
                Fraction(b['pts_time'])==Fraction(b['dts_time']) and
                Fraction(next_b['pts_time'])>Fraction(b['pts_time']))
    except (KeyError,ValueError,ZeroDivisionError,TypeError):
        return False


def aac_terminal_duration_case(reference, output, *, preserved_priming=False):
    """Recognize only a shortened final packet; decoded proof is still mandatory."""
    count=0;mismatch=None;previous=None;last=None
    try:
        for a,b in zip_longest(packet_rows(reference),packet_rows(output)):
            count+=1
            if a is None or b is None or a['data_hash']!=b['data_hash']:return None
            for key in ('pts_time','dts_time'):
                if abs(Fraction(a[key])-Fraction(b[key]))>Fraction(1,500):return None
            if (preserved_priming and count==1 and b.get('duration_time') in (None,'N/A')
                    and Fraction(a['duration_time'])>0):
                continue
            x,y=Fraction(a['duration_time']),Fraction(b['duration_time'])
            if x<=0 or y<=0:return None
            if abs(x-y)>Fraction(1,500):
                if mismatch is not None:return None
                mismatch=count
            previous,last=last,(x,y)
        if count<2 or mismatch!=count or previous is None:return None
        if not (last[0]<previous[0]<=Fraction(1,10) and abs(last[1]-previous[0])<=Fraction(1,500)):return None
        return count
    except (KeyError,ValueError,ZeroDivisionError,TypeError):return None


def audio_hash_rows(path):
    time_base=None
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('#tb 0:'):
                time_base=Fraction(line.split(':',1)[1].strip())
            if not line.strip() or line.startswith('#'):continue
            values=[v.strip() for v in line.split(',')]
            if (time_base is None or time_base<=0 or len(values)!=6 or values[0]!='0'
                    or not re.fullmatch('[0-9a-f]{64}',values[5]) or int(values[3])<=0):
                raise ValueError('Invalid decoded audio hash evidence')
            yield dict(pts=Fraction(values[2])*time_base,
                       duration=Fraction(values[3])*time_base,size=int(values[4]),hash=values[5])


def missing_audio_duration_case(reference, output):
    """Representation candidate only; requires independent decoded audio proof."""
    count=0;missing=False
    try:
        for a,b in zip_longest(packet_rows(reference),packet_rows(output)):
            if a is None or b is None or not a.get('data_hash') or a['data_hash']!=b.get('data_hash'):return None
            for key in ('pts_time','dts_time'):
                if abs(Fraction(a[key])-Fraction(b[key]))>Fraction(1,500):return None
            left,right=a.get('duration_time'),b.get('duration_time')
            if right in (None,'N/A') and left not in (None,'N/A'):
                if Fraction(left)<=0:return None
                missing=True
            elif left!=right and abs(Fraction(left)-Fraction(right))>Fraction(1,500):return None
            count+=1
        return count if count and missing else None
    except (KeyError,ValueError,TypeError,ZeroDivisionError):return None


def reconstructed_audio_timestamp_case(reference, output):
    """Candidate evidence only: identical payloads, interior absent source PTS.

    Callers must restrict the codec and independently compare complete decoded
    PCM, sample counts and presentation timing before accepting this case.
    """
    count=0;changed=False;pending=[];previous=None
    try:
        for a,b in zip_longest(packet_rows(reference),packet_rows(output)):
            if a is None or b is None or not re.fullmatch(r'SHA256:[0-9a-fA-F]{64}',a.get('data_hash','')) or a['data_hash']!=b.get('data_hash'):return None
            count+=1
            for key in ('duration_time','pts_time','dts_time'):
                left,right=a.get(key),b.get(key)
                if left==right:continue
                if key in ('pts_time','dts_time') and left in (None,'N/A') and right not in (None,'N/A'):
                    if previous is None:return None
                    value=Fraction(right)
                    if value<previous:return None
                    pending.append(value);changed=True
                elif left in (None,'N/A') or right in (None,'N/A') or abs(Fraction(left)-Fraction(right))>Fraction(1,500):return None
            if a.get('pts_time') not in (None,'N/A'):
                anchor=Fraction(a['pts_time'])
                if previous is not None and anchor<previous:return None
                if pending and max(pending)>anchor+Fraction(1,500):return None
                pending=[];previous=anchor
        return count if changed and not pending else None
    except (ValueError,TypeError,ZeroDivisionError,KeyError):return None


def compare_decoded_audio(reference, output, expected_first_source=None, expected_first_output=None):
    if (expected_first_source is None)!=(expected_first_output is None):
        raise ValueError('Both initial audio anchors are required together')
    count=0;max_delta=Fraction(0);previous=[None,None]
    for a,b in zip_longest(audio_hash_rows(reference),audio_hash_rows(output)):
        if a is None or b is None:raise ValueError('Decoded audio frame count changed')
        if any(a[k]!=b[k] for k in ('duration','size','hash')):
            raise ValueError('Decoded audio payload/sample count changed')
        delta=abs(a['pts']-b['pts']);max_delta=max(max_delta,delta)
        if delta>Fraction(1,500):raise ValueError('Decoded audio presentation timing changed')
        if count==0 and expected_first_source is not None and (abs(a['pts']-Fraction(expected_first_source))>Fraction(1,500) or
                        abs(b['pts']-Fraction(expected_first_output))>Fraction(1,500)):
            raise ValueError('Initial AAC packet is not proven non-output')
        for i,item in enumerate((a,b)):
            if previous[i] is not None and item['pts']<=previous[i]:
                raise ValueError('Non-increasing decoded audio timeline')
            previous[i]=item['pts']
        count+=1
    if count==0:raise ValueError('No decoded audio evidence')
    return dict(frames=count,max_timestamp_delta_seconds=float(max_delta),pcm_identical=True,
                non_output_initial_packet_verified=expected_first_source is not None)


def split_packet_evidence(combined, directory, label, indices, guard=lambda:None):
    indices=set(indices)
    if any(type(i) is not int or i<0 for i in indices):raise ValueError('Invalid copied stream index')
    paths={i:Path(directory)/(label+f'-stream-{i}.txt') for i in indices}
    counts={i:0 for i in indices}
    total=combined.stat().st_size;processed=0
    progress('Organizing copied-track evidence',detail='Separating audio/subtitle records from one media pass')
    with ExitStack() as stack:
        handles={i:stack.enter_context(path.open('x',encoding='utf-8')) for i,path in paths.items()}
        source=stack.enter_context(combined.open(encoding='utf-8'))
        for number,line in enumerate(source):
            processed+=len(line.encode('utf-8'))
            if number%4096==0:
                guard();progress('Organizing copied-track evidence',stage_percent=min(99.9,100*processed/total) if total else None,
                                 detail=f'{number} packet records inspected')
            if not line.strip():continue
            row=dict(item.split('=',1) for item in line.strip().split('|') if '=' in item)
            try:index=int(row['stream_index'])
            except (KeyError,ValueError) as exc:raise ValueError('Missing/invalid packet stream identity') from exc
            if index not in indices:continue
            if not re.fullmatch(r'SHA256:[0-9a-fA-F]{64}',row.get('data_hash','')):
                raise ValueError(f'Missing/invalid packet hash for stream {index}')
            handles[index].write(line if line.endswith('\n') else line+'\n');counts[index]+=1
    guard()
    progress('Organizing copied-track evidence',stage_percent=100,detail=f'{sum(counts.values())} copied packets in {len(indices)} tracks')
    return paths


def collect_packets(ffprobe, source, directory, label, indices, timeout, guard,
                    duration=None, start=0, *, input_options=()):
    if not indices:return {}
    if any(type(i) is not int or i<0 for i in indices):
        raise ValueError('Invalid copied stream index')
    indices=sorted(set(indices))
    if len(indices)<=2:
        paths={}
        for position,index in enumerate(indices,1):
            guard()
            target=Path(directory)/(label+f'-stream-{index}.txt')
            command=[ffprobe,'-v','error',*input_options,'-select_streams',str(index),
                     '-show_packets','-show_data_hash','sha256','-show_entries',
                     'packet=stream_index,pts_time,dts_time,duration_time,data_hash:packet_side_data=',
                     '-of','compact=p=0',str(source)]
            run_probe(command,target,f'Checking copied track: {label} · {position}/{len(indices)}',
                      timeout,guard,duration,start)
            errors=target.with_suffix(target.suffix+'.stderr')
            if not errors.is_file() or errors.stat().st_size:
                raise ValueError('Selected packet reader did not produce clean error evidence: '+errors.name)
            for number,row in enumerate(packet_rows(target)):
                if number%4096==0:guard()
                if row.get('stream_index')!=str(index):
                    raise ValueError('Selected packet stream identity changed')
                if not re.fullmatch(r'SHA256:[0-9a-fA-F]{64}',row.get('data_hash','')):
                    raise ValueError(f'Missing/invalid packet hash for stream {index}')
            paths[index]=target
        guard()
        return paths
    combined=Path(directory)/(label+'-all-packets.txt')
    # Excluding packet side-data fields keeps each packet on one compact line.
    # No decoding is requested here; existing full decode/frame checks remain.
    command=[ffprobe,'-v','error',*input_options,'-show_packets','-show_data_hash','sha256',
             '-show_entries','packet=stream_index,pts_time,dts_time,duration_time,data_hash:packet_side_data=',
             '-of','compact=p=0',str(source)]
    run_probe(command,combined,'Checking all copied tracks: '+label,timeout,guard,duration,start)
    return split_packet_evidence(combined,directory,label,indices,guard)
