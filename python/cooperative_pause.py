"""Opt-in Linux stage suspension. Never signal a discovered external process.

Lease files belong in the private work directory, not in media. A supervisor
must refresh requests; expired/malformed requests release the owned worker.
This is not a restart checkpoint and does not release GPU memory.
"""
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
import subprocess

MEDIA_TOOLS = {'ffmpeg', 'ffprobe', 'mkvmerge', 'dovi_tool', 'hdr10plus_tool'}


def launch_owned(command, **kwargs):
    """Arm parent-death cleanup before a child can be suspended (no preexec_fn)."""
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Linux-only media suspension')
    import select
    reader, writer = os.pipe()
    child = None
    try:
        inherited = tuple(kwargs.pop('pass_fds', ()))
        child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).with_name('pause_worker.py')),
                                  str(os.getpid()), str(writer), *map(str, command)],
                                 start_new_session=True, pass_fds=(*inherited, writer), **kwargs)
        os.close(writer)
        writer = None
        if not select.select([reader], [], [], 5)[0] or os.read(reader, 1) != b'R':
            raise RuntimeError('Media suspension safety handshake failed')
        return child
    except BaseException:
        if child is not None:
            child.kill()
            child.wait(timeout=5)
            if child.stdout:child.stdout.close()
        raise
    finally:
        os.close(reader)
        if writer is not None:os.close(writer)


def lease_reason(path, now=None):
    if not path:
        return None
    now = time.time() if now is None else now
    try:
        # Bound control input; no media inspection and no unbounded JSON reads.
        with Path(path).open('r', encoding='utf-8') as stream:
            data = json.loads(stream.read(4097))
        until = data.get('expires_at')
        if (data.get('pause') is True and type(until) in (int, float)
                and math.isfinite(until) and 0 < until-now <= 60):
            return str(data.get('reason') or 'Yielding resources')[:200]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def configured_lease(command, env=None):
    path = (os.environ if env is None else env).get('MUXMENDER_PAUSE_LEASE')
    if not path:
        return None
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Cooperative media pause is supported only on Linux')
    # Do not stop Python orchestration: its nested watchdogs must stay alive.
    if not command or Path(str(command[0])).name not in MEDIA_TOOLS:
        return None
    if not Path(path).is_absolute():
        raise ValueError('Pause lease must use an absolute work-directory path')
    return path


class OwnedStagePause:
    """Only accepts a direct Popen child launched in its own session."""
    def __init__(self, child, path):
        self.child, self.path = child, path
        self.paused = False
        self.started = None
        self.total = 0.0
        self.reason = None

    def _signal(self, value):
        if not sys.platform.startswith('linux'):
            raise RuntimeError('Linux-only process suspension')
        if self.child.poll() is not None:
            return False
        # The live, unreaped direct child owns this isolated group. Never use
        # PIDs from NVIDIA telemetry as signal targets.
        if os.getpgid(self.child.pid) != self.child.pid:
            raise RuntimeError('Refusing to suspend a non-isolated process group')
        try:
            os.killpg(self.child.pid, value)
        except ProcessLookupError:
            return False
        return True

    def update(self):
        reason = lease_reason(self.path)
        if reason and not self.paused and self._signal(signal.SIGSTOP):
            self.paused, self.started = True, time.monotonic()
        elif not reason and self.paused:
            self.resume()
        self.reason = reason if self.paused else None
        return self.paused

    def elapsed(self):
        return self.total + (time.monotonic()-self.started if self.paused else 0)

    def resume(self):
        if self.paused:
            self._signal(signal.SIGCONT)
            self.total += time.monotonic()-self.started
            self.paused, self.started, self.reason = False, None, None
