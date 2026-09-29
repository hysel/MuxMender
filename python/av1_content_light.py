"""Restore constant source HDR content-light values without re-encoding AV1.

Metadata OBU syntax: https://aomediacodec.github.io/av1-spec/av1-spec.pdf
Preserves every other OBU byte and every IVF timestamp. Full downstream decoded
frame, track, metadata and quality checks remain mandatory.
"""
import hashlib
from fractions import Fraction
from pathlib import Path
import struct


def leb(data, offset):
    value=0
    for index in range(8):
        if offset+index>=len(data):raise ValueError('Truncated AV1 LEB128')
        byte=data[offset+index];value|=(byte&127)<<(7*index)
        if not byte&128:return value,offset+index+1
    raise ValueError('Unterminated AV1 LEB128')


def obus(packet):
    offset=0
    while offset<len(packet):
        start=offset;header=packet[offset];offset+=1
        if header&129 or not header&2:raise ValueError('Invalid or unsized AV1 OBU')
        kind=(header>>3)&15
        if header&4:
            if offset>=len(packet) or packet[offset]&7:raise ValueError('Invalid AV1 extension header')
            offset+=1
        size,payload=leb(packet,offset);offset=payload+size
        if offset>len(packet):raise ValueError('Truncated AV1 OBU')
        yield kind,packet[start:offset],packet[payload:offset]


def is_cll(kind,payload):
    return kind==5 and leb(payload,0)[0]==1


def patch_packet(packet, light):
    if len(light)!=4:raise ValueError('Content-light values require four bytes')
    metadata=b'\x2a\x06\x01'+light+b'\x80'
    output=bytearray();inserted=False;original=bytearray()
    for kind,raw,payload in obus(packet):
        if is_cll(kind,payload):continue
        original.extend(raw)
        if kind in (3,6) and not inserted:
            output.extend(metadata);inserted=True
        output.extend(raw)
    if not inserted:raise ValueError('No AV1 frame header in encoded packet')
    verified=b''.join(raw for kind,raw,payload in obus(output) if not is_cll(kind,payload))
    if bytes(original)!=verified:raise ValueError('AV1 picture or other metadata changed')
    return bytes(output),hashlib.sha256(original).digest()


def restore_ivf(source, destination, light, guard=lambda:None):
    source=Path(source);destination=Path(destination)
    if source.resolve()==destination.resolve() or destination.exists() or destination.is_symlink():
        raise ValueError('AV1 restoration requires a new output')
    count=0;digest=hashlib.sha256()
    with source.open('rb') as reader,destination.open('xb') as writer:
        header=reader.read(32)
        if len(header)!=32 or header[:4]!=b'DKIF' or header[4:8]!=b'\x00\x00\x20\x00' or header[8:12]!=b'AV01':
            raise ValueError('Expected FFmpeg AV1 IVF stream')
        writer.write(header)
        while True:
            guard();record=reader.read(12)
            if not record:break
            if len(record)!=12:raise ValueError('Truncated IVF frame header')
            size=struct.unpack('<I',record[:4])[0]
            if not 0<size<=64*1024*1024:raise ValueError('Invalid IVF packet size')
            packet=reader.read(size)
            if len(packet)!=size:raise ValueError('Truncated IVF packet')
            patched,proof=patch_packet(packet,light);digest.update(proof)
            writer.write(struct.pack('<I',len(patched))+record[4:]+patched);count+=1
    if not count:raise ValueError('Empty AV1 stream')
    return dict(packets=count,non_cll_obus_sha256=digest.hexdigest(),
                picture_payload_unchanged=True,ivf_timestamps_unchanged=True,full_validation_required=True)


def constant_light(frames, guard=lambda:None):
    from hevc_content_light import content_light
    value=None;count=0
    for count,frame in enumerate(frames,1):
        if count%4096==0:guard()
        try:current=content_light(frame)
        except ValueError:return None
        if value is None:value=current
        elif current!=value:return None
    return value if count else None


