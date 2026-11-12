"""Restore the reference's declared duration after complete media validation.

This edits the generated container's Info element, never media packets, clocks,
track metadata or the reference. References are the original or owned samples;
normal validation still decides publication.
"""
from fractions import Fraction
from pathlib import Path
import io
import math
import struct
import zlib


class DurationHeaderError(ValueError):
    """The existing duration representation proof did not establish equality."""


def master_element(path,identifier=0x1549a966):
    from matroska_boundary import element
    with Path(path).open('rb') as stream:
        total=Path(path).stat().st_size
        if element(stream,True)[0]!=0x1a45dfa3:raise ValueError('Not an EBML container')
        length,width=element(stream)
        if length>1024*1024:raise ValueError('Unbounded EBML header')
        stream.seek(length,1)
        if element(stream,True)[0]!=0x18538067:raise ValueError('No Matroska Segment')
        segment,width=element(stream);begin=stream.tell()
        end=total if segment==(1<<(7*width))-1 else begin+segment
        if end>total:raise ValueError('Truncated Matroska Segment')
        for _ in range(4096):
            if stream.tell()>=end:break
            key=element(stream,True)[0];size,width=element(stream);position=stream.tell()
            if size==(1<<(7*width))-1 or position+size>end:raise ValueError('Unbounded Matroska header element')
            if key==identifier:
                if not 0<size<=1024*1024:raise ValueError('Invalid bounded Matroska Info')
                return position,stream.read(size)
            if key==0x1f43b675:break
            stream.seek(position+size)
    raise ValueError('No bounded Matroska Info before media clusters')


def info_element(path):
    return master_element(path)


def fields(payload):
    from matroska_boundary import element
    stream=io.BytesIO(payload);result={}
    while stream.tell()<len(payload):
        start=stream.tell();key=element(stream,True)[0];size,width=element(stream);position=stream.tell()
        if position+size>len(payload):raise ValueError('Truncated Matroska Info child')
        value=stream.read(size)
        if key in (0x4489,0x2ad7b1,0xbf):
            if key in result:raise ValueError('Ambiguous Matroska duration header')
            result[key]=(start,position,position+size,value)
    duration=result.get(0x4489)
    if duration is None or len(duration[3]) not in (4,8):raise ValueError('Missing Matroska duration float')
    value=struct.unpack('>f' if len(duration[3])==4 else '>d',duration[3])[0]
    scale=int.from_bytes(result[0x2ad7b1][3],'big') if 0x2ad7b1 in result else 1000000
    if not math.isfinite(value) or value<=0 or scale<=0:raise ValueError('Invalid Matroska duration value')
    if 0xbf in result:
        start,position,end,stored=result[0xbf]
        if len(stored)!=4 or stored!=zlib.crc32(payload[:start]+payload[end:]).to_bytes(4,'little'):
            raise ValueError('Invalid Matroska Info checksum')
    return result,Fraction(value)*scale/1000000000


def plan(source_payload,output_payload):
    _,seconds=fields(source_payload);items,_=fields(output_payload)
    scale=int.from_bytes(items[0x2ad7b1][3],'big') if 0x2ad7b1 in items else 1000000
    _,position,end,old=items[0x4489]
    value=seconds*1000000000/scale
    new=struct.pack('>f' if len(old)==4 else '>d',float(value))
    if Fraction(struct.unpack('>f' if len(old)==4 else '>d',new)[0])*scale/1000000000!=seconds:
        raise ValueError('Original duration is not exactly representable in output header')
    patched=bytearray(output_payload);patched[position:end]=new
    if 0xbf in items:
        start,position,end,_=items[0xbf]
        patched[position:end]=zlib.crc32(patched[:start]+patched[end:]).to_bytes(4,'little')
    fields(patched)
    return bytes(patched),seconds


def restore(work,source,output,before,after,label,frames):
    from artifact_manifest import registered_outputs,command_outputs
    from dvd_av1_batch import save
    from job_tracking import progress
    source=Path(source);output=Path(output);root=work.directory.resolve()
    original=getattr(work.args,'source',None)
    owned=registered_outputs(root)
    original_reference=original is not None and source.resolve()==Path(original).resolve()
    generated_reference=(not source.is_symlink() and source.resolve().parent==root and source in owned)
    if (not (original_reference or generated_reference) or
            type(frames) is not int or frames<=0 or output.is_symlink() or
            output.resolve().parent!=root or output not in owned):
        raise ValueError('Duration restoration requires the original or an owned reference and a completely audited output')
    for data in (before,after):
        names=set(data.get('format',{}).get('format_name','').split(','))
        if not names or not names<={'matroska','webm'}:raise ValueError('Duration restoration requires Matroska headers')
    old_source=work.audit_identity(source);old_output=work.audit_identity(output)
    if old_source[:2]==old_output[:2]:raise ValueError('Output shares original container bytes')
    aliases=[p for p in owned if work.audit_identity(p)[:2]==old_output[:2]]
    if output.stat().st_nlink!=len(aliases):
        raise ValueError('Duration restoration cannot change an unregistered container link')
    color=getattr(work,'color_intermediates',{}).get(output.resolve())
    hdr=getattr(work,'hdr_intermediates',{}).get(output.resolve(),[])
    for path,identity in ([color] if color else [])+list(hdr):
        if path in aliases and work.audit_identity(path)[:4]!=identity:
            raise ValueError('Owned intermediate changed before duration restoration')
    _,source_info=info_element(source);offset,output_info=info_element(output)
    patched,seconds=plan(source_info,output_info)
    if abs(seconds-Fraction(str(before['format']['duration'])))>Fraction(1,1000000):
        raise ValueError('Original declared duration differs from reader metadata')
    work.guard()
    if old_source!=work.audit_identity(source) or old_output!=work.audit_identity(output):
        raise ValueError('Media changed before original duration restoration')
    progress('Preserving the original declared playback length',
        detail='All decoded pictures and copied tracks verified; restoring container duration only')
    with command_outputs(root,[],mutated=aliases):
        with output.open('r+b') as stream:
            stream.seek(offset)
            if stream.read(len(output_info))!=output_info:raise ValueError('Generated header changed before duration restoration')
            stream.seek(offset);stream.write(patched);stream.flush()
    if old_source!=work.audit_identity(source):raise ValueError('Original changed during duration restoration')
    new_offset,new_info=info_element(output)
    if new_offset!=offset or new_info!=patched or output.stat().st_size!=old_output[2]:
        raise ValueError('Generated duration restoration failed its byte check')
    # A generated final output may share an inode with a registered encoder
    # intermediate. Rebind only these proved header mutations for later cleanup.
    if color and color[0] in aliases:
        work.color_intermediates[output.resolve()]=(color[0],work.audit_identity(color[0])[:4])
    if hdr:
        work.hdr_intermediates[output.resolve()]=[(path,work.audit_identity(path)[:4] if path in aliases else identity)
                                                for path,identity in hdr]
    proof=dict(method='original-declared-matroska-duration',original_seconds=str(seconds),
        reference_kind='original' if original_reference else 'owned-sample',
        previous_seconds=after['format']['duration'],verified_decoded_frames=frames,
        complete_copied_tracks_verified=True,media_packets_unchanged=True,
        changed_bytes='Info duration and its existing CRC only',validation_required=True)
    save(root/(label+'-original-duration-restoration.json'),proof)
    return proof
