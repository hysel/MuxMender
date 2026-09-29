"""Read-only HDR routing evidence; never authorizes conversion or replacement."""
import json
import math
import subprocess


class AutomaticHDRSkip(ValueError):
    reason_code = 'dolby_vision_requires_preservation_route'


def recover_empty_dv_declaration(video,evidence):
    """Remove only a contradicted container declaration from in-memory routing."""
    from hevc_inventory import absent_dv
    if video.get('codec_name')!='hevc' or not absent_dv(evidence):return False
    sides=video.get('side_data_list',[])
    declared=[s for s in sides if s.get('side_data_type')=='DOVI configuration record']
    if not declared:return False
    video['side_data_list']=[s for s in sides if s.get('side_data_type')!='DOVI configuration record']
    return True


def enforce_automatic_policy(video, inspection=None):
    """Prevent the ordinary HDR path from silently dropping Dolby Vision."""
    observed=classify(video,[]) if inspection is None else inspection
    if observed.get('kind')=='Dolby Vision' or classify(video,[])['kind']=='Dolby Vision':
        raise AutomaticHDRSkip('Dolby Vision requires its metadata-preserving route, not ordinary HDR encoding. Original retained.')


def classify(video, frames):
    names = {str(item.get('side_data_type', '')).lower()
             for record in [video, *frames]
             for item in record.get('side_data_list', [])}
    if any('dovi' in name or 'dolby' in name for name in names):
        kind = 'Dolby Vision'
    elif any('2094-40' in name or 'hdr10+' in name for name in names):
        kind = 'HDR10+'
    elif any('dynamic' in name and 'hdr' in name for name in names):
        kind = 'dynamic HDR'
    elif video.get('color_transfer') == 'arib-std-b67':
        kind = 'HLG'
    else:
        kind = 'PQ HDR (dynamic metadata not observed in sampled frames)'
    return dict(kind=kind, sampled_frames=len(frames), side_data_types=sorted(names),
                full_metadata_scan_required=True, conversion_authorized=False,
                reason=f'{kind} requires a validated metadata-preserving encoding and quality workflow; original retained')


def inspect(ffprobe, source, video, duration):
    duration = float(duration)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('HDR inspection requires a finite positive duration')
    frames = []
    for fraction in (.15, .5, .85):
        result = subprocess.run([str(ffprobe), '-v', 'error', '-select_streams', 'V:0',
            '-read_intervals', f'{duration*fraction:.3f}%+#1', '-show_frames',
            '-of', 'json', str(source)], capture_output=True, text=True, timeout=30, check=True)
        window = json.loads(result.stdout).get('frames', [])
        if not window:
            raise ValueError('HDR inspection returned no decoded frames')
        frames.extend(window)
    report=classify(video, frames)
    # Recover absent container labels only from consistent decoded declarations.
    # These are routing hints; full-frame metadata validation is still required.
    from legacy_color import FIELDS, UNKNOWN
    recovered={}
    for key in FIELDS:
        values={frame[key] for frame in frames if frame.get(key) not in UNKNOWN}
        if video.get(key) not in UNKNOWN:values.add(video[key])
        if len(values)>1:raise ValueError('Conflicting HDR color metadata: '+key)
        if video.get(key) in UNKNOWN and values:recovered[key]=next(iter(values))
    report['recovered_color']=recovered
    return report
