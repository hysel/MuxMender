"""Copy source HEVC HDR10+/CLL metadata into separately encoded AV1 packets.

Metadata is associated by presentation time, with one use per decoded source
picture. Picture OBUs, packet timing and codec parameters remain unchanged.
Independent full-frame metadata, geometry, track and quality checks still apply.
"""
import hashlib
from fractions import Fraction
from pathlib import Path
import sqlite3

from av1_content_light import obus, leb
from hevc_content_light import messages, content_light, START

HDR10PLUS = bytes.fromhex('b5003c000104')


def unsigned_leb(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result) + bytes([value])


def source_payload(packet, length_size):
    if length_size not in (0, 1, 2, 3, 4):
        raise ValueError('Invalid HEVC NAL length size')
    if length_size == 0:
        starts=list(START.finditer(packet))
        if not starts or packet[:starts[0].start()].strip(b'\x00'):
            raise ValueError('Invalid Annex-B HEVC packet')
        nals=[packet[match.end():(starts[i+1].start() if i+1<len(starts) else len(packet))]
              for i,match in enumerate(starts)]
        # Parse the same NAL payloads through one length-delimited implementation.
        packet=b''.join(len(nal).to_bytes(4,'big')+nal for nal in nals)
        length_size=4
    offset = 0; payloads = []; pictures = 0
    while offset < len(packet):
        if offset + length_size > len(packet):raise ValueError('Truncated HEVC length')
        size = int.from_bytes(packet[offset:offset + length_size], 'big'); offset += length_size
        nal = packet[offset:offset + size]; offset += size
        if size < 2 or len(nal) != size or nal[0] & 128 or not nal[1] & 7:
            raise ValueError('Invalid HEVC NAL')
        if ((nal[0] & 1) << 5) | (nal[1] >> 3):
            raise ValueError('Layered HEVC requires its own metadata route')
        kind = (nal[0] >> 1) & 63
        if kind < 32:
            if len(nal) < 3:raise ValueError('Missing HEVC slice header')
            pictures += bool(nal[2] & 128)
        if kind in (39, 40):
            payloads.extend(data for number, data in messages(nal)
                            if number == 4 and data.startswith(HDR10PLUS))
    if pictures != 1 or len(payloads) > 1:
        raise ValueError('Ambiguous HEVC picture or HDR10+ association')
    return payloads[0] if payloads else None


def is_hdr10plus(kind, payload):
    if kind != 5:return False
    metadata_type, offset = leb(payload, 0)
    return metadata_type == 4 and payload[offset:].startswith(HDR10PLUS)


def patch_packet(packet, t35, *, light='unchanged'):
    if t35 is not None and (not t35.startswith(HDR10PLUS) or len(t35) <= len(HDR10PLUS)):
        raise ValueError('Invalid HDR10+ registered payload')
    change_light = light != 'unchanged'
    if change_light and light is not None and (not isinstance(light, bytes) or len(light) != 4):
        raise ValueError('CLL metadata requires four bytes or an absent source record')
    source = list(obus(packet))
    if not any(kind in (3, 6) for kind, _, _ in source):raise ValueError('Missing AV1 picture header')
    def replaced(kind, payload):
        return is_hdr10plus(kind, payload) or (change_light and kind == 5 and leb(payload, 0)[0] == 1)
    retained = b''.join(raw for kind, raw, payload in source if not replaced(kind, payload))
    output = bytearray()
    for kind, raw, payload in source:
        if replaced(kind, payload):continue
        if kind in (3, 6):
            # A temporal unit may contain hidden reference pictures. Metadata is
            # set at each header; the decoded-frame validator independently
            # verifies the actual displayed frame, including show-existing.
            items = ([] if t35 is None else [b'\x04' + t35 + b'\x80'])
            if change_light and light is not None:items.insert(0, b'\x01' + light + b'\x80')
            extension = raw[1:2] if raw[0] & 4 else b''
            for item in items:
                output.extend(bytes([0x2a | (raw[0] & 4)]) + extension + unsigned_leb(len(item)) + item)
        output.extend(raw)
    checked = b''.join(raw for kind, raw, payload in obus(output) if not replaced(kind, payload))
    if checked != retained:raise ValueError('AV1 picture or unrelated metadata changed')
    return bytes(output), hashlib.sha256(retained).hexdigest()