def source_light(workflow, source, before, label):
    from hdr10plus_preserve import frame_records
    frames=workflow.frame_cache.get(str(source.resolve()))
    if frames is None:frames=workflow.frame_file(source,label+'-cll-source',before['format'])
    return constant_light(frame_records(frames),workflow.guard)


def available():
    """Optional packet-copy dependency; ordinary AV1 validation remains usable."""
    try:
        import av
        return av.__version__=='18.1.0'
    except ImportError:
        return False


def restore_container(source,destination,light,guard=lambda:None):
    """Copy AV1 packets with the original codec parameters, not an IVF detour.

    The original mastering metadata must survive without float32 rounding.
    This writes a new video-only intermediate; the shared remuxer restores all
    other tracks and the full validator independently checks the final output.
    """
    import av
    source=Path(source);destination=Path(destination)
    if source.resolve()==destination.resolve():raise ValueError('Distinct output required')
    digest=hashlib.sha256();count=0
    # Exclusive creation also rejects dangling symlinks and existing outputs.
    with destination.open('xb') as target,av.open(str(source)) as reader,av.open(target,'w',format='matroska',options={'avoid_negative_ts':'disabled'}) as writer:
        streams=[s for s in reader.streams.video if s.codec_context.name in ('av1','libdav1d') and not (s.disposition & s.disposition.attached_pic)]
        if len(streams)!=1:raise ValueError('Expected one primary AV1 stream')
        stream=streams[0];output=writer.add_stream_from_template(stream,opaque=True)
        output.time_base=stream.time_base
        for packet in reader.demux(stream):
            guard()
            if not packet.size:continue
            data,proof=patch_packet(bytes(packet),light);digest.update(proof)
            copied=av.Packet(data)
            copied.pts=packet.pts;copied.dts=packet.dts;copied.duration=packet.duration
            copied.time_base=packet.time_base;copied.is_keyframe=packet.is_keyframe;copied.stream=output
            writer.mux(copied);count+=1
            if count%120==0:
                print('frame='+str(count),flush=True)
                if packet.pts is not None:print('out_time_us='+str(int(packet.pts*packet.time_base*1000000)),flush=True)
    if not count:raise ValueError('Empty AV1 stream')
    return dict(packets=count,non_cll_obus_sha256=digest.hexdigest(),picture_payload_unchanged=True,
                packet_timestamps_copied=True,codec_parameters_copied=True,full_validation_required=True)


def finalize(workflow, encoded, output, light, label, duration):
    from auto_optimize import main_video
    from hdr10plus_preserve import preserved_tracks_command
    from job_tracking import progress
    import sys
    restored=output.with_name(output.stem+'-restored-cll-video.mkv')
    ffmpeg=workflow.args.ffmpeg
    progress('Restoring original AV1 content-light metadata',detail='Constant source values; no picture re-encoding')
    proof=workflow.directory/(label+'-cll-preservation.json')
    workflow.execute([sys.executable,'-B',str(Path(__file__).resolve()),str(encoded),str(restored),light.hex(),str(proof)],label+'-restore-av1-cll',duration)
    info=workflow.probe(encoded);video=main_video(info)
    command=preserved_tracks_command(ffmpeg,restored,encoded,output,info['streams'])
    sar=video.get('sample_aspect_ratio')
    if sar not in (None,'N/A','0:1'):
        aspect=Fraction(sar.replace(':','/'))*Fraction(video['width'],video['height'])
        command[-1:-1]=['-aspect:v:0',str(aspect.numerator)+':'+str(aspect.denominator)]
    workflow.execute(workflow.preserve_covers(command,encoded,info,label+'-cll',input_index=1),label+'-mux-cll',duration)
    for path in [encoded,restored]:
        stat=path.stat()
        workflow.hdr_intermediates.setdefault(output.resolve(),[]).append(
            (path,(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)))


if __name__=='__main__':
    import sys,json
    source,destination,light,proof=sys.argv[1:]
    result=restore_container(source,destination,bytes.fromhex(light))
    with Path(proof).open('x') as file:json.dump(result,file,indent=2)
