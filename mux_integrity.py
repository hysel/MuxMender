"""Conservative, bounded startup checks for standalone output publication."""
import json
import math
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
