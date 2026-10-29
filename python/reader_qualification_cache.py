"""Private, app-owned reader evidence; never trust a receipt from media or the UI."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid
import re
import shutil

POLICY_VERSION=1
MAXIMUM_PAIRS=32


def cache_root(output_root=None):
    account=os.geteuid() if callable(getattr(os,'geteuid',None)) else 'unsupported'
    return Path(output_root if output_root is not None else os.environ.get('MUXMENDER_OUTPUT_ROOT','/output'))/('.reader-qualification-'+str(account))


def identity(reader_root):
    if not sys.platform.startswith('linux') or not callable(getattr(os,'geteuid',None)):return None
    from gpu_frame_reader import trusted_file
    from encoder_capabilities import nvidia_adapters
    binary=Path(reader_root)/'ffprobe-cuda'
    try:
        data=trusted_file(binary,64*1024*1024)
        if not data.startswith(b'\x7fELF') or not os.access(binary,os.X_OK):return None
        adapters=nvidia_adapters()
        if len(adapters)!=1:return None
        adapter={k:adapters[0][k] for k in ('uuid','driver')}
        if any(not isinstance(v,str) or not v for v in adapter.values()):return None
        binding=dict(binary_sha256=hashlib.sha256(data).hexdigest(),adapter=adapter,
            visibility={k:os.environ.get(k) for k in ('CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER')})
        cpu=shutil.which('ffprobe')
        if cpu is None:return None
        cpu_data=trusted_file(Path(cpu),128*1024*1024)
        if not cpu_data.startswith(b'\x7fELF'):return None
        cpu_digest=hashlib.sha256(cpu_data).hexdigest()
        key=hashlib.sha256(json.dumps(dict(binding,policy=POLICY_VERSION,cpu_reader_sha256=cpu_digest),sort_keys=True).encode()).hexdigest()
        return dict(binding=binding,key=key,binary=str(binary),data=data,cpu_binary=cpu,cpu_sha256=cpu_digest)
    except (OSError,ValueError,KeyError,TypeError):return None


def private_descriptor(root,create=False):
    root=Path(root)
    if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('Linked GPU cache')
    if create:
        try:root.mkdir(mode=0o700)
        except FileExistsError:pass
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    info=os.fstat(fd)
    if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700:
        os.close(fd);raise ValueError('GPU cache must be private to the app account')
    return fd


def read_record(root,key):
    if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('Invalid GPU cache key')
    fd=private_descriptor(root)
    try:
        handle=os.open(key+'.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(handle,'rb') as stream:
            info=os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or
                    stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size>2*1024*1024):
                raise ValueError('Untrusted GPU cache record')
            try:value=json.loads(stream.read(2*1024*1024+1))
            except RecursionError as exc:raise ValueError('GPU cache nesting exceeds its budget') from exc
            if not isinstance(value,dict) or value.get('binding_key')!=key:raise ValueError('GPU cache binding mismatch')
            return value
    finally:os.close(fd)


def write_record(root,key,value):
    if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('Invalid GPU cache key')
    data=json.dumps(dict(value,binding_key=key),sort_keys=True).encode()
    if len(data)>2*1024*1024:raise ValueError('GPU cache exceeds evidence budget')
    fd=private_descriptor(root,True);temporary='.'+uuid.uuid4().hex+'.tmp'
    try:
        handle=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        with os.fdopen(handle,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.rename(temporary,key+'.json',src_dir_fd=fd,dst_dir_fd=fd)
        os.fsync(fd)
        older=[]
        for name in os.listdir(fd):
            if name==key+'.json' or not re.fullmatch(r'[0-9a-f]{64}\.json',name):continue
            info=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if (stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and
                    stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1):older.append((info.st_mtime_ns,name))
        for _,name in sorted(older,reverse=True)[2:]:os.unlink(name,dir_fd=fd)
    finally:
        try:os.unlink(temporary,dir_fd=fd)
        except FileNotFoundError:pass
        os.close(fd)


@contextmanager
def exclusive_check(root):
    """Do not queue several copies of a long first-use check."""
    import fcntl
    fd=private_descriptor(root,True);lock=None
    try:
        lock=os.open('check.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=fd)
        info=os.fstat(lock)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or
                stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):raise ValueError('Untrusted GPU cache lock')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:yield False
        else:yield True
    finally:
        if lock is not None:os.close(lock)
        os.close(fd)


def verified_profile(context,record):
    from host_reader_qualification import verified_receipt
    if not isinstance(record,dict) or not isinstance(record.get('receipt'),dict):raise ValueError('Incomplete GPU evidence record')
    receipt=record.get('receipt',{})
    if any(receipt.get(k)!=v for k,v in context['binding'].items()):raise ValueError('GPU cache hardware/build mismatch')
    try:checked=json.loads(verified_receipt(receipt,record.get('evidence'),context['data'],maximum_pairs=MAXIMUM_PAIRS))
    except ValueError:raise
    except Exception as exc:raise ValueError('Malformed GPU comparison evidence') from exc
    return dict(checked,binary=context['binary'])


def load_profile(reader_root,root=None):
    root=cache_root() if root is None else Path(root)
    try:
        if not root.exists():return None
    except OSError:return None
    context=identity(reader_root)
    if context is None:return None
    try:return verified_profile(context,read_record(root,context['key']))
    except (OSError,ValueError,TypeError,KeyError):return None
