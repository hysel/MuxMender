"""Read-only, bounded checks before ordinary video re-encoding."""
import math


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
