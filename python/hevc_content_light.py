"""Restore source content-light SEI by decoded presentation-frame identity.

Only a new Annex-B HEVC copy is written. Decoded packet positions map display
order back to coded order (including B frames). Full downstream frame/quality
validation is mandatory; this helper does not authorize publication.
"""
import hashlib
import re
import struct
from itertools import zip_longest
from pathlib import Path

START = re.compile(b'\x00\x00\x00?\x01')


def unescape(data):
    out=bytearray();zeros=0
    for i,value in enumerate(data):
        if zeros==2 and value==3:
            if i+1==len(data) or data[i+1]>3:raise ValueError('Invalid SEI escape')
            zeros=0;continue
        out.append(value);zeros=zeros+1 if value==0 else 0
    return bytes(out)


def escape(data):
    out=bytearray();zeros=0
    for value in data:
        if zeros==2 and value<=3:out.append(3);zeros=0
        out.append(value);zeros=zeros+1 if value==0 else 0
    return bytes(out)


def integer(value):
    return b'\xff'*(value//255)+bytes([value%255])


def messages(nal):
    data=unescape(nal[2:]).rstrip(b'\x00');offset=0;result=[]
    while data[offset:]!=b'\x80':
        values=[]
        for _ in range(2):
            value=0
            while True:
                if offset>=len(data):raise ValueError('Truncated SEI')
                part=data[offset];offset+=1;value+=part
                if part!=255:break
            values.append(value)
        kind,length=values
        if offset+length>=len(data):raise ValueError('Truncated SEI payload')
        result.append((kind,data[offset:offset+length]));offset+=length
    return result


def sei(header,items):
    return header+escape(b''.join(integer(k)+integer(len(p))+p for k,p in items)+b'\x80')


def patch_packet(packet,payload):
    starts=list(START.finditer(packet));out=bytearray();pictures=0;vcl=hashlib.sha256()
    if not starts or starts[0].start()!=0:raise ValueError('Invalid Annex-B packet')
    for i,match in enumerate(starts):
        end=starts[i+1].start() if i+1<len(starts) else len(packet)
        prefix=packet[match.start():match.end()];nal=packet[match.end():end]
        if len(nal)<2 or nal[0]&128 or not nal[1]&7:raise ValueError('Invalid HEVC header')
        kind=(nal[0]>>1)&63;layer=((nal[0]&1)<<5)|(nal[1]>>3)
        if layer:raise ValueError('Layered HEVC requires its separate finalizer')
        if kind<32:
            if len(nal)<3:raise ValueError('Missing slice header')
            if nal[2]&128:
                pictures+=1
                # Prefix SEI inherits temporal_id_plus1 from its associated picture.
                out+=b'\x00\x00\x00\x01'+sei(bytes([39<<1,nal[1]&7]),[(144,payload)])
            vcl.update(prefix+nal)
        if kind in (39,40):
            items=messages(nal);kept=[item for item in items if item[0]!=144]
            if kept==items:out+=prefix+nal
            elif kept:out+=prefix+sei(nal[:2],kept)
        else:out+=prefix+nal
    if pictures!=1:raise ValueError('Expected one decoded picture per packet')
    return bytes(out),vcl.digest()


def content_light(frame):
    items=[s for s in frame.get('side_data_list',[]) if s.get('side_data_type')=='Content light level metadata']
    if len(items)!=1:raise ValueError('One source content-light record required per frame')
    values=[items[0].get(k) for k in ('max_content','max_average')]
    if any(type(v) is not int or not 0<=v<=65535 for v in values):raise ValueError('Invalid content-light value')
    return struct.pack('>HH',*values)


def restore(source,destination,source_frames,encoded_frames,guard=lambda:None):
    source=Path(source);destination=Path(destination)
    if source.resolve()==destination.resolve() or destination.exists() or destination.is_symlink():
        raise ValueError('Content-light restoration requires a new output')
    mapping={}
    for i,(reference,encoded) in enumerate(zip_longest(source_frames,encoded_frames)):
        if i%4096==0:guard()
        if reference is None or encoded is None:raise ValueError('Decoded frame count changed')
        try:position=int(encoded['pkt_pos'])
        except (KeyError,ValueError,TypeError):raise ValueError('Missing decoded packet position') from None
        if position<0 or position in mapping:raise ValueError('Ambiguous decoded packet position')
        mapping[position]=content_light(reference)
    offsets=sorted(mapping);size=source.stat().st_size
    if not offsets or offsets[0]!=0 or offsets[-1]>=size:raise ValueError('Incomplete encoded packet coverage')
    before=hashlib.sha256();after=hashlib.sha256()
    with source.open('rb') as reader,destination.open('xb') as writer:
        for i,position in enumerate(offsets):
            guard();length=(offsets[i+1] if i+1<len(offsets) else size)-position
            if not 0<length<=64*1024*1024:raise ValueError('Invalid encoded packet length')
            packet=reader.read(length)
            if len(packet)!=length:raise ValueError('Encoded input truncated')
            patched,digest=patch_packet(packet,mapping[position])
            # Reparse to independently check that all coded slices remain identical.
            _,checked=patch_packet(patched,mapping[position])
            before.update(digest);after.update(checked);writer.write(patched)
    if before.digest()!=after.digest():raise ValueError('Coded picture payload changed')
    return dict(frames=len(offsets),coded_picture_sha256=before.hexdigest(),picture_payload_unchanged=True,
                method='decoded-packet-position-content-light-v1',full_validation_required=True)
