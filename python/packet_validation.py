"""One demux/hash pass per file, with bounded-memory per-track evidence.

Video packet hashes are collected but not compared (video is re-encoded). Track
interleaving may change in a remux, so comparisons remain ordered *per stream*.
"""
from contextlib import ExitStack
import re
from pathlib import Path
from task_progress import run_probe
from job_tracking import progress


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
