"""Conservative, bounded startup checks for standalone output publication."""
import json
import math
from fractions import Fraction
import subprocess
import hashlib
from pathlib import Path


def playback_plan(data, audio_track=None, subtitle_track=None):
    """Explicit additive EAC3 policy; track selectors are zero-based by type."""
    streams = data['streams']
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    subtitles = [s for s in streams if s.get('codec_type') == 'subtitle']
    if audio_track is None:
        defaults = [i for i, s in enumerate(audio) if s.get('disposition', {}).get('default')]
        if len(defaults) == 1:
            audio_track = defaults[0]
        elif len(audio) == 1:
            audio_track = 0
        else:
            raise ValueError('Choose --compatibility-audio-track: audio selection is ambiguous or absent')
    if not 0 <= audio_track < len(audio):
        raise ValueError('Compatibility audio track is out of range')
    selected = audio[audio_track]
    if selected.get('channels') not in (1, 2, 6) or selected.get('channel_layout') not in ('mono', 'stereo', '5.1', '5.1(side)'):
        raise ValueError('Compatibility audio supports known mono, stereo or 5.1 layouts; no automatic downmix')
    if subtitle_track is not None and not 0 <= subtitle_track < len(subtitles):
        raise ValueError('Default subtitle track is out of range')
    # Reuse the selected EAC3 track instead of growing repeated outputs.
    added = selected.get('codec_name') != 'eac3'
    dispositions = []
    for s in streams:
        flags = {k for k, v in s.get('disposition', {}).items() if v}
        if s.get('codec_type') == 'audio':
            flags.discard('default')
            if not added and s['index'] == selected['index']:
                flags.add('default')
        if s.get('codec_type') == 'subtitle' and subtitle_track is not None:
            flags.discard('default')
            if s['index'] == subtitles[subtitle_track]['index']:
                flags.add('default')
        dispositions.append(sorted(flags))
    if added:
        dispositions.append(['default'])
    # Some clients choose the first matching-language audio despite default flags.
    # Keep an explicit identity map so reordering never weakens preservation checks.
    compatible = None if added else selected['index']
    order = []
    inserted = False
    flags_by_index = {s['index']: dispositions[i] for i, s in enumerate(streams)}
    flags_by_index[None] = ['default']
    for s in streams:
        if s.get('codec_type') == 'audio' and not inserted:
            order.append(compatible)
            inserted = True
        if added or s['index'] != compatible:
            order.append(s['index'])
    dispositions = [flags_by_index[i] for i in order]
    return dict(audio_index=selected['index'], audio_ordinal=audio_track,
                added_audio=added, new_audio_ordinal=0, output_order=order,
                language=selected.get('tags', {}).get('language', 'und'),
                channels=selected['channels'], dispositions=dispositions,
                subtitle_track=subtitle_track)


def playback_command(source, output, data, plan, ffmpeg):
    command = [ffmpeg, '-hide_banner', '-nostdin', '-n', '-copyts', '-i', str(source)]
    for index in plan['output_order']:
        command += ['-map', f"0:{plan['audio_index'] if index is None else index}"]
    command += ['-map_metadata', '0', '-map_chapters', '0', '-c', 'copy']
    if plan['added_audio']:
        n = plan['new_audio_ordinal']
        command += [f'-c:a:{n}', 'eac3', f'-b:a:{n}', '640k', f'-ar:a:{n}', '48000',
                    f'-metadata:s:a:{n}', f"language={plan['language']}",
                    f'-metadata:s:a:{n}', 'title=EAC3 compatibility']
    for i, flags in enumerate(plan['dispositions']):
        command += [f'-disposition:{i}', '+'.join(flags) or '0']
    return command + ['-avoid_negative_ts', 'disabled', '-max_interleave_delta',
                      '0', str(output)]


def packet_fingerprints(path, ffprobe):
    """Bounded-memory per-stream fingerprints include packet bytes and timing."""
    command = [ffprobe, '-v', 'error', '-show_packets', '-show_data_hash', 'sha256',
               '-show_entries', 'packet=stream_index,pts_time,dts_time,duration_time,size,data_hash',
               '-of', 'compact=p=0:nk=0', str(path)]
    hashes, counts = {}, {}
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True, encoding='utf-8') as process:
        try:
            for line in process.stdout:
                fields = dict(p.split('=', 1) for p in line.strip().split('|') if '=' in p)
                if 'stream_index' not in fields:
                    continue
                index = int(fields.pop('stream_index'))
                hashes.setdefault(index, hashlib.sha256()).update(json.dumps(fields, sort_keys=True).encode('utf-8'))
                counts[index] = counts.get(index, 0) + 1
            if process.wait():
                raise RuntimeError('Playback packet verification failed')
        finally:
            if process.poll() is None:
                process.kill()
    return {i: (counts[i], h.hexdigest()) for i, h in hashes.items()}


