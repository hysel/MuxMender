"""Exact per-track duration rounding checks backed by decoded audio samples."""
from fractions import Fraction
import math


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
