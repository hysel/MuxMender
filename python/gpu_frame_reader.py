"""Select an attested native reader without changing any media validation gate.

Release/admin receipts and private app-computed evidence are verified separately;
neither comes from a media file or dashboard request. Unsupported hardware or
scope keeps the CPU reader; a selected reader's decode error is never retried as
a success on another backend.
"""
import hashlib
import json
import math
import os
from pathlib import Path,PurePosixPath
import stat
import sys
import time

READER_ROOT=Path('/opt/muxmender-readers')
HOST_QUALIFICATION_ROOT=Path('/opt/muxmender-host-qualification')
PROOF_FIELDS=('full_eof','every_frame_cpu_gpu_equal','corrupt_controls_rejected')
# Raw HEVC currently emits no decoded frames with this native artifact. Keep
# complete CPU reads there even when a containerized HEVC scope is attested.
NATIVE_DEMUXERS=frozenset(('matroska','webm','mov','mp4','m4a','3gp','3g2','mj2','mpegts','obu'))


class QualificationAvailable(Exception):
    """Replan a queued reader before it has opened any output or media process."""
    def __init__(self,profile):
        super().__init__('A matching GPU reader was verified while this stage waited')
        self.profile=profile


def qualification_stamp(storage):
    try:return sorted((p.name,p.stat().st_mtime_ns,p.stat().st_size)
                      for p in Path(storage).glob('*.json'))
    except OSError:return []


def qualification_wait_guard(storage,guard,can_use,*,initial_stamp=None):
    """Observe new app proofs only during admission, never interrupt a reader."""
    previous=qualification_stamp(storage) if initial_stamp is None else initial_stamp
    checked=-float('inf')
    def check():
        nonlocal previous,checked
        guard()
        now=time.monotonic()
        if now-checked<5:return
        checked=now;current=qualification_stamp(storage)
        if current==previous:return
        previous=current
        profile=load_qualification(app_storage=storage)
        if profile is not None and can_use(profile):raise QualificationAvailable(profile)
    return check


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


def load_qualification(root=READER_ROOT,qualification_root=None,diagnostics=None,app_storage=None):
    """Reuse host evidence across updates only when the shipped binary still matches.

    The optional host mount is administrator-owned and read-only in the app;
    it is never loaded from writable output/media or selected by a web request.
    App-owned, complete comparison evidence is loaded from private persistent
    state as well. Administrator mounts are a compatibility path, not required.
    """
    if not sys.platform.startswith('linux'):return None
    roots=[Path(qualification_root)] if qualification_root is not None else [Path(root),HOST_QUALIFICATION_ROOT]
    profiles=[]
    for receipt_root in roots:
        result=_load_qualification(Path(root),receipt_root,diagnostics)
        if result is not None:profiles.append(result)
    if qualification_root is None:
        from reader_qualification_cache import load_profile
        cached=load_profile(root,app_storage)
        if cached is not None:profiles.append(cached)
    return merge_qualifications(profiles)


def merge_qualifications(profiles):
    if not profiles:return None
    result=dict(profiles[0],scopes=list(profiles[0].get('scopes',[])))
    for profile in profiles[1:]:
        if any(profile.get(k)!=result.get(k) for k in ('binary','binary_sha256','adapter')):continue
        for scope in profile.get('scopes',[]):
            if scope not in result['scopes']:result['scopes'].append(scope)
    return result


def _load_qualification(root,receipt_root,diagnostics=None):
    try:
        receipt=json.loads(trusted_file(receipt_root/'qualification.json',65536))
        if not isinstance(receipt,dict) or receipt.get('schema')!=1:return None
        from reader_qualification_cache import POLICY_VERSION
        # Older administrator receipts belong to the original policy. A future
        # policy change must not silently bypass fresh automatic checks.
        policy=receipt.get('reader_policy',1)
        if type(policy) is not int or policy!=POLICY_VERSION:return None
        binary=root/'ffprobe-cuda'
        data=trusted_file(binary,64*1024*1024)
        digest=hashlib.sha256(data).hexdigest()
        if digest!=receipt.get('binary_sha256'):
            if diagnostics is not None:
                diagnostics.append(dict(code='reader_build_changed',reason=
                    'The GPU reader was updated. The app will use a complete CPU reference for automatic compatibility checks.'))
            return None
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