def verify_playback_copy(source, output, before, after, plan, ffprobe):
    expected = len(before['streams']) + int(plan['added_audio'])
    if len(after['streams']) != expected:
        raise RuntimeError('Playback preparation changed the stream count')
    for i, original in enumerate(before['streams']):
        result = after['streams'][plan['output_order'].index(original['index'])]
        for key in ('codec_type', 'codec_name', 'width', 'height', 'pix_fmt', 'color_space',
                    'color_transfer', 'color_primaries', 'color_range', 'sample_rate', 'channels', 'channel_layout', 'side_data_list'):
            if original.get(key) != result.get(key):
                raise RuntimeError(f'Playback preparation changed original stream {i}: {key}')
        for key in ('language', 'title'):
            if original.get('tags', {}).get(key) != result.get('tags', {}).get(key):
                raise RuntimeError(f'Playback preparation changed stream {i} {key}')
    for i, stream in enumerate(after['streams']):
        actual = sorted(k for k, v in stream.get('disposition', {}).items() if v)
        if actual != plan['dispositions'][i]:
            raise RuntimeError('Playback default/forced flags do not match the plan')
    if before.get('chapters', []) != after.get('chapters', []):
        raise RuntimeError('Playback preparation changed chapters')
    if plan['added_audio']:
        added = after['streams'][plan['output_order'].index(None)]
        if added.get('codec_name') != 'eac3' or added.get('channels') != plan['channels'] or added.get('sample_rate') != '48000':
            raise RuntimeError('Unexpected compatibility audio format')
    original = packet_fingerprints(source, ffprobe)
    result = packet_fingerprints(output, ffprobe)
    if any(result.get(plan['output_order'].index(i)) != value for i, value in original.items()):
        raise RuntimeError('Original packet payloads or timestamps changed during playback preparation')
    return {'original_packets_and_timing': True, 'stream_metadata': True,
            'chapters': True, 'defaults_and_forced_flags': True}

# Finite instead of unlimited buffering for sparse subtitle streams.
INTERLEAVE_MICROSECONDS = 10_000_000
MAX_STARTUP_AUDIO_LEAD = 0.1


def seek_track_alignment(data, tolerance=2.0):
    """Require every audio/video track promptly at a seek point, not just video."""
    indices = {s['index'] for s in data['streams'] if s.get('codec_type') in ('video', 'audio')}
    first = {}
    for packet in data.get('packets', []):
        index = packet['stream_index']
        if index in indices and index not in first:
            try:
                value = float(packet['pts_time'])
            except (KeyError, TypeError, ValueError):
                return False
            if not math.isfinite(value):
                return False
            first[index] = value
    return bool(indices) and first.keys() == indices and max(first.values())-min(first.values()) <= tolerance


def verify_seek_interleaving(path, ffprobe, positions):
    results = []
    for position in positions:
        command = [ffprobe, '-v', 'error', '-read_intervals', f'{position}%+#2048',
                   '-show_streams', '-show_packets', '-show_entries',
                   'stream=index,codec_type:packet=stream_index,pts_time', '-of', 'json', str(path)]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        passed = result.returncode == 0 and seek_track_alignment(json.loads(result.stdout))
        results.append({'seconds': position, 'passed': passed})
    return bool(results) and all(r['passed'] for r in results), results


def startup_audio_lead(data):
    """Audio seconds physically preceding the first video packet; None if unknown."""
    videos = {s['index'] for s in data['streams'] if s.get('codec_type') == 'video'}
    audios = {s['index'] for s in data['streams'] if s.get('codec_type') == 'audio'}
    if not videos:
        return None
    if not audios:
        return 0.0
    latest_audio = None
    for packet in data.get('packets', []):
        index = packet['stream_index']
        if index not in videos | audios:
            continue
        try:
            timestamp = float(packet['pts_time'])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(timestamp):
            return None
        if index in videos:
            return max(0.0, latest_audio - timestamp) if latest_audio is not None else 0.0
        latest_audio = timestamp if latest_audio is None else max(latest_audio, timestamp)
    return None


