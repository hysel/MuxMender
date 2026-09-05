"""Persistent, local job records. Never reads or changes media files."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

_active = None


class Job:
    def __init__(self, folder, title):
        self.directory = Path(folder) / ('job-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        self.directory.mkdir(parents=True, exist_ok=False)
        self.lock = threading.Lock()
        self.data = dict(title=title, state='running', pid=os.getpid(), started=time.time())
        self.save()

    def save(self, **changes):
        with self.lock:
            self.data.update(changes, updated=time.time())
            temporary = self.directory / 'job.json.tmp'
            temporary.write_text(json.dumps(self.data), encoding='utf-8')
            temporary.replace(self.directory / 'job.json')


def phase(directory, label, percent):
    if _active:
        try:
            _active.save(linked_run=str(Path(directory).resolve()), phase=label, percent=percent)
        except OSError:
            pass  # Monitoring must not fail an encode.


def tracked_call(function, title, folder=None):
    """Wrap a CLI invocation, preserving stdout and stderr and its exit status."""
    global _active
    if _active:
        return function()
    from run_logged import Tee
    try:
        job = Job(folder or Path(__file__).resolve().parent / 'reports', title)
        log = (job.directory / 'terminal.log').open('x', encoding='utf-8')
    except OSError as exc:
        print(f'Dashboard logging unavailable: {exc}', file=sys.stderr)
        return function()
    _active = job
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(5):
            try:
                job.save()
            except OSError:
                pass
    worker = threading.Thread(target=heartbeat, daemon=True)
    original = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = Tee(original[0], log), Tee(original[1], log)
    worker.start()
    code = 1
    try:
        print(f'Dashboard job: {job.directory}', flush=True)
        code = function() or 0
        return code
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        raise
    except KeyboardInterrupt:
        code = 130
        raise
    finally:
        stop.set()
        worker.join(timeout=6)
        sys.stdout, sys.stderr = original
        log.close()
        try:
            job.save(state='completed' if code == 0 else 'cancelled' if code == 130 else 'failed',
                     exit_code=code, finished=time.time())
        except OSError as exc:
            print(f'Dashboard final status unavailable: {exc}', file=sys.stderr)
        _active = None
