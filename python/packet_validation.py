"""One demux/hash pass per file, with bounded-memory per-track evidence.

Video packet hashes are collected but not compared (video is re-encoded). Track
interleaving may change in a remux, so comparisons remain ordered *per stream*.
"""
from contextlib import ExitStack
import re
from pathlib import Path
from task_progress import run_probe
from job_tracking import progress
from fractions import Fraction
from itertools import zip_longest


def packet_rows(path):
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield dict(item.split('=',1) for item in line.strip().split('|') if '=' in item)


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
                    duration=None, start=0):
    if not indices:return {}
    combined=Path(directory)/(label+'-all-packets.txt')
    # Excluding packet side-data fields keeps each packet on one compact line.
    # No decoding is requested here; existing full decode/frame checks remain.
    command=[ffprobe,'-v','error','-show_packets','-show_data_hash','sha256',
             '-show_entries','packet=stream_index,pts_time,dts_time,duration_time,data_hash:packet_side_data=',
             '-of','compact=p=0',str(source)]
    run_probe(command,combined,'Checking all copied tracks: '+label,timeout,guard,duration,start)
    return split_packet_evidence(combined,directory,label,indices,guard)
