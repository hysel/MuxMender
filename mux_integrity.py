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