def select_reader(video,duration,hdr_mode,qualification,*,container=None):
    """Pure planning; CPU fallback is a backend choice, never an input rejection."""
    cpu=dict(backend='cpu',reason='Using complete CPU inspection; supported GPU paths are checked automatically')
    if not isinstance(qualification,dict) or not isinstance(video,dict):return cpu
    side_data=video.get('side_data_list',[])
    if isinstance(side_data,list) and any(isinstance(item,dict) and
            any(token in str(item.get('side_data_type','')).lower() for token in ('dovi','dolby')) for item in side_data):
        return dict(cpu,reason='Dolby Vision frame-reader parity is not qualified; complete CPU inspection is retained')
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<60:
        return dict(cpu,reason='CPU reader avoids GPU startup cost for short inputs')
    if hdr_mode not in ('sdr','hdr10','hdr10plus','pq','hlg'):return cpu
    scopes=qualification.get('scopes',[])
    if not isinstance(scopes,list):return cpu
    for scope in scopes:
        if not isinstance(scope,dict) or any(scope.get(k) is not True for k in PROOF_FIELDS):continue
        modes=scope.get('hdr_modes',[])
        if not isinstance(modes,list):continue
        if (scope.get('codec')!=video.get('codec_name') or scope.get('pixel_format')!=video.get('pix_fmt')
                or hdr_mode not in modes):continue
        if container is not None and scope.get('containers') is not None:
            names=set(container.split(',')) if isinstance(container,str) else set()
            covered=scope['containers']
            if (not names or not isinstance(covered,list) or not all(isinstance(n,str) for n in covered)
                    or not names<=set(covered)):continue
        reduction=scope.get('time_reduction_percent')
        if type(reduction) not in (int,float) or not math.isfinite(reduction) or reduction<=0:continue
        binary=qualification.get('binary')
        if not isinstance(binary,str) or not PurePosixPath(binary).is_absolute():continue
        return dict(backend='cuda',binary=binary,containers=scope.get('containers'),
                    reason='Qualified GPU reader; complete frames and all existing checks retained')
    return dict(cpu,reason='No matching GPU reader qualification; continuing with CPU inspection')


def reader_environment():
    return dict(os.environ,MUXMENDER_RESEARCH_CUDA_READER='1')


def reader_label(plan,diagnostics=()):
    if plan['backend']=='cuda':return 'GPU reader'
    if any(item.get('code')=='reader_build_changed' for item in diagnostics):
        return 'CPU reader (automatic GPU setup)'
    return 'CPU reader'


SDR_FRAME_FIELDS='pts_time,best_effort_timestamp_time,width,height,pix_fmt,sample_aspect_ratio,interlaced_frame,top_field_first,repeat_pict,color_primaries,color_transfer,color_space,color_range'


def sdr_reader_request(cpu,source,video,duration,qualification,threads=2,decoder_options=(),container=None):
    """Complete SDR inspection with exactly the existing fields and output syntax."""
    plan=select_reader(video,float(duration),'sdr',qualification,container=container)
    names=set(container.split(',')) if isinstance(container,str) else set()
    if plan['backend']=='cuda' and (not names or not names<=NATIVE_DEMUXERS):
        plan=dict(backend='cpu',reason='This native reader lacks the container reader; complete CPU inspection is retained')
    if plan['backend']=='cuda' and plan.get('containers') is not None:
        qualified=plan['containers']
        if not isinstance(qualified,list) or not all(isinstance(item,str) for item in qualified) or not names<=set(qualified):
            plan=dict(backend='cpu',reason='This container has no matching SDR frame-reader evidence; complete CPU inspection is retained')
    gpu=plan['backend']=='cuda'
    # Match the qualified native decoder scheduling: retain strict errors in
    # one frame context rather than relying on asynchronous frame threading.
    command=[plan['binary'] if gpu else cpu,'-v','error',*(['-err_detect','explode'] if gpu else []),
             '-threads',str(threads),*(['-thread_type','slice'] if gpu else []),'-select_streams','V:0','-show_frames',
             '-show_entries','frame='+SDR_FRAME_FIELDS,'-of','compact=p=0',*decoder_options,str(source)]
    return command,(dict(env=reader_environment()) if gpu else {}),plan


def hdr_reader_request(cpu,source,video,duration,mode,qualification,decoder_options=(),container=None):
    """One command policy for automatic and preservation frame-reader callers."""
    from decoder_context import hdr_reader_options
    plan=select_reader(video,float(duration),mode,qualification,container=container)
    names=set(container.split(',')) if isinstance(container,str) else set()
    if plan['backend']=='cuda' and (not names or not names<=NATIVE_DEMUXERS):
        plan=dict(backend='cpu',reason='This native reader lacks the container reader; complete CPU inspection is retained')
    gpu=plan['backend']=='cuda'
    binary=plan['binary'] if gpu else cpu
    command=[binary,'-v','error',*(['-err_detect','explode'] if gpu else []),
             *hdr_reader_options(duration),'-select_streams','V:0',*decoder_options,str(source)]
    return command,(dict(env=reader_environment()) if gpu else {}),plan
