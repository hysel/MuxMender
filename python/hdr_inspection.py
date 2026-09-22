"""Read-only HDR routing evidence; never authorizes conversion or replacement."""
import json
import math
import subprocess


class AutomaticHDRSkip(ValueError):
    reason_code = 'dolby_vision_temporarily_disabled'


def enforce_automatic_policy(video, inspection=None):
    """Temporary shared guardrail; never strip DV to process an HDR10 base layer."""
    observed=classify(video,[]) if inspection is None else inspection
    if observed.get('kind')=='Dolby Vision' or classify(video,[])['kind']=='Dolby Vision':
        raise AutomaticHDRSkip('Dolby Vision conversion is temporarily disabled, including combined Dolby Vision + HDR10+. Original retained; no encoding or replacement performed.')


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
        result = subprocess.run([str(ffprobe), '-v', 'error', '-select_streams', 'v:0',
            '-read_intervals', f'{duration*fraction:.3f}%+#1', '-show_frames',
            '-of', 'json', str(source)], capture_output=True, text=True, timeout=30, check=True)
        window = json.loads(result.stdout).get('frames', [])
        if not window:
            raise ValueError('HDR inspection returned no decoded frames')
        frames.extend(window)
    return classify(video, frames)
