"""Pinned build transformation; preserve upstream licenses and CPU scoring.

CUDA PTX: https://github.com/Netflix/vmaf/pull/1397
CUDA ADM: https://github.com/Netflix/vmaf/issues/1564
"""
import pathlib,hashlib,sys
p=pathlib.Path(sys.argv[1])/'libavfilter/vf_libvmaf.c'
data=p.read_bytes()
if hashlib.sha256(data).hexdigest()!='6c6fa0392255074a2cfbd8bf0264ce53f442f66cb892ea154845eb735b7ea5c9':raise RuntimeError('Unexpected FFmpeg source')
a=b'    AV_PIX_FMT_YUV420P,\n    AV_PIX_FMT_YUV444P16,\n'
b=b'    AV_PIX_FMT_YUV420P,\n    AV_PIX_FMT_YUV420P10,\n    AV_PIX_FMT_YUV444P16,\n'
if data.count(a)!=1:raise RuntimeError('Unexpected format table')
result=data.replace(a,b)
if hashlib.sha256(result).hexdigest()!='8c08f26db914d310a27e77d3977c6a675ea5010eef9c73b4c763e0f6ce08f89a':raise RuntimeError('Unexpected patched output')
p.write_bytes(result)
print('Enabled direct planar 10-bit CUDA scoring input; CPU formats unchanged')
