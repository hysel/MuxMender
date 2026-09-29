"""Cross-process admission for memory-heavy readers, not weaker validation.

The OS releases the lock on process death. Only an explicitly configured shared
work root is used; source folders are never used for lock files.
"""
from contextlib import contextmanager
from functools import wraps
import inspect
import os
from pathlib import Path
import time


def heavy_reader(command):
    return '-show_frames' in command or any(
        word in str(arg) for arg in command for word in ('libvmaf','libplacebo','tonemap'))


@contextmanager
def validation_slot(command,guard=lambda:None,timeout=None):
    root=os.environ.get('MUXMENDER_VALIDATION_LOCK_ROOT')
    if not root or os.name!='posix' or not heavy_reader(command):
        yield
        return
    import fcntl
    from job_tracking import progress
    path=Path(root)
    if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('Unsafe validation lock root')
    path.mkdir(parents=True,exist_ok=True)
    lock=path/'heavy-reader.lock'
    fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    started=time.monotonic();waiting=False
    try:
        while True:
            guard()
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                waiting=True
                elapsed=time.monotonic()-started
                progress('Waiting for validation resources',stage_percent=None,stage_eta=None,
                         detail=f'Waiting {int(elapsed)} seconds for the shared validation slot; execution has not started')
                if timeout is not None and elapsed>=timeout:
                    raise TimeoutError('Timed out waiting for heavy validation resources; retry when the server is less busy')
                time.sleep(1)
        if waiting:progress('Validation resources acquired',detail='Continuing the same checks')
        yield
    finally:
        os.close(fd)


def validation_limited(function):
    signature=inspect.signature(function)
    @wraps(function)
    def wrapped(*args,**kwargs):
        values=signature.bind(*args,**kwargs).arguments
        # The wrapped timeout limits actual processing, not time queued behind
        # another reader. The guard still permits cancellation while waiting.
        with validation_slot(values['command'],values.get('guard') or (lambda:None)):
            return function(*args,**kwargs)
    return wrapped
