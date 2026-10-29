"""Restore explicit audio BlockDuration only in a verified generated sample.

No audio payload, PTS, DTS or decoded picture is changed. Callers repeat their
ordinary packet, decoded-picture and metadata checks before using the sample.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import io
from pathlib import Path
import zlib

from matroska_boundary import element


@dataclass
class Span:
    start:int
    body:int
    end:int
    kind:int


def size_bytes(size):
    for width in range(1,9):
        if 0<=size<(1<<(width*7))-1:return (size|(1<<(width*7))).to_bytes(width,'big')
    raise ValueError('Matroska element exceeds the size representation')


def header(kind,size):
    return kind.to_bytes((kind.bit_length()+7)//8,'big')+size_bytes(size)


def spans(stream,start,end):
    stream.seek(start)
    while stream.tell()<end:
        begin=stream.tell();kind,_=element(stream,True);size,width=element(stream);body=stream.tell()
        stop=end if size==(1<<(width*7))-1 and kind==0x18538067 else body+size
        if not body<=stop<=end:raise ValueError('Incomplete working Matroska element')
        yield Span(begin,body,stop,kind)
        stream.seek(stop)


def restore_file(sample,output,plans,guard=lambda:None):
    """Write exact original durations without a muxer re-deriving them."""
    sample,output=Path(sample),Path(output)
    if sample==output or output.exists() or output.is_symlink() or sample.is_symlink():
        raise ValueError('Duration restoration requires a distinct generated file')
    matched=set()
    with sample.open('rb') as incoming,output.open('x+b') as outgoing:
        total=sample.stat().st_size;top=list(spans(incoming,0,total))
        if len(top)!=2 or top[0].kind!=0x1a45dfa3 or top[1].kind!=0x18538067:
            raise ValueError('Duration restoration requires one complete Matroska container')
        scale=1000000
        for info in spans(incoming,top[1].body,top[1].end):
            if info.kind!=0x1549a966:continue
            for child in spans(incoming,info.body,info.end):
                if child.kind==0x2ad7b1:
                    incoming.seek(child.body);scale=int.from_bytes(incoming.read(child.end-child.body),'big')
        if scale<=0:raise ValueError('Invalid working Matroska time scale')
        converted={}
        for position,plan in plans.items():
            ticks=Fraction(plan['duration_seconds'])/Fraction(scale,1000000000)
            if ticks.denominator!=1 or ticks<=0:raise ValueError('Original packet duration is not exactly representable')
            converted[position]=dict(plan,duration=int(ticks))
        plans=converted
        def read(start,end):
            incoming.seek(start);return incoming.read(end-start)
        def raw(span):return ('raw',span.start,span.end)
        def length(piece):
            if isinstance(piece,bytes):return len(piece)
            if piece[0]=='raw':return piece[2]-piece[1]
            return len(header(piece[1],piece[3]))+piece[3]
        def node(kind,pieces):return ('node',kind,pieces,sum(map(length,pieces)))
        def crc(stream,start,end):
            value=0;stream.seek(start)
            while stream.tell()<end:
                guard();chunk=stream.read(min(1024*1024,end-stream.tell()))
                if not chunk:raise ValueError('Incomplete CRC evidence')
                value=zlib.crc32(chunk,value)
            return value
        def container(span,children):
            original=list(spans(incoming,span.body,span.end));checks=[s for s in original if s.kind==0xbf]
            if len(checks)>1:raise ValueError('Ambiguous Matroska checksum')
            if checks:
                check=checks[0]
                if check.start!=span.body or check.end-check.body!=4:
                    raise ValueError('Unsupported working checksum placement')
                value=crc(incoming,check.end,span.end);stored=read(check.body,check.end)
                endian=next((order for order in ('little','big') if value.to_bytes(4,order)==stored),None)
                if endian is None:raise ValueError('Working sample CRC is invalid')
                children=[('crc',endian)]+children
            return node(span.kind,children)
        # CRC placeholder length is fixed; all other lengths are explicit.
        old_length=length
        def length(piece):
            return 6 if not isinstance(piece,bytes) and piece[0]=='crc' else old_length(piece)
        def block(span,simple):
            plan=plans.get(span.body)
            if plan is None:return raw(span)
            incoming.seek(span.body);_,track_width=element(incoming)
            lead=read(span.body,span.body+track_width+3)
            if len(lead)!=track_width+3 or lead[-1]&6:
                raise ValueError('Duration restoration needs one copied audio packet per block')
            start=span.body+len(lead);hashed=hashlib.sha256();incoming.seek(start)
            while incoming.tell()<span.end:
                guard();data=incoming.read(min(1024*1024,span.end-incoming.tell()))
                if not data:raise ValueError('Incomplete copied audio payload')
                hashed.update(data)
            if span.end-start!=plan['size'] or 'SHA256:'+hashed.hexdigest()!=plan['data_hash']:
                raise ValueError('Audio block does not match its source packet evidence')
            matched.add(span.body)
            # SimpleBlock's key/discard bits do not belong to Block. A group
            # without ReferenceBlock remains a key packet, as audio requires.
            if simple:lead=lead[:-1]+bytes([lead[-1]&0x08])
            payload=[lead,('raw',start,span.end)]
            return node(0xa1,payload)
        def group(span):
            children=list(spans(incoming,span.body,span.end));blocks=[s for s in children if s.kind==0xa1]
            if len(blocks)!=1:raise ValueError('Ambiguous working BlockGroup')
            plan=plans.get(blocks[0].body)
            if plan is None:return raw(span)
            items=[block(s,False) if s.kind==0xa1 else raw(s) for s in children if s.kind not in (0x9b,0xbf)]
            value=plan['duration'];encoded=value.to_bytes(max(1,(value.bit_length()+7)//8),'big')
            items.append(header(0x9b,len(encoded))+encoded)
            return container(span,items)
        def cluster(span):
            pieces=[]
            for child in spans(incoming,span.body,span.end):
                if child.kind in (0xbf,0xa7,0xab):continue
                if child.kind==0xa3 and child.body in plans:
                    plan=plans[child.body];value=plan['duration'];encoded=value.to_bytes(max(1,(value.bit_length()+7)//8),'big')
                    pieces.append(node(0xa0,[block(child,True),header(0x9b,len(encoded))+encoded]))
                elif child.kind==0xa0:pieces.append(group(child))
                else:pieces.append(raw(child))
            return container(span,pieces)
        children=[]
        for span in spans(incoming,top[1].body,top[1].end):
            if span.kind in (0xbf,0x114d9b74,0x1c53bb6b):continue
            children.append(cluster(span) if span.kind==0x1f43b675 else raw(span))
        tree=container(top[1],children)
        if matched!=set(plans):raise ValueError('Not every planned audio duration has one working block')
        def write(piece):
            guard()
            if isinstance(piece,bytes):outgoing.write(piece);return
            if piece[0]=='raw':
                incoming.seek(piece[1]);left=piece[2]-piece[1]
                while left:
                    guard();chunk=incoming.read(min(1024*1024,left))
                    if not chunk:raise ValueError('Working container changed while copying')
                    outgoing.write(chunk);left-=len(chunk)
                return
            outgoing.write(header(piece[1],piece[3]));checksum=None;body=outgoing.tell()
            for child in piece[2]:
                if not isinstance(child,bytes) and child[0]=='crc':
                    outgoing.write(b'\xbf\x84\0\0\0\0');checksum=(outgoing.tell()-4,child[1]);continue
                write(child)
            if checksum:
                end=outgoing.tell();outgoing.flush();value=crc(outgoing,body+6,end)
                outgoing.seek(checksum[0]);outgoing.write(value.to_bytes(4,checksum[1]));outgoing.seek(end)
        write(raw(top[0]));write(tree)
    return len(matched)


def restore(work,source_metadata,sample,sample_metadata,original,copied,shift,label,tolerance):
    from auto_optimize import paired_streams,metadata_check,main_video,reference_metadata_from_frames,compact_rows
    from reference_sampling import verify_source_slice,ReferencePacketDurationError
    from artifact_manifest import command_outputs
    from job_tracking import progress
    from dvd_av1_batch import save
    from source_format import valid_pixel_format
    sample=Path(sample)
    if sample.parent.resolve()!=work.directory.resolve() or sample.resolve()==Path(work.args.source).resolve():
        raise ValueError('Duration restoration is limited to generated samples')
    plans={};tracks=[]
    for before,after in paired_streams(source_metadata,sample_metadata):
        if before['codec_type']!='audio':continue
        a=[p for p in original if p['stream_index']==before['index']]
        b=[p for p in copied if p['stream_index']==after['index']]
        try:verify_source_slice(a,b,shift,tolerance=tolerance)
        except ReferencePacketDurationError:
            matches=[i for i in range(len(a)-len(b)+1) if b and
                a[i].get('pts_time') not in (None,'N/A') and b[0].get('pts_time') not in (None,'N/A') and
                abs(Fraction(b[0]['pts_time'])-Fraction(a[i]['pts_time'])-shift)<=tolerance and
                all(x['data_hash']==y['data_hash'] for x,y in zip(a[i:],b))]
            if len(matches)!=1:raise ValueError('Duration restoration needs unique unchanged original packets')
            rows=a[matches[0]:matches[0]+len(b)]
            verify_source_slice(a,[dict(p,duration_time=r['duration_time']) for p,r in zip(b,rows)],shift,tolerance=tolerance)
            for row,reference in zip(b,rows):
                position=int(row['pos'])
                if position in plans:raise ValueError('Laced packets require a separate duration representation')
                plans[position]=dict(duration_seconds=reference['duration_time'],size=int(row['size']),data_hash=row['data_hash'])
            tracks.append(dict(source_index=before['index'],sample_index=after['index'],packets=len(b)))
    if not plans:return sample
    target=work.directory/(label+'-original-packet-durations.mkv')
    identity=work.audit_identity(sample)
    progress('Restoring original durations in the working sample',
        detail='Copied packet bytes and PTS/DTS stay unchanged; exact source duration fields are written explicitly')
    with command_outputs(work.directory,[str(target)]):restore_file(sample,target,plans,work.guard)
    if work.audit_identity(sample)!=identity:raise ValueError('Working sample changed during duration restoration')
    after=work.probe(target)
    def described(data,path,part):
        if valid_pixel_format(main_video(data).get('pix_fmt')):return data
        evidence=work.frame_file(path,label+'-'+part+'-format',data['format'])
        from hdr10plus_preserve import frame_records
        return reference_metadata_from_frames(data,source_metadata,
            frame_records(evidence) if work.hdr_mode else compact_rows(evidence,'width'))
    metadata_check(described(sample_metadata,sample,'before'),described(after,target,'after'),main_video(sample_metadata)['codec_name'])
    save(work.directory/(label+'-packet-duration-restoration.json'),dict(
        method='explicit-original-audio-block-durations',tracks=tracks,
        original_media_unchanged=True,packet_payload_hashes_verified=True,
        source_packet_pts_dts_verified=True,full_sample_validation_required=True))
    return target
