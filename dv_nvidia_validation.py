"""Bounded-memory frame evidence for the explicit NVIDIA DV experiment."""
import itertools
from pathlib import Path
import subprocess
import time
from fractions import Fraction

import dv_preservation_test as dv


def grouped_packets(packets):
    """Allow mux interleaving changes, but preserve order within every track."""
    groups = {}
    for packet in packets:
        groups.setdefault(packet['stream_index'], []).append(packet)
    return groups


def compare_track_packets(before, after, streams):
    """Exact bytes/order/PTS; report AAC container-duration quantization separately.

    Caller must additionally prove decoded PCM identity for every returned track.
    """
    left, right = grouped_packets(before), grouped_packets(after)
    if left.keys() != right.keys():
        raise ValueError('Track packet inventory changed')
    info = {s['index']: s for s in streams}
    rounded = {}
    for index, packets in left.items():
        if len(packets) != len(right[index]):
            raise ValueError('Track packet count changed')
        for a, b in zip(packets, right[index]):
            if a == b:
                continue
            if {k:v for k,v in a.items() if k != 'duration_time'} != {k:v for k,v in b.items() if k != 'duration_time'}:
                raise ValueError('Track packet bytes, sequence or timestamps changed')
            stream = info[index]
            if stream.get('codec_type') != 'audio' or stream.get('codec_name') != 'aac' or stream.get('time_base') != '1/1000':
                raise ValueError('Unexpected packet duration change')
            x, y = Fraction(a['duration_time']), Fraction(b['duration_time'])
            if min(x,y) <= 0 or abs(x-y) > Fraction(1,1000):
                raise ValueError('AAC duration change exceeds one Matroska millisecond')
            rounded[index] = rounded.get(index, 0)+1
    return rounded


def frame_evidence(ffprobe, source, output, guard, timeout=3600):
    fields = ('side_data_type,red_x,red_y,green_x,green_y,blue_x,blue_y,'
              'white_point_x,white_point_y,min_luminance,max_luminance,max_content,max_average')
    command = [ffprobe, '-v', 'error', '-threads', '0', '-select_streams', 'v:0',
               '-show_frames', '-show_entries',
               'frame=best_effort_timestamp_time,interlaced_frame,repeat_pict:frame_side_data=' + fields,
               '-of', 'compact', str(source)]
    started = last = time.monotonic()
    with Path(output).open('xb') as out, Path(str(output)+'.log').open('xb') as err:
        process = subprocess.Popen(command, stdout=out, stderr=err)
        try:
            while process.poll() is None:
                guard()
                now = time.monotonic()
                if now-started > timeout:
                    raise RuntimeError('Frame evidence timeout; all files retained')
                if now-last > 15:
                    print(f'{guard.phase}: {now-started:.0f}s elapsed', flush=True)
                    last = now
                time.sleep(.5)
            if process.returncode:
                raise RuntimeError(f'Frame decode failed; see {output}.log')
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
    return command


def frames(path):
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                continue
            if not line.startswith('frame|'):
                raise ValueError('Unexpected frame evidence record')
            fields, side = {}, {}
            for item in line.strip().split('|')[1:]:
                key, separator, value = item.partition('=')
                if not separator:
                    raise ValueError('Malformed frame evidence field')
                if key.startswith('side_datum/'):
                    group, key = key.split(':', 1)
                    side.setdefault(group, {})[key] = value
                elif ':' not in key:
                    fields[key] = value
            fields['interlaced_frame'] = int(fields['interlaced_frame'])
            fields['repeat_pict'] = int(fields['repeat_pict'])
            fields['side_data_list'] = list(side.values())
            dv.require_nvidia_frames([fields])
            if not any('Dolby Vision RPU Data' == s.get('side_data_type') for s in side.values()):
                raise ValueError('A decoded frame lacks Dolby Vision RPU data')
            yield fields


def validate_source_frames(path, expected_pts, guard=lambda: None):
    count = 0
    for frame, timestamp in itertools.zip_longest(frames(path), expected_pts):
        guard()
        if frame is None or timestamp is None or abs(float(frame['best_effort_timestamp_time'])-timestamp) > .002:
            raise ValueError('Source decoded-frame and packet timelines differ')
        count += 1
    return count


def compare_frames(source, output, guard=lambda: None):
    count, rounded = 0, 0
    for before, after in itertools.zip_longest(frames(source), frames(output)):
        guard()
        if before is None or after is None:
            raise ValueError('Decoded frame count changed')
        if abs(float(before['best_effort_timestamp_time'])-float(after['best_effort_timestamp_time'])) > .002:
            raise ValueError('Decoded frame timing changed')
        if dv.compare_static_hdr([before], [after]):
            rounded += 1
        count += 1
    if not count:
        raise ValueError('No decoded frames')
    return dict(frames=count, static_hdr_rounding_frames=rounded,
                timing_preserved=True, static_hdr_preserved=True,
                progressive=True, rpu_present_every_frame=True)