def verify_startup_interleaving(path, ffprobe):
    """Bound output to 2048 packets; reject insufficient evidence, never silently pass."""
    command = [ffprobe, '-v', 'error', '-read_intervals', '%+#2048',
               '-show_streams', '-show_packets', '-show_entries',
               'stream=index,codec_type:packet=stream_index,pts_time', '-of', 'json', str(path)]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=30)
    if result.returncode:
        return False, 'startup interleaving probe failed; output retained for review'
    lead = startup_audio_lead(json.loads(result.stdout))
    if lead is None:
        return False, 'startup packet ordering could not be verified within 2048 packets'
    if lead > MAX_STARTUP_AUDIO_LEAD:
        return False, f'audio precedes first video packet by {lead:.3f}s; unsafe startup interleaving'
    return True, f'startup interleaving verified ({lead:.3f}s audio prefix)'


def video_stage_command(command):
    """Derive a video-only command; input timestamps remain on the source timeline."""
    result = list(command)
    index = result.index('-map')
    if result[index + 1] != '0':
        raise ValueError('Expected the standard single-input stream mapping')
    result[index + 1] = '0:v:0'
    # Finalization restores all source dispositions at their original indices.
    index = 0
    while index < len(result) - 1:
        if result[index].startswith('-disposition:'):
            del result[index:index + 2]
        else:
            index += 1
    if '-copyts' not in result:
        index = result.index('-i')
        result[index:index] = ['-copyts']
    if '-avoid_negative_ts' not in result:
        result[-1:-1] = ['-avoid_negative_ts', 'disabled']
    if '-fps_mode' not in result:
        result[-1:-1] = ['-fps_mode', 'passthrough']
    if '-enc_time_base:v' not in result:
        result[-1:-1] = ['-enc_time_base:v', 'demux']
    return result


def finalize_command(video, source, output, source_probe, ffmpeg):
    """Keep tracks and chronological interleaving despite sparse subtitles.

    Callers must monitor memory while running this ordered mux command.
    """
    streams = source_probe['streams']
    if sum(s.get('codec_type') == 'video' for s in streams) != 1:
        raise ValueError('Hardware finalization requires exactly one video stream')
    mapping = []
    disposition = []
    for index, stream in enumerate(streams):
        mapping += ['-map', '0:v:0' if stream['codec_type'] == 'video' else f"1:{stream['index']}"]
        flags = '+'.join(k for k, value in stream.get('disposition', {}).items() if value) or '0'
        disposition += [f'-disposition:{index}', flags]
    return [ffmpeg, '-hide_banner', '-nostdin', '-n', '-copyts',
            '-i', str(video), '-i', str(source), *mapping,
            '-map_metadata', '1', '-map_chapters', '1', '-c', 'copy',
            *disposition, '-avoid_negative_ts', 'disabled',
            '-max_interleave_delta', '0', str(output)]


def savings_summary(size_pairs):
    """Aggregate accepted outputs; percentage is weighted by source bytes."""
    pairs = list(size_pairs)
    source = sum(a for a, b in pairs)
    output = sum(b for a, b in pairs)
    saved = source - output
    return dict(files=len(pairs), source_bytes=source, output_bytes=output,
                saved_bytes=saved, saved_MB=saved/10**6, saved_GB=saved/10**9,
                saved_TB=saved/10**12, saved_percent=100*saved/source if source else 0,
                basis='Accepted output size reduction; originals and intermediates retained unless explicitly removed. Decimal MB/GB/TB; not measured disk space reclaimed.')


def savings_summary_text(summary):
    return (f"Size reduction across {summary['files']} accepted output(s): "
            f"{summary['saved_MB']:,.2f} MB / {summary['saved_GB']:,.3f} GB / "
            f"{summary['saved_TB']:.6f} TB ({summary['saved_percent']:.2f}%). "
            'Retained originals/intermediates still occupy disk space.')


class NoSavingsError(ValueError):
    """Stop optimization while retaining the original and diagnostic outputs."""


