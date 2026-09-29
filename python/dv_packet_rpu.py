"""Select sample RPUs by decoded packet identity, not inferred HEVC POC order.

Only unchanged source payloads are selected. Full decoded metadata, timing and
quality validation must still pass after injection. Not a full-file extractor.
"""
from fractions import Fraction
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def hex_payload(text):
    # XML normalizes ffprobe's newlines to spaces. Fixed-width hex columns keep
    # ASCII text (including colons and hex-looking text) out of the payload.
    result=bytearray()
    for match in re.finditer(r'(?<!\S)([0-9a-fA-F]{8}): ([0-9a-fA-F ]{39})  ',text):
        if int(match[1],16)!=len(result):raise ValueError('Invalid packet hex offset')
        result.extend(bytes.fromhex(match[2]))
    if not result:raise ValueError('Missing packet bytes')
    return bytes(result)


def packet_rpu(data, length_size):
    if length_size not in (1,2,3,4):raise ValueError('Invalid HEVC NAL length size')
    offset=0;records=[];pictures=0
    while offset<len(data):
        if offset+length_size>len(data):raise ValueError('Truncated HEVC NAL length')
        size=int.from_bytes(data[offset:offset+length_size],'big');offset+=length_size
        nal=data[offset:offset+size];offset+=size
        if size<2 or len(nal)!=size or nal[0]&128 or not nal[1]&7:
            raise ValueError('Invalid HEVC packet NAL')
        kind=(nal[0]>>1)&63;layer=((nal[0]&1)<<5)|(nal[1]>>3)
        if layer:raise ValueError('Layered HEVC requires its layer-aware workflow')
        if kind<32:
            if len(nal)<3:raise ValueError('Missing slice header')
            pictures+=bool(nal[2]&128)
        if kind==62:
            if len(nal)<3 or nal[2]!=0x19:raise ValueError('Invalid Dolby Vision RPU prefix')
            records.append(nal[2:])
    if pictures!=1 or len(records)!=1:raise ValueError('Expected one picture and RPU per selected packet')
    return records[0]


def write_selected(xml_path, frames, destination, length_size, guard=lambda:None):
    wanted={}
    for frame in frames:
        position=str(int(frame['pkt_pos']));pts=Fraction(frame['best_effort_timestamp_time'])
        if position in wanted:raise ValueError('Duplicate decoded packet identity')
        wanted[position]=pts
    if not wanted:raise ValueError('No decoded sample frames')
    records={}
    for _,element in ET.iterparse(xml_path,events=['end']):
        if element.tag!='packet':continue
        guard();position=element.attrib.get('pos')
        if position in wanted:
            if position in records or Fraction(element.attrib['pts_time'])!=wanted[position]:
                raise ValueError('Packet identity or presentation timestamp mismatch')
            data=hex_payload(element.attrib['data'])
            if len(data)!=int(element.attrib['size']):raise ValueError('Packet byte count mismatch')
            records[position]=packet_rpu(data,length_size)
        element.clear()
    if records.keys()!=wanted.keys():raise ValueError('Missing decoded-frame RPU packet')
    with Path(destination).open('xb') as output:
        for position in wanted:
            guard();output.write(b'\x00\x00\x00\x01'+records[position])
    return len(records)


def extract(ffprobe, source, frames, directory, guard=lambda:None):
    from native_pipeline import checked_json
    from task_progress import run_probe
    data=checked_json([ffprobe,'-v','error','-select_streams','V:0','-show_streams',
                       '-show_data','-of','json',str(source)])
    streams=data['streams']
    if len(streams)!=1 or streams[0]['codec_name']!='hevc':raise ValueError('One primary HEVC stream required')
    extra=hex_payload(streams[0]['extradata'])
    if len(extra)<23 or extra[0]!=1:raise ValueError('Invalid HEVC configuration record')
    directory=Path(directory);xml=directory/'source-rpu-packets.xml';output=directory/'picture-ordered-rpu.bin'
    run_probe([ffprobe,'-v','error','-select_streams','V:0','-show_packets','-show_data',
               '-show_entries','packet=pos,pts_time,size,data','-of','xml',str(source)],
              xml,'Matching Dolby Vision metadata to decoded pictures',120,guard)
    if xml.with_suffix(xml.suffix+'.stderr').read_text().strip():raise ValueError('Packet reader reported errors')
    count=write_selected(xml,frames,output,(extra[21]&3)+1,guard)
    return output,dict(method='decoded-packet-position-and-pts',frames=count,payloads_unchanged=True)
