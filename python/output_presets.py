"""Shared output targets and explicit target-resolution quality policy.

Plex-inspired targets are not a promise of Direct Play on every Plex client.
Audio and subtitles remain copies; their bitrate is additional to video.
"""
from copy import deepcopy
from fractions import Fraction

PRESETS={
    'original':dict(label='Original resolution — automatic size reduction',width=None,height=None,
                    video_bps=None,mean=90,p5=90),
    'tv1080':dict(label='1080p TV · up to 8 Mbps video',width=1920,height=1080,
                  video_bps=8000000,mean=95,p5=90),
    'mobile720':dict(label='720p · up to 4 Mbps video',width=1280,height=720,
                     video_bps=4000000,mean=93,p5=90),
    'small480':dict(label='480p · up to 1.5 Mbps video',width=854,height=480,
                    video_bps=1500000,mean=90,p5=90),
}


def preset(identifier='original'):
    if not isinstance(identifier,str) or identifier not in PRESETS:
        raise ValueError('Unknown output preset')
    return dict(PRESETS[identifier],id=identifier)


def geometry(video,identifier):
    policy=preset(identifier)
    width=video['width'];height=video['height']
    if type(width) is not int or type(height) is not int or min(width,height)<=0:
        raise ValueError('Invalid source geometry for output preset')
    if policy['width'] is None:return dict(width=width,height=height,sar=video.get('sample_aspect_ratio'),resized=False)
    ratio=min(Fraction(1),Fraction(policy['width'],width),Fraction(policy['height'],height))
    if ratio==1:return dict(width=width,height=height,sar=video.get('sample_aspect_ratio'),resized=False)
    sar=Fraction(str(video.get('sample_aspect_ratio','1:1')).replace(':','/'))
    if sar<=0:raise ValueError('Unresolved source pixel aspect ratio')
    unit=4 if video.get('field_order') in ('tt','bb','tb','bt') else 2
    new_width=max(2,int(width*ratio)//2*2)
    new_height=max(unit,int(height*ratio)//unit*unit)
    # Scale rounding must not change display aspect, stretch, crop or upscale.
    new_sar=sar*Fraction(width*new_height,height*new_width)
    return dict(width=new_width,height=new_height,
                sar=f'{new_sar.numerator}:{new_sar.denominator}',resized=True)


def scale_filter(video,identifier):
    if identifier=='original':return ''
    target=geometry(video,identifier)
    if not target['resized']:return ''
    interl=1 if video.get('field_order') in ('tt','bb','tb','bt') else 0
    return (f"scale={target['width']}:{target['height']}:flags=lanczos:interl={interl},"
            f"setsar={target['sar'].replace(':','/')}:max=1000000")


def expected_metadata(before,identifier):
    result=deepcopy(before)
    from auto_optimize import main_video
    video=main_video(result);target=geometry(video,identifier)
    if target['resized']:
        video.update(width=target['width'],height=target['height'],sample_aspect_ratio=target['sar'])
    return result


def expected_frame_rows(rows,target):
    for row in rows:
        expected=dict(row)
        if target['resized']:
            expected.update(width=str(target['width']),height=str(target['height']),sample_aspect_ratio=target['sar'])
        yield expected


def encoder_options(video,identifier):
    policy=preset(identifier)
    if identifier=='original':return []
    filters=scale_filter(video,identifier)
    options=['-filter:v:0',filters] if filters else []
    if policy['video_bps'] is not None:
        # A video ceiling, not a total media bitrate or a quality waiver.
        options+=['-maxrate:v:0',str(policy['video_bps']),'-bufsize:v:0',str(2*policy['video_bps'])]
    return options