def savings_decision(source_bytes, output_bytes, minimum_percent=5.0):
    if source_bytes <= 0 or output_bytes <= 0:
        raise ValueError('Positive source and output sizes are required')
    if not math.isfinite(minimum_percent) or not 0 <= minimum_percent < 100:
        raise ValueError('Minimum savings must be finite and in [0,100)')
    savings = 100 * (source_bytes-output_bytes) / source_bytes
    eligible = output_bytes < source_bytes and savings >= minimum_percent
    reason = ('meets size threshold; preservation and playback checks still required' if eligible else
              'output is larger than or equal to the source; keep original' if output_bytes >= source_bytes else
              'savings are below the minimum; keep original')
    return dict(eligible=eligible, savings_percent=savings,
                minimum_percent=minimum_percent, source_bytes=source_bytes,
                output_bytes=output_bytes, reason=reason)


def normalize_rounding(left, right, original_decode, output_decode):
    def tracks(items):
        result={}
        for item in items:
            key=item.get('stream_index')
            if not isinstance(key,int):raise ValueError('Missing stream identity')
            result.setdefault(key,[]).append(item)
        return result
    def stream_formats(data):
        return {s['index']:(s['codec_name'],int(s['sample_rate']),Fraction(s['time_base']))
                for s in data.get('streams',[])}
    formats=stream_formats(original_decode)
    if formats!=stream_formats(output_decode):raise ValueError('Audio format/time base changed')
    a,b=tracks(left),tracks(right)
    fa,fb=tracks(original_decode.get('frames',[])),tracks(output_decode.get('frames',[]))
    if not a.keys()==b.keys()==fa.keys()==fb.keys():raise ValueError('Audio track/frame identities changed')
    normalized_left=[];normalized_right=[];rounded=0
    for key in a:
        if not len(a[key])==len(b[key])==len(fa[key])==len(fb[key]):
            raise ValueError('Cannot establish one-to-one audio packet/frame correspondence')
        _,rate,tick=formats[key]
        if rate<=0 or not 0<tick<=Fraction(1,1000):raise ValueError('Unsupported audio clock precision')
        for packet,other,frame,other_frame in zip(a[key],b[key],fa[key],fb[key]):
            if frame!=other_frame or frame.get('pts_time')!=packet.get('pts_time') or frame.get('pts_time')!=other.get('pts_time'):
                raise ValueError('Decoded audio frame timing/sample metadata changed')
            samples=frame.get('nb_samples')
            if not isinstance(samples,int) or samples<=0:raise ValueError('Invalid decoded sample count')
            x,y=dict(packet),dict(other)
            if x.get('duration_time')!=y.get('duration_time') and 'duration_time' in x and 'duration_time' in y:
                duration=Fraction(samples,rate)
                allowed={math.floor(duration/tick)*tick, math.ceil(duration/tick)*tick}
                if Fraction(x['duration_time']) not in allowed or Fraction(y['duration_time']) not in allowed:
                    raise ValueError('Audio duration difference exceeds sample-backed rounding')
                x['duration_time']=y['duration_time']=str(duration)
                rounded+=1
            normalized_left.append(x);normalized_right.append(y)
    return normalized_left,normalized_right,rounded

def inspect_packets(packets, initial_dts_allowance=0):
    reasons = []
    previous = None
    if not packets:
        return ['No video packets available in sampled window']
    for index, packet in enumerate(packets):
        try:
            pts = float(packet['pts_time'])
            if not math.isfinite(pts):
                raise ValueError('nonfinite PTS')
            if 'dts_time' not in packet and index < initial_dts_allowance and previous is None:
                continue
            dts = float(packet['dts_time'])
            if not math.isfinite(pts) or not math.isfinite(dts):
                raise ValueError('nonfinite')
        except (KeyError, TypeError, ValueError):
            reasons.append('Missing or invalid video PTS/DTS')
            continue
        # PTS may be reordered by B-frames; DTS must increase in demux order.
        if previous is not None and dts <= previous:
            reasons.append('Non-increasing video DTS')
        previous = dts
    return sorted(set(reasons))

