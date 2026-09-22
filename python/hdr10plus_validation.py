"""Fail-closed HDR10+ frame validation, independent of encoder vendor.

Passing this module proves frame metadata preservation, not perceptual quality
or permission to replace media. Callers must separately validate other tracks.
"""
from fractions import Fraction
from itertools import zip_longest
from media_metadata import equivalent_ratio


def preserve_json_pairs(items):
    """ffprobe emits repeated HDR10+ keys; ordinary JSON parsing loses values."""
    result = {}
    for key, value in items:
        result.setdefault(key, []).append(value)
    return {key: values[0] if len(values) == 1 else values for key, values in result.items()}


def hdr_metadata(frame):
    result = []
    for item in frame.get('side_data_list', []):
        name = item.get('side_data_type', '').lower()
        if 'dovi' in name or 'dolby' in name:
            raise ValueError('Dolby Vision needs a separate preservation workflow')
        if any(token in name for token in ('mastering', 'content light', '2094', 'hdr')):
            result.append(item)
    return result


def canonical_hdr_metadata(items):
    """Normalize exact mastering-display fractions, not measured HDR values.

    HEVC and AV1 can report 35400/50000 and 177/250 for the identical coordinate.
    Dynamic metadata, list ordering and unknown properties remain unchanged.
    """
    fields = {'red_x','red_y','green_x','green_y','blue_x','blue_y',
              'white_point_x','white_point_y','min_luminance','max_luminance'}
    result=[]
    for item in items:
        normalized=dict(item)
        if item.get('side_data_type') == 'Mastering display metadata':
            for key in fields & item.keys():
                try:
                    normalized[key]=Fraction(str(item[key]))
                except (ValueError, ZeroDivisionError, TypeError) as exc:
                    raise ValueError('Invalid mastering-display fraction: '+key) from exc
        result.append(normalized)
    return result


def validate_frames(source, output, mode='hdr10plus'):
    """Accept iterators to avoid retaining a full movie's frame data in memory."""
    if mode not in ('hdr10plus','hdr10','pq','hlg'):raise ValueError('Unsupported HDR preservation mode')
    missing = object()
    count = dynamic_count = static_count = 0
    previous = previous_output = None
    max_delta=Fraction(0)
    fields = ('width', 'height', 'pix_fmt', 'color_range', 'color_space',
              'color_transfer', 'color_primaries', 'sample_aspect_ratio')
    for index, (a, b) in enumerate(zip_longest(source, output, fillvalue=missing)):
        if a is missing or b is missing:
            raise ValueError('Frame count changed')
        supported={f'yuv{chroma}p{depth}' for chroma in ('420','422','444') for depth in ('','10le','12le')}
        if a.get('pix_fmt') not in supported or a.get('color_transfer') != ('arib-std-b67' if mode=='hlg' else 'smpte2084'):
            raise ValueError('HDR path requires matching transfer and supported native pixel format')
        for key in fields:
            if a.get(key) in (None, 'unknown', 'unspecified') or not (equivalent_ratio(a.get(key),b.get(key)) if key=='sample_aspect_ratio' else a.get(key)==b.get(key)):
                raise ValueError(f'Frame {index}: {key} missing or changed')
        for record in (a,b):
            if record.get('interlaced_frame') != 0 or record.get('repeat_pict') != 0:
                raise ValueError(f'Frame {index}: unconfirmed progressive/non-repeated frame')
            if any('display matrix' in s.get('side_data_type','').lower() for s in record.get('side_data_list',[])):
                raise ValueError('Display rotation requires separate geometry validation')
        try:
            left = Fraction(a['best_effort_timestamp_time'])
            right = Fraction(b['best_effort_timestamp_time'])
        except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
            raise ValueError('Missing or invalid frame timing') from exc
        delta=abs(left-right);max_delta=max(max_delta,delta)
        if delta>Fraction(1,500) or (previous is not None and left <= previous) or (previous_output is not None and right<=previous_output):
            raise ValueError(f'Frame {index}: timestamp changed or non-increasing')
        previous = left
        previous_output=right
        original, encoded = hdr_metadata(a), hdr_metadata(b)
        if a.get('chroma_location') != b.get('chroma_location'):
            raise ValueError(f'Frame {index}: chroma location changed')
        if mode=='hdr10' and any(any(token in item.get('side_data_type','').lower()
                                     for token in ('dynamic','2094','hdr10+')) for item in original+encoded):
            raise ValueError('Dynamic HDR found during static HDR10 validation; requires separate route')
        if canonical_hdr_metadata(original) != canonical_hdr_metadata(encoded):
            raise ValueError(f'Frame {index}: HDR metadata changed')
        dynamic_count += any('2094-40' in item.get('side_data_type', '') or
                             'HDR10+' in item.get('side_data_type', '') for item in original)
        static_count += any(item.get('side_data_type')=='Mastering display metadata' for item in original)
        count += 1
    if not count or (mode=='hdr10plus' and not dynamic_count) or (mode=='hdr10' and not static_count):
        raise ValueError('No '+mode+' frame evidence')
    return dict(frames=count, hdr10plus_frames=dynamic_count,static_hdr_frames=static_count,mode=mode,
                hdr_metadata_exact=True, frame_timestamps_exact=max_delta==0,frame_timing_preserved=True,max_timestamp_delta_seconds=float(max_delta),
                geometry_color_exact=True, quality_approved=False,
                replacement_authorized=False)