def timestamp_us(value):
    return round(Fraction(value) * 1000000)


def one_record(database, value, tolerance):
    matches = database.execute('SELECT time, light, payload, loaded, used FROM frames WHERE time BETWEEN ? AND ?',
                               (value - tolerance, value + tolerance)).fetchall()
    if len(matches) != 1:raise ValueError('HDR metadata timestamp has no unique source picture')
    return matches[0]


def restore_container(source, encoded, frames, destination, guard=lambda: None):
    """Use a disk index so full-length frame metadata does not accumulate in RAM."""
    import av
    from hdr10plus_preserve import frame_records
    source, encoded, frames, destination = map(Path, (source, encoded, frames, destination))
    if destination.resolve() in (source.resolve(), encoded.resolve(), frames.resolve()):
        raise ValueError('HDR restoration requires a distinct output')
    database_path = destination.with_suffix('.hdr-index.sqlite')
    fingerprints = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in (source, encoded, frames)}
    # Exclusive creation rejects an existing or symlinked scratch index.
    with database_path.open('xb'):pass
    def check():
        guard()
        if any((path.stat().st_size, path.stat().st_mtime_ns) != identity for path, identity in fingerprints.items()):
            raise ValueError('HDR restoration input changed')
    database = None
    try:
        database = sqlite3.connect(database_path)
        database.execute('PRAGMA journal_mode=OFF')
        database.execute('PRAGMA cache_size=-4096')
        database.execute('CREATE TABLE frames (time INTEGER PRIMARY KEY, light BLOB, payload BLOB, loaded INTEGER DEFAULT 0, used INTEGER DEFAULT 0)')
        count = 0
        for frame in frame_records(frames):
            if count % 4096 == 0:check()
            try:time = timestamp_us(frame['pts_time'])
            except (KeyError, ValueError, ZeroDivisionError) as error:raise ValueError('Missing source HDR presentation time') from error
            records = [s for s in frame.get('side_data_list', []) if s.get('side_data_type') == 'Content light level metadata']
            light = content_light(frame) if records else None
            database.execute('INSERT INTO frames (time, light) VALUES (?, ?)', (time, light));count += 1
            if count % 4096 == 0:print('Indexed HDR pictures='+str(count), flush=True)
        if not count:raise ValueError('No source HDR frame evidence')
        with av.open(str(source)) as reader:
            streams = [s for s in reader.streams.video if s.codec_context.name == 'hevc' and not (s.disposition & s.disposition.attached_pic)]
            if len(streams) != 1:raise ValueError('Expected one primary HEVC source stream')
            stream = streams[0];extra = stream.codec_context.extradata
            if extra and len(extra)>=23 and extra[0]==1:
                length = (extra[21] & 3) + 1
            else:
                length = 0  # Annex-B demuxers, including transport streams.
            for packet_number, packet in enumerate(reader.demux(stream), 1):
                check()
                if not packet.size:continue
                if packet.pts is None:raise ValueError('Missing HEVC packet PTS')
                value = timestamp_us(packet.pts * packet.time_base)
                # ffprobe prints presentation times with microsecond precision.
                matches = database.execute('SELECT time, loaded FROM frames WHERE time BETWEEN ? AND ?', (value-1, value+1)).fetchall()
                if not matches:continue  # Non-output/preroll packets are not displayed pictures.
                if len(matches) != 1 or matches[0][1]:raise ValueError('Ambiguous HEVC frame metadata mapping')
                database.execute('UPDATE frames SET payload=?, loaded=1 WHERE time=?',
                                 (source_payload(bytes(packet), length), matches[0][0]))
                if packet_number % 4096 == 0:
                    print('Reading original HDR packets='+str(packet_number), flush=True)
        if database.execute('SELECT count(*) FROM frames WHERE loaded=0').fetchone()[0]:
            raise ValueError('Incomplete source HDR picture association')
        digest = hashlib.sha256();packets = 0;dynamic = 0
        with destination.open('xb') as target, av.open(str(encoded)) as reader, av.open(target, 'w', format='matroska', options={'avoid_negative_ts':'disabled'}) as writer:
            streams = [s for s in reader.streams.video if s.codec_context.name in ('av1', 'libdav1d') and not (s.disposition & s.disposition.attached_pic)]
            if len(streams) != 1:raise ValueError('Expected one primary AV1 stream')
            stream = streams[0];output = writer.add_stream_from_template(stream, opaque=True);output.time_base = stream.time_base
            for packet in reader.demux(stream):
                check()
                if not packet.size:continue
                if packet.pts is None:raise ValueError('Missing AV1 packet PTS')
                value = timestamp_us(packet.pts * packet.time_base)
                # Bound only association to the container's timestamp precision.
                # Full independent timing validation retains its own threshold.
                tolerance = min(2000, max(1, timestamp_us(packet.time_base / 2) + 1))
                time, light, payload, loaded, used = one_record(database, value, tolerance)
                if not loaded or used:raise ValueError('Source HDR picture was absent or already used')
                data, preserved = patch_packet(bytes(packet), payload, light=light)
                digest.update(bytes.fromhex(preserved));dynamic += payload is not None
                copied = av.Packet(data);copied.pts = packet.pts;copied.dts = packet.dts;copied.duration = packet.duration
                copied.time_base = packet.time_base;copied.is_keyframe = packet.is_keyframe;copied.stream = output
                writer.mux(copied);packets += 1
                database.execute('UPDATE frames SET used=1 WHERE time=?', (time,))
                if packets % 120 == 0:
                    print('frame='+str(packets), flush=True)
                    print('out_time_us='+str(value), flush=True)
        if database.execute('SELECT count(*) FROM frames WHERE used=0').fetchone()[0]:
            raise ValueError('Encoded AV1 omitted source HDR pictures')
        check()
        return dict(frames=count, packets=packets, hdr10plus_packets=dynamic,
                    non_restored_obus_sha256=digest.hexdigest(), picture_payload_unchanged=True,
                    packet_timestamps_copied=True, codec_parameters_copied=True,
                    method='source-presentation-time-hdr-copy-v1', full_validation_required=True)
    finally:
        if database is not None:database.close()
        database_path.unlink()