def verified_reorder_prefix(data, frames, seek_preroll=False):
    """Accept only a bounded leading DTS omission backed by decoded real PTS.

    This does not generate timestamps or accept best-effort timestamp guesses.
    """
    streams = data.get('streams', [])
    if len(streams) != 1 or streams[0].get('codec_name') not in ('h264', 'hevc'):
        return 0
    delay = streams[0].get('has_b_frames', 0)
    if not isinstance(delay, int) or not 1 <= delay <= 16:
        return 0
    packets = data.get('packets', [])
    missing = 0
    for packet in packets:
        if 'dts_time' in packet:
            break
        missing += 1
    if not 1 <= missing <= delay or len(packets) <= missing:
        return 0
    if inspect_packets(packets, missing):
        return 0
    try:
        packet_pts = sorted(float(p['pts_time']) for p in packets)
        frame_pts = [float(f['pts_time']) for f in frames]
    except (KeyError, TypeError, ValueError):
        return 0
    # A seek into an open GOP can include leading pictures needing the preceding
    # GOP. Account only for bounded pictures preceding the first key picture;
    # never apply this exception at the beginning of the actual source.
    if seek_preroll and frame_pts and 'K' in packets[0].get('flags', ''):
        first = float(packets[0]['pts_time'])
        leading = [p for p in packet_pts if p < first]
        if frame_pts[0] == first and len(leading) <= delay:
            packet_pts = [p for p in packet_pts if p >= first]
    if len(frame_pts) != len(packet_pts) or not all(math.isfinite(p) for p in frame_pts):
        return 0
    if any(b <= a for a, b in zip(frame_pts, frame_pts[1:])):
        return 0
    return missing if frame_pts == packet_pts else 0

def conversion_preflight(info, ffprobe, read_json):
    reasons = []
    for field in ('color_primaries', 'color_transfer', 'color_space', 'color_range'):
        if getattr(info, field) in (None, '', 'unknown', 'unspecified', 'reserved'):
            reasons.append('Unspecified ' + field + '; no automatic color assumption')
    result = dict(status='needs-review', reasons=reasons, windows=[],
                  scope='Up to 256 video packets at start, midpoint, and near end; not full-file validation')
    if reasons:
        return result
    if not math.isfinite(info.duration_seconds) or info.duration_seconds <= 0:
        reasons.append('Unknown or invalid duration')
        return result
    positions = sorted(set((0.0, info.duration_seconds/2, max(0.0, info.duration_seconds-20))))
    for position in positions:
        data = read_json([ffprobe, '-v', 'error', '-select_streams', 'v:0',
            '-read_intervals', f'{position:g}%+#256', '-show_packets', '-show_entries',
            'packet=pts_time,dts_time,flags:stream=codec_name,has_b_frames', '-show_streams', '-of', 'json', info.path])
        findings = inspect_packets(data.get('packets', []))
        allowance = 0
        if findings == ['Missing or invalid video PTS/DTS']:
            decoded = read_json([ffprobe, '-v', 'error', '-threads', '2', '-select_streams', 'v:0',
                '-read_intervals', f'{position:g}%+#256', '-show_frames', '-show_entries',
                'frame=pts_time', '-of', 'json', info.path])
            allowance = verified_reorder_prefix(data, decoded.get('frames', []), seek_preroll=position > 0)
            if allowance:
                findings = inspect_packets(data['packets'], allowance)
        result['windows'].append(dict(requested_seconds=position, packet_count=len(data.get('packets', [])),
                                      reasons=findings, verified_initial_dts_omissions=allowance))
        reasons.extend(findings)
    result['reasons'] = sorted(set(reasons))
    result['status'] = 'needs-review' if reasons else 'passed-sampled-checks'
    return result


def repair_av1_hdr_stream(source, destination, mastering, progress=None):
    """Two-pass, bounded-memory IVF repair; no writes until full input validation.

    Keeps all IVF timing/header and coded picture bytes. Only known-clamped MDCV
    coordinates may change. Full source/frame metadata validation is still required.
    """
    import struct
    source, destination = Path(source), Path(destination)
    initial = source.stat()
    if destination.exists() or source.resolve() == destination.resolve():
        raise FileExistsError('HDR repair requires a new destination')
    def walk(output=None):
        summary = dict(frames=0, mastering_obus=0, edit_count=0, edit_examples=[])
        with source.open('rb') as stream:
            header = stream.read(32)
            if len(header) != 32 or header[:4] != b'DKIF':
                raise ValueError('Invalid IVF header')
            if output:
                output.write(header)
            while record := stream.read(12):
                if len(record) != 12:
                    raise ValueError('Truncated IVF frame header')
                size = struct.unpack_from('<I', record)[0]
                if not 0 < size <= 32*1024**2 or summary['frames'] >= 2_000_000:
                    raise ValueError('IVF frame size/count exceeds guarded limit')
                body = stream.read(size)
                if len(body) != size:
                    raise ValueError('Truncated IVF frame')
                patched, details = _repair_av1_hdr_bytes(header+record+body, mastering, True)
                if output:
                    output.write(patched[32:])
                summary['mastering_obus'] += details['mastering_obus']
                summary['edit_count'] += len(details['edits'])
                for edit in details['edits']:
                    if len(summary['edit_examples']) < 16:
                        summary['edit_examples'].append(dict(edit, frame=summary['frames']))
                summary['frames'] += 1
                if progress and summary['frames'] % 256 == 0:
                    progress((50 if output else 0) + 50*stream.tell()/initial.st_size)
        if not summary['frames'] or not summary['mastering_obus']:
            raise ValueError('Missing AV1 mastering metadata')
        return summary
    expected = walk()
    if (source.stat().st_size, source.stat().st_mtime_ns) != (initial.st_size, initial.st_mtime_ns):
        raise ValueError('IVF source changed during validation')
    with destination.open('xb') as output:
        actual = walk(output)
    if expected != actual or (source.stat().st_size, source.stat().st_mtime_ns) != (initial.st_size, initial.st_mtime_ns):
        raise ValueError('IVF source changed during repair; output not accepted')
    return dict(actual, scope='Known MDCV clamp repair; all other bytes and IVF timestamps retained',
                max_frame_bytes=32*1024**2, source_bytes=initial.st_size)


