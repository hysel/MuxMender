"""Lossless semantic translation of verified QuickTime chapter-text tracks."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from media_metadata import canonical_chapters
from task_progress import run_probe


def packet_payload(text):
    chunks=[]
    for line in str(text).splitlines():
        if not line.strip():continue
        match=re.fullmatch(r'[0-9a-fA-F]{8}: ([0-9a-fA-F ]+?)  .*',line)
        if not match:raise ValueError('Invalid chapter packet dump')
        chunks.append(bytes.fromhex(match[1]))
    return b''.join(chunks)


def verify_track(data, stream, packets, descriptor=None):
    chapters=canonical_chapters(data.get('chapters',[]))
    if not chapters or len(packets)!=len(chapters):raise ValueError('Chapter packet inventory differs')
    base=Fraction(stream['time_base'])
    if base<=0:raise ValueError('Invalid chapter packet clock')
    for packet,chapter in zip(packets,chapters):
        if packet.get('stream_index')!=stream['index']:raise ValueError('Wrong chapter packet stream')
        if type(packet.get('pts')) is not int or type(packet.get('duration')) is not int:
            raise ValueError('Incomplete chapter packet timing')
        start=packet['pts']*base;end=start+packet['duration']*base
        if start!=chapter['start'] or end!=chapter['end']:raise ValueError('Native chapter timing differs')
        payload=packet_payload(packet.get('data',''))
        if len(payload)<2:raise ValueError('Incomplete native chapter text')
        length=int.from_bytes(payload[:2],'big');tail=payload[2+length:]
        # The optional standard encoding atom declares UTF-8 text. No unknown
        # payload is treated as a disposable chapter or silently omitted.
        if len(payload)<2+length or tail not in (b'',bytes.fromhex('0000000c656e636400000100')):
            raise ValueError('Unrecognized extra chapter packet data')
        title=payload[2:2+length].decode('utf-8',errors='strict')
        if title!=chapter['tags'].get('title',''):raise ValueError('Native chapter title differs')
    tags=stream.get('tags',{})
    if stream.get('extradata_size',0) and not re.fullmatch(r'SHA256:[0-9a-fA-F]{64}',stream.get('extradata_hash','')):
        raise ValueError('Missing native chapter extradata identity')
    descriptor_kind=None
    if stream.get('extradata_size',0):
        # These are the two default chapter-text sample descriptions observed
        # before/after FFmpeg chapter regeneration. Custom fonts, styling or
        # additional atoms are NOT discarded. Chapter payloads/timing are
        # independently checked in full above.
        known=(bytes.fromhex('00000000000000010000000000000000'+'00'*27),
               bytes.fromhex('00000001000000000000000000000000'
                             '00000000000000010000000000000000'
                             '000d667461620001000100'))
        if descriptor is None or len(descriptor)!=stream['extradata_size'] or (
                'SHA256:'+hashlib.sha256(descriptor).hexdigest()).lower()!=stream['extradata_hash'].lower():
            raise ValueError('Native chapter descriptor identity differs')
        if descriptor not in known:raise ValueError('Custom native chapter descriptor requires preservation')
        descriptor_kind='default-chapter-text'
    if set(tags)-{'creation_time','language','handler_name','vendor_id'}:
        raise ValueError('Chapter data has additional stream metadata')
    return dict(language=tags.get('language','und'),handler_name=tags.get('handler_name'),disposition=stream.get('disposition',{}),
                descriptor=descriptor_kind,side_data=stream.get('side_data_list',[]),
                chapters=len(chapters),method='complete-native-chapter-text-equivalence')


def inspect(workflow, source, data):
    if 'mov' not in data.get('format',{}).get('format_name','').split(','):return []
    tracks=[s for s in data.get('streams',[]) if s.get('codec_type')=='data' and
            s.get('codec_name')=='bin_data' and s.get('codec_tag_string')=='text']
    if not tracks or not data.get('chapters'):return []
    if len(tracks)!=1:raise ValueError('Ambiguous native chapter data tracks')
    stream=tracks[0]
    label=hashlib.sha256(str(Path(source).resolve()).encode()).hexdigest()[:16]
    path=workflow.directory/('chapter-track-'+label+'.json')
    run_probe([workflow.args.ffprobe,'-v','error','-ignore_chapters','1','-select_streams',str(stream['index']),
               '-show_packets','-show_streams','-show_data','-of','json',str(source)],path,'Checking native chapter text',
              workflow.args.timeout,workflow.guard)
    errors=path.with_suffix(path.suffix+'.stderr')
    if not errors.is_file() or errors.stat().st_size:raise ValueError('Native chapter reader reported errors')
    if path.stat().st_size>4*1024*1024:raise ValueError('Oversized native chapter evidence')
    evidence=json.loads(path.read_text())
    native=next((s for s in evidence.get('streams',[]) if s.get('index')==stream['index']),{})
    descriptor=packet_payload(native['extradata']) if native.get('extradata') else None
    proof=verify_track(data,stream,evidence['packets'],descriptor)
    data['chapter_track_semantics']=proof
    data['streams']=[s for s in data['streams'] if s['index']!=stream['index']]
    return [stream['index']]


def mapping_options(command, tracks):
    """Omit only the verified redundant chapter representation from all maps."""
    result=list(command);inputs=[result[i+1] for i,v in enumerate(result[:-1]) if v=='-i']
    for number,source in enumerate(inputs):
        indices=tracks.get(str(Path(source).resolve()),())
        if not indices:continue
        for i in reversed(range(len(result)-1)):
            if result[i]=='-map' and result[i+1]==str(number):
                result[i+2:i+2]=[item for index in indices for item in ('-map',f'-{number}:{index}')]
    return result