def finalize(workflow, source, encoded, output, frames, label, duration):
    import sys
    from hdr10plus_preserve import preserved_tracks_command
    from auto_optimize import main_video
    restored = output.with_name(output.stem+'-restored-hdr-video.mkv')
    proof = workflow.directory/(label+'-av1-hdr-preservation.json')
    workflow.execute([sys.executable, '-B', str(Path(__file__).resolve()), str(source), str(encoded),
                      str(frames), str(restored), str(proof), str(restored.with_suffix('.hdr-index.sqlite'))],
                     label+'-restore-av1-hdr', duration)
    info = workflow.probe(encoded);video = main_video(info)
    command = preserved_tracks_command(workflow.args.ffmpeg, restored, encoded, output, info['streams'])
    sar = video.get('sample_aspect_ratio')
    if sar not in (None, 'N/A', '0:1'):
        aspect = Fraction(sar.replace(':','/')) * Fraction(video['width'],video['height'])
        command[-1:-1] = ['-aspect:v:0', str(aspect.numerator)+':'+str(aspect.denominator)]
    workflow.execute(workflow.preserve_covers(command, encoded, info, label+'-hdr', input_index=1), label+'-mux-hdr', duration)
    for path in (encoded, restored):
        stat = path.stat()
        workflow.hdr_intermediates.setdefault(output.resolve(), []).append(
            (path, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)))


if __name__ == '__main__':
    import sys, json
    if len(sys.argv)!=7 or Path(sys.argv[6])!=Path(sys.argv[4]).with_suffix('.hdr-index.sqlite'):
        raise ValueError('Explicit owned HDR scratch index required')
    result = restore_container(*sys.argv[1:5])
    with Path(sys.argv[5]).open('x') as report:json.dump(result, report, indent=2)
