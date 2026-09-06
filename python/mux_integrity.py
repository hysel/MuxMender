"""Conservative, bounded startup checks for standalone output publication."""
import json
import math
from fractions import Fraction
import subprocess

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
    """Keep original stream order, metadata, chapters and explicit dispositions."""
    streams = source_probe['streams']
    if sum(s.get('codec_type') == 'video' for s in streams) != 1:
        raise ValueError('NVIDIA finalization requires exactly one video stream')
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
            '-max_interleave_delta', str(INTERLEAVE_MICROSECONDS), str(output)]


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
    if len(streams) != 1 or streams[0].get('codec_name') != 'h264':
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
