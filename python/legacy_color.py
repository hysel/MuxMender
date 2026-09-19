"""Recover declared SDR metadata; never infer color from resolution alone."""
import copy
import json
import math
import subprocess

FIELDS=('color_primaries','color_transfer','color_space','color_range')
UNKNOWN=(None,'unknown','unspecified','reserved','')
SDR_PRIMARIES={'bt709','smpte170m','bt470bg'}
SDR_TRANSFER={'bt709','smpte170m','gamma22','gamma28','bt470m','bt470bg'}
SDR_MATRIX={'bt709','smpte170m','bt470bg'}


def inspect_frames(ffprobe,source,duration):
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid duration for color inspection')
    intervals=','.join(f'{duration*f:.3f}%+#24' for f in (.1,.5,.9))
    command=[ffprobe,'-v','error','-select_streams','v:0','-read_intervals',intervals,'-show_frames',
             '-show_entries','frame=color_primaries,color_transfer,color_space,color_range:frame_side_data',
             '-of','json',str(source)]
    return json.loads(subprocess.check_output(command,text=True,timeout=60)).get('frames',[])


def resolve(data,frames,assumption='inspect'):
    effective=copy.deepcopy(data)
    video=next(s for s in effective['streams'] if s['codec_type']=='video')
    evidence=dict(original={k:video.get(k) for k in FIELDS},decoded_frames=len(frames),assumed=[],recovered=[])
    for frame in frames:
        for item in frame.get('side_data_list',[]):
            if any(token in str(item.get('side_data_type','')).lower() for token in ('dovi','dolby','mastering','content light','hdr','display matrix')):
                raise ValueError('HDR/Dolby Vision or geometry side data requires its specialized workflow')
    for key in FIELDS:
        values={f[key] for f in frames if f.get(key) not in UNKNOWN}
        if video.get(key) not in UNKNOWN:values.add(video[key])
        if len(values)>1:raise ValueError('Conflicting color metadata: '+key)
        if values:
            if video.get(key) in UNKNOWN:evidence['recovered'].append(key)
            video[key]=next(iter(values))
    if assumption=='bt709-limited':
        expected=dict(color_primaries='bt709',color_transfer='bt709',color_space='bt709',color_range='tv')
        for key,value in expected.items():
            if video.get(key) in UNKNOWN:
                video[key]=value;evidence['assumed'].append(key)
            elif video[key]!=value:raise ValueError('BT.709 test assumption conflicts with declared '+key)
    missing=[key for key in FIELDS if video.get(key) in UNKNOWN]
    evidence.update(effective={k:video.get(k) for k in FIELDS},missing=missing,
                    replacement_allowed=not evidence['assumed'] and not missing)
    return effective,evidence


def is_supported(video):
    return (video.get('color_primaries') in SDR_PRIMARIES and video.get('color_transfer') in SDR_TRANSFER
            and video.get('color_space') in SDR_MATRIX)
