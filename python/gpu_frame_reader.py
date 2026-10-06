"""Select an attested native reader without changing any media validation gate.

An image qualification receipt is installed alongside the reader by the release
process, not supplied by a media file or dashboard request. Unsupported hardware
or scope keeps the CPU reader; a selected reader's decode error is never retried
as a success on another backend.
"""
import hashlib
import json
import math
import os
from pathlib import Path,PurePosixPath
import stat
import sys

READER_ROOT=Path('/opt/muxmender-readers')
PROOF_FIELDS=('full_eof','every_frame_cpu_gpu_equal','corrupt_controls_rejected')
NATIVE_DEMUXERS=frozenset(('matroska','webm','mov','mp4','m4a','3gp','3g2','mj2','mpegts','hevc','obu'))


def visibility_matches(expected,current,sole_uuid):
    """Accept equivalent container selectors only after sole-device attestation.

    NVIDIA's container selector may be `all` or the sole physical UUID. Docker
    device requests can expose that same GPU while leaving the base image's
    selector at `void`; accept this only after sole-device identity attestation.
    CUDA logical-device mask and ordering still must match literally. Never
    infer equivalence for numeric indices, lists or multiple GPUs.
    """
    keys={'CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER'}
    if not isinstance(expected,dict) or not isinstance(current,dict) or set(expected)!=keys or set(current)!=keys:return False
    if any(expected[key]!=current[key] for key in ('CUDA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER')):return False
    before=expected['NVIDIA_VISIBLE_DEVICES'];after=current['NVIDIA_VISIBLE_DEVICES']
    if before==after:return True
    if not isinstance(sole_uuid,str) or not sole_uuid.startswith('GPU-'):return False
    return before in ('all',sole_uuid,'void') and after in ('all',sole_uuid,'void')


def trusted_file(path,limit):
    """Image-owned, bounded, non-linked inputs only; no media-folder receipts."""
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('Linked reader package')
    for parent in path.parents:
        info=parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('Reader package has an untrusted parent directory')
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(descriptor,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or info.st_size>limit:
            raise ValueError('Untrusted reader package')
        return stream.read(limit+1)


def load_qualification(root=READER_ROOT):
    if not sys.platform.startswith('linux'):return None
    try:
        root=Path(root)
        receipt=json.loads(trusted_file(root/'qualification.json',65536))
        if not isinstance(receipt,dict) or receipt.get('schema')!=1:return None
        binary=root/'ffprobe-cuda'
        data=trusted_file(binary,64*1024*1024)
        if hashlib.sha256(data).hexdigest()!=receipt.get('binary_sha256'):return None
        if not os.access(binary,os.X_OK):return None
        from encoder_capabilities import nvidia_adapters
        adapters=nvidia_adapters()
        # Until explicit device routing is qualified, never pick an arbitrary
        # device from a multi-GPU host. Other configurations keep CPU inspection.
        if not isinstance(adapters,list) or len(adapters)!=1 or not isinstance(adapters[0],dict):return None
        adapter=adapters[0]
        if receipt.get('adapter')!={k:adapter.get(k) for k in ('uuid','driver')}:
            return None
        if not visibility_matches(receipt.get('visibility'),{k:os.environ.get(k) for k in
                ('CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER')},adapter.get('uuid')):
            return None
        return dict(receipt,binary=str(binary))
    except (OSError,ValueError,TypeError):return None


def select_reader(video,duration,hdr_mode,qualification):
    """Pure planning; CPU fallback is a backend choice, never an input rejection."""
    cpu=dict(backend='cpu',reason='Using the existing complete CPU frame reader')
    if not isinstance(qualification,dict) or not isinstance(video,dict):return cpu
    side_data=video.get('side_data_list',[])
    if isinstance(side_data,list) and any(isinstance(item,dict) and
            any(token in str(item.get('side_data_type','')).lower() for token in ('dovi','dolby')) for item in side_data):
        return dict(cpu,reason='Dolby Vision frame-reader parity is not qualified; complete CPU inspection is retained')
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<60:
        return dict(cpu,reason='CPU reader avoids GPU startup cost for short inputs')
    if hdr_mode not in ('hdr10','hdr10plus','pq','hlg'):return cpu
    scopes=qualification.get('scopes',[])
    if not isinstance(scopes,list):return cpu
    for scope in scopes:
        if not isinstance(scope,dict) or any(scope.get(k) is not True for k in PROOF_FIELDS):continue
        modes=scope.get('hdr_modes',[])
        if not isinstance(modes,list):continue
        if (scope.get('codec')!=video.get('codec_name') or scope.get('pixel_format')!=video.get('pix_fmt')
                or hdr_mode not in modes):continue
        reduction=scope.get('time_reduction_percent')
        if type(reduction) not in (int,float) or not math.isfinite(reduction) or reduction<=0:continue
        binary=qualification.get('binary')
        if not isinstance(binary,str) or not PurePosixPath(binary).is_absolute():continue
        return dict(backend='cuda',binary=binary,
                    reason='Qualified GPU reader; complete frames and all existing checks retained')
    return dict(cpu,reason='No matching GPU reader qualification; continuing with CPU inspection')


def reader_environment():
    return dict(os.environ,MUXMENDER_RESEARCH_CUDA_READER='1')


def hdr_reader_request(cpu,source,video,duration,mode,qualification,decoder_options=(),container=None):
    """One command policy for automatic and preservation frame-reader callers."""
    from decoder_context import hdr_reader_options
    plan=select_reader(video,float(duration),mode,qualification)
    names=set(container.split(',')) if isinstance(container,str) else set()
    if plan['backend']=='cuda' and (not names or not names<=NATIVE_DEMUXERS):
        plan=dict(backend='cpu',reason='This native reader lacks the container reader; complete CPU inspection is retained')
    gpu=plan['backend']=='cuda'
    binary=plan['binary'] if gpu else cpu
    command=[binary,'-v','error',*(['-err_detect','explode'] if gpu else []),
             *hdr_reader_options(duration),'-select_streams','V:0',*decoder_options,str(source)]
    return command,(dict(env=reader_environment()) if gpu else {}),plan
