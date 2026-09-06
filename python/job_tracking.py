"""Persistent, local job records. Never reads or changes media files."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
import traceback

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
            _active.save(linked_run=str(Path(directory).resolve()), phase=label, percent=percent,
                         progress_kind='legacy')
        except OSError:
            pass  # Monitoring must not fail an encode.


def progress(label, completed=0, total=None, stage_percent=None, stage_eta=None,
             directory=None, detail=None, unit='steps', **changes):
    """Explicit overall work count and independent current-stage progress."""
    if not _active:
        return
    values = dict(progress_kind='structured', phase=label, completed=completed,
                  total=total, unit=unit, stage_percent=stage_percent,
                  stage_eta=stage_eta, detail=detail,
                  percent=100 * completed / total if total else None)
    if directory:
        values['linked_run'] = str(Path(directory).resolve())
    values.update(changes)
    try:
        _active.save(**values)
    except OSError:
        pass


def tracked_call(function, title, folder=None):
    """Wrap a CLI invocation, preserving stdout and stderr and its exit status."""
    global _active
    if _active:
        return function()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    from run_logged import Tee
    try:
        job = Job(folder or Path(__file__).resolve().parent.parent / 'reports', title)
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
    except Exception:
        traceback.print_exc()
        raise
    finally:
        stop.set()
        worker.join(timeout=6)
        sys.stdout, sys.stderr = original
        log.close()
        try:
            state = 'completed' if code == 0 else 'cancelled' if code == 130 else 'failed'
            if code == 1 and job.data.get('completion_state') == 'completed-with-errors':
                state = 'completed-with-errors'
            job.save(state=state,
                     exit_code=code, finished=time.time())
        except OSError as exc:
            print(f'Dashboard final status unavailable: {exc}', file=sys.stderr)
        _active = None
