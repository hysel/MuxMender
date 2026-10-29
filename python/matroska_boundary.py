"""Recover a bounded Matroska read view without changing its container bytes.

Only bytes after a finite, declared Segment are excluded from the working copy.
Original input, copied media packets and every conversion check remain separate.
"""
import hashlib
import re
import time
from pathlib import Path


def element(stream,identifier=False):
    first=stream.read(1)
    if not first:raise ValueError('Missing EBML element')
    width=1;mask=128
    while not first[0]&mask:
        width+=1;mask>>=1
        if width>8:raise ValueError('Invalid EBML element')
    if identifier and width>4:raise ValueError('Invalid EBML identifier')
    raw=first+stream.read(width-1)
    if len(raw)!=width:raise ValueError('Incomplete EBML element')
    value=int.from_bytes(raw,'big')
    return (value if identifier else value&((1<<(7*width))-1)),width


def declared_boundary(source,guard=lambda:None):
    source=Path(source);size=source.stat().st_size
    with source.open('rb') as stream:
        if element(stream,True)[0]!=0x1a45dfa3:raise ValueError('Not an EBML container')
        length,width=element(stream)
        if length==(1<<(7*width))-1 or stream.tell()+length>=size:
            raise ValueError('Incomplete EBML header')
        stream.seek(length,1)
        if element(stream,True)[0]!=0x18538067:raise ValueError('No declared Matroska Segment')
        length,width=element(stream);start=stream.tell();end=start+length
        if length==(1<<(7*width))-1 or not start<end<size:return None
        # Never hide a second container/Segment behind padding. The recovered
        # read is for one finite Segment, not concatenated or linked inputs.
        stream.seek(end);previous=b''
        while chunk:=stream.read(1024*1024):
            guard()
            joined=previous+chunk
            if any(marker in joined for marker in (b'\x1a\x45\xdf\xa3',b'\x18\x53\x80\x67')):
                raise ValueError('Additional container data follows the declared Segment')
            previous=joined[-3:]
    return dict(segment_start=start,segment_end=end,trailing_bytes=size-end)


def applicable(metadata,error):
    names=set(metadata.get('format',{}).get('format_name','').split(','))
    if not names or not names<={'matroska','webm'}:return False
    text=str(error)
    if re.search(r'out of memory|cannot allocate|permission denied|input/output error|no space left',text,re.I):return False
    return bool(re.search(r'Element at 0x[0-9a-f]+ ending at 0x[0-9a-f]+ exceeds containing master element ending at 0x[0-9a-f]+|Truncating packet of size [0-9]+ to [0-9]+',text))


def prepare(work,source,metadata,source_sha256,error):
    """Return a verified read view or decline; never reinterpret audio errors."""
    if not applicable(metadata,error):return None
    work.guard()
    try:layout=declared_boundary(source,work.guard)
    except ValueError:return None
    if layout is None:return None
    from artifact_manifest import command_outputs
    from auto_optimize import main_video,metadata_check
    from task_progress import digest
    from job_tracking import progress
    from dvd_av1_batch import save
    source=Path(source);before=work.audit_identity(source)
    target=work.directory/'input-reader-view.mkv'
    work.guard()
    if target.exists() or target.is_symlink():raise ValueError('Input read view requires a new file')
    original=work.probe(source)
    progress('Recovering the declared container boundary',
        detail='Creating an exact working copy of the complete Segment; original packets and clocks stay unchanged')
    remaining=layout['segment_end'];hashed=hashlib.sha256();reported=time.monotonic()
    with command_outputs(work.directory,[str(target)]):
        with source.open('rb') as incoming,target.open('xb') as outgoing:
            while remaining:
                work.guard();chunk=incoming.read(min(16*1024*1024,remaining))
                if not chunk:raise ValueError('Source ended before its declared container boundary')
                outgoing.write(chunk);hashed.update(chunk);remaining-=len(chunk)
                if time.monotonic()-reported>=5:
                    progress('Recovering the declared container boundary',
                        completed=layout['segment_end']-remaining,total=layout['segment_end'],unit='bytes',
                        stage_percent=100*(1-remaining/layout['segment_end']),
                        detail='Copying original container bytes; no re-encoding or timing changes')
                    reported=time.monotonic()
    work.guard()
    if work.audit_identity(source)!=before:raise ValueError('Source changed during container recovery')
    checksum=hashed.hexdigest()
    if digest(target,work.guard)!=checksum:raise ValueError('Input read view failed its complete byte check')
    work.reader_source_paths.add(str(target.resolve()))
    after=work.probe(target)
    metadata_check(original,after,main_video(original)['codec_name'])
    proof=dict(method='exact-declared-matroska-segment',**layout,
        source_sha256=source_sha256,view_sha256=checksum,view=str(target),
        original_unchanged=True,complete_prefix_bytes_verified=True,
        header_metadata_preserved=True,full_conversion_validation_required=True)
    save(work.directory/'source-container-boundary.json',proof)
    work.reader_learning_sources.add(str(target.resolve()))
    return target,proof
