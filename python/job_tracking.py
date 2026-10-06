"""Persistent, local job records. Never reads or changes media files."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
import traceback
from contextlib import contextmanager
from app_version import VERSION
from performance import accumulate

_active = None
_thread_progress=threading.local()


@contextmanager
def isolated_progress(observer):
    """Let a parent report parallel work without competing stage updates."""
    previous=getattr(_thread_progress,'observer',None)
    previous_phase=getattr(_thread_progress,'phase',None)
    _thread_progress.observer=observer;_thread_progress.phase=None
    try:yield
    finally:
        _thread_progress.observer=previous;_thread_progress.phase=previous_phase


def local_progress(values):
    observer=getattr(_thread_progress,'observer',None)
    if observer is None:return False
    if 'phase' in values:_thread_progress.phase=values['phase']
    observer(values)
    return True


class Job:
    def __init__(self, folder, title):
        self.directory = Path(folder) / ('job-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        self.directory.mkdir(parents=True, exist_ok=False)
        self.lock = threading.Lock()
        self.last_timing = time.monotonic()
        self.data = dict(title=title, state='running', pid=os.getpid(), started=time.time(),
                         phase='Starting task', stage_started=time.time(), app_version=VERSION,
                         performance_seconds={}, performance_schema=3,
                         performance_scope='Observed job wall time; resource admission and native-stage GPU-sharing pauses are separate. Not CPU time.')
        self.save()

    def save(self, **changes):
        with self.lock:
            now=time.monotonic()
            if self.data.get('state')=='running':
                accumulate(self.data['performance_seconds'], self.data.get('phase',''), now-self.last_timing,
                           self.data.get('performance_category'))
            self.last_timing=now
            if 'phase' in changes and changes['phase'] != self.data.get('phase'):
                changes['stage_started']=time.time()
                # Legacy phase updates must not inherit the previous step's
                # 100%/ETA/detail while new evidence is still being collected.
                for field in ('stage_percent','stage_eta','stage_updated','detail'):
                    changes.setdefault(field,None)
            self.data.update(changes, updated=time.time())
            temporary = self.directory / 'job.json.tmp'
            temporary.write_text(json.dumps(self.data), encoding='utf-8')
            temporary.replace(self.directory / 'job.json')


def phase(directory, label, percent):
    if local_progress(dict(phase=label,percent=percent)):return
    if _active:
        try:
            _active.save(linked_run=str(Path(directory).resolve()), phase=label, percent=percent,
                         progress_kind='legacy')
        except OSError:
            pass  # Monitoring must not fail an encode.


def progress(label, completed=0, total=None, stage_percent=None, stage_eta=None,
             directory=None, detail=None, unit='steps', **changes):
    """Explicit overall work count and independent current-stage progress."""
    if local_progress(dict(phase=label,stage_percent=stage_percent,detail=detail,**changes)):return
    if not _active:
        return
    values = dict(progress_kind='structured', phase=label, completed=completed,
                  total=total, unit=unit, stage_percent=stage_percent,
                  stage_eta=stage_eta, detail=detail,
                  stage_updated=time.time() if stage_percent is not None else None,
                  eta_scope='Current stage only; later muxing/verification time is not included',
                  percent=100 * completed / total if total else None)
    if directory:
        values['linked_run'] = str(Path(directory).resolve())
    values.update(changes)
    try:
        _active.save(**values)
    except OSError:
        pass


def stage_progress(percent, eta, detail=None):
    """Update current-stage telemetry without resetting completed-work progress."""
    if local_progress(dict(stage_percent=percent,stage_eta=eta,detail=detail)):return
    if _active:
        try:
            values=dict(stage_percent=percent, stage_eta=eta, stage_updated=time.time(),
                        eta_scope='Current stage only; later muxing/verification time is not included')
            if detail is not None:values['detail']=detail
            _active.save(**values)
        except OSError:
            pass


def workflow_stage(name):
    """Stable top-level stage, independent of repeatable check percentages."""
    if name not in ('inspect','compare','encode','validate','publish','cleanup'):
        raise ValueError('Unknown workflow stage')
    if _active:
        try:_active.save(workflow_stage=name,stage_percent=None,stage_eta=None)
        except OSError:pass


@contextmanager
def measured_operation(category):
    """Explicit, non-overlapping elapsed time; phase labels remain presentation."""
    if category not in ('validation_wait','gpu_wait','gpu_pause','publication_wait','publication',
                        'frame_validation','quality_measurement','encoding'):
        raise ValueError('Unknown measured operation')
    if getattr(_thread_progress,'observer',None) is not None:
        yield
        return
    job=_active
    previous=job.data.get('performance_category') if job else None
    try:
        if job:
            try:job.save(performance_category=category)
            except OSError:pass
        yield
    finally:
        if job:
            try:job.save(performance_category=previous)
            except OSError:pass


def current_phase():
    if getattr(_thread_progress,'observer',None) is not None:return getattr(_thread_progress,'phase',None)
    return _active.data.get('phase') if _active else None


def current_workflow_stage():
    return _active.data.get('workflow_stage') if _active else None


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
    except Exception as exc:
        try:
            job.save(error=str(exc),detail=str(exc))
        except OSError:
            pass  # A report-write failure must not hide the processing error.
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
