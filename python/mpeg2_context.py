"""Remove an ignored picture extension from a private MPEG-2 read context.

The source and every coded media byte remain intact. Only a working copy's
decoder-initialization header is cleaned; ordinary strict validation follows.
"""
import hashlib
import io
import re
import time
import zlib
from pathlib import Path


def children(payload):
    from matroska_boundary import element
    stream=io.BytesIO(payload)
    while stream.tell()<len(payload):
        start=stream.tell();key=element(stream,True)[0];identifier_end=stream.tell()
        size,width=element(stream);position=stream.tell();end=position+size
        if end>len(payload):raise ValueError('Truncated MPEG-2 initialization container')
        stream.seek(end)
        yield dict(key=key,start=start,id_end=identifier_end,position=position,end=end,width=width,
                   value=payload[position:end])


def checksum(payload,original):
    entries=[x for x in children(original) if x['key']==0xbf]
    if len(entries)>1:raise ValueError('Ambiguous initialization header checksum')
    if entries:
        x=entries[0];a,b=x['start'],x['end']
        if len(x['value'])!=4 or x['value']!=zlib.crc32(original[:a]+original[b:]).to_bytes(4,'little'):
            raise ValueError('Invalid initialization header checksum')
        payload=bytearray(payload)
        payload[x['position']:b]=zlib.crc32(payload[:a]+payload[b:]).to_bytes(4,'little')
    return bytes(payload)


def clean_private(payload):
    """Only orphan picture-coding extensions in sequence initialization data."""
    starts=list(re.finditer(b'\x00\x00\x01',payload))
    if not starts or starts[0].start()!=0 or payload[3]!=0xb3:return None
    kept=[];removed=0;sequence_extension=False
    for i,match in enumerate(starts):
        unit=payload[match.start():starts[i+1].start() if i+1<len(starts) else len(payload)]
        if len(unit)<4:raise ValueError('Incomplete MPEG-2 initialization start code')
        kind=unit[3]
        if kind in (0,0xb8) or 1<=kind<=0xaf:
            return None  # Never alter a picture, GOP or slice stream.
        if kind==0xb5:
            if len(unit)<5:raise ValueError('Incomplete MPEG-2 extension')
            extension=unit[4]>>4
            if extension==1:sequence_extension=True
            if extension==8:
                if not sequence_extension or len(unit)!=9:return None
                removed+=len(unit);continue
        kept.append(unit)
    return (b''.join(kept),removed) if removed else None


def tracks_plan(payload):
    result=bytearray(payload);matches=[]
    for entry in children(payload):
        if entry['key']!=0xae:continue
        items=list(children(entry['value']))
        def one(key):
            found=[x for x in items if x['key']==key]
            if len(found)>1:raise ValueError('Ambiguous MPEG-2 track descriptor')
            return found[0] if found else None
        kind=one(0x83);codec=one(0x86);private=one(0x63a2)
        if not kind or int.from_bytes(kind['value'],'big')!=1 or not codec or codec['value']!=b'V_MPEG2' or not private:continue
        cleaned=clean_private(private['value'])
        if cleaned is None:continue
        value,removed=cleaned;width=private['width'];length=len(value)
        if length>=(1<<(7*width))-1:raise ValueError('Unrepresentable initialization size')
        replacement=(entry['value'][private['start']:private['id_end']]+
                     ((1<<(7*width))|length).to_bytes(width,'big')+value)
        padding=private['end']-private['start']-len(replacement)
        if not 2<=padding<=128:raise ValueError('Cannot retain initialization element offsets')
        replacement+=b'\xec'+bytes([0x80|(padding-2)])+bytes(padding-2)
        child=bytearray(entry['value']);child[private['start']:private['end']]=replacement
        result[entry['position']:entry['end']]=checksum(child,entry['value'])
        matches.append(dict(removed_initialization_bytes=removed,media_packets_changed=False))
    if len(matches)!=1:raise ValueError('Expected exactly one recoverable MPEG-2 initialization context')
    return checksum(result,payload),matches[0]


def prepare(work,source,metadata,source_sha256,error):
    from auto_optimize import main_video,metadata_check
    from matroska_duration import master_element
    from artifact_manifest import command_outputs
    from task_progress import digest
    from dvd_av1_batch import save
    from job_tracking import progress
    if main_video(metadata).get('codec_name')!='mpeg2video':return None
    if 'ignoring pic cod ext after 0' not in str(error):return None
    names=set(metadata.get('format',{}).get('format_name','').split(','))
    if not names or not names<={'matroska','webm'}:return None
    source=Path(source);identity=work.audit_identity(source)
    try:
        offset,original=master_element(source,0x1654ae6b)
        patched,detail=tracks_plan(original)
    except ValueError:return None
    target=work.directory/'mpeg2-initialization-view.mkv'
    if target.exists() or target.is_symlink():raise ValueError('Initialization view requires a new file')
    progress('Recovering original MPEG-2 decoder initialization',
        detail='Copying original media bytes; removing only an ignored orphan extension from the private read context')
    old_hash=hashlib.sha256();new_hash=hashlib.sha256();position=0;last=time.monotonic()
    with command_outputs(work.directory,[str(target)]):
        with source.open('rb') as incoming,target.open('xb') as outgoing:
            while chunk:=incoming.read(16*1024*1024):
                work.guard();old_hash.update(chunk)
                a=max(position,offset);b=min(position+len(chunk),offset+len(original))
                if a<b:
                    chunk=chunk[:a-position]+patched[a-offset:b-offset]+chunk[b-position:]
                outgoing.write(chunk);new_hash.update(chunk);position+=len(chunk)
                if time.monotonic()-last>=5:
                    progress('Recovering original MPEG-2 decoder initialization',completed=position,total=identity[2],unit='bytes',stage_percent=100*position/identity[2])
                    last=time.monotonic()
    if old_hash.hexdigest()!=source_sha256 or identity!=work.audit_identity(source):
        raise ValueError('Original changed during initialization context recovery')
    view_identity=work.audit_identity(target)
    if digest(target,work.guard)!=new_hash.hexdigest() or view_identity!=work.audit_identity(target):
        raise ValueError('Initialization view failed its complete byte verification')
    if not hasattr(work,'reader_source_evidence'):work.reader_source_evidence={}
    work.reader_source_evidence[str(target.resolve())]=dict(source=str(source.resolve()),source_identity=identity,view_identity=view_identity)
    work.reader_source_paths.add(str(target.resolve()))
    after=work.probe(target)
    metadata_check(metadata,after,'mpeg2video')
    proof=dict(method='orphan-mpeg2-private-picture-extension',**detail,
        source_sha256=source_sha256,view_sha256=new_hash.hexdigest(),view=str(target),
        original_unchanged=True,complete_nonheader_bytes_identical=True,
        validation_required=True)
    save(work.directory/'source-initialization-recovery.json',proof)
    return target,proof