def _repair_av1_hdr_bytes(raw, mastering, allow_no_metadata=False):
    """Bounded diagnostic only: repair the reproduced QSV 50000 chroma clamp.

    Caller must establish constant source metadata and independently check decode
    hashes/timing after repair. Never used by the normal optimizer or its gate.
    Every byte except verified MDCV coordinate fields stays unchanged.
    """
    import struct
    data = bytearray(raw)
    if len(data) < 32 or data[:4] != b'DKIF' or data[8:12] != b'AV01' or struct.unpack_from('<HH', data, 4) != (0, 32):
        raise ValueError('Expected version-zero AV1 IVF with 32-byte header')
    coordinates = ('red_x','red_y','green_x','green_y','blue_x','blue_y','white_point_x','white_point_y')
    def quantize(field, scale):
        value = Fraction(str(mastering[field])) * scale
        return (value + Fraction(1, 2)).numerator // (value + Fraction(1, 2)).denominator
    expected = [quantize(k, 65536) for k in coordinates]
    if any(not 0 <= value < 65536 for value in expected):
        raise ValueError('Mastering coordinates outside representable range')
    lum = [quantize('max_luminance', 256), quantize('min_luminance', 16384)]
    def leb(pos, end):
        value = 0
        for i in range(8):
            if pos >= end:
                raise ValueError('Truncated OBU size/type')
            byte = data[pos]; pos += 1; value |= (byte & 127) << (7*i)
            if not byte & 128:
                return value, pos
        raise ValueError('Oversized OBU LEB128')
    pos, frames, metadata_count, edits = 32, 0, 0, []
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError('Truncated IVF frame')
        size = struct.unpack_from('<I', data, pos)[0]
        pos += 12; end = pos + size; frames += 1
        if end > len(data) or frames > 3600:
            raise ValueError('Truncated or over-bound research IVF')
        while pos < end:
            header = data[pos]; pos += 1
            if header & 129 or not header & 2:
                raise ValueError('Unsupported OBU header')
            if header & 4:
                pos += 1
            size, payload = leb(pos, end); next_pos = payload + size
            if next_pos > end:
                raise ValueError('OBU exceeds frame')
            if (header >> 3) & 15 == 5:
                kind, body = leb(payload, next_pos)
                if kind == 2:
                    if next_pos-body != 25 or data[next_pos-1] != 128:
                        raise ValueError('Unexpected MDCV payload layout')
                    values = struct.unpack_from('>8H2I', data, body)
                    if list(values[8:]) != lum:
                        raise ValueError('Unexpected luminance change; clamp repair refused')
                    for i, wanted in enumerate(expected):
                        if values[i] == wanted:
                            continue
                        if values[i] != 50000 or wanted <= 50000:
                            raise ValueError('Metadata differs beyond reproduced 50000 clamp')
                        struct.pack_into('>H', data, body+2*i, wanted)
                        edits.append(dict(frame=frames-1, field=coordinates[i], before=values[i], after=wanted))
                    metadata_count += 1
            pos = next_pos
    if not frames or (not metadata_count and not allow_no_metadata):
        raise ValueError('No frames/mastering metadata to verify')
    return bytes(data), dict(frames=frames, mastering_obus=metadata_count, edits=edits,
                scope='Bounded metadata-only research; normal AV1 HDR gate unchanged')
