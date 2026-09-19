"""Opt-in serial safe-copy queue. Never writes media or replaces originals."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

SCOPE = Path('TV/Series/Season 1')
EXTENSIONS = {'.mkv', '.mp4', '.m4v', '.avi', '.ts', '.mov'}


def read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


def write(path, value):
    # Unique staging avoids collisions; fsync makes replacement journals/queue
    # receipts durable before subsequent destructive publication operations.
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2)
            handle.flush();os.fsync(handle.fileno())
        temporary.replace(path)
        if os.name=='posix':
            descriptor=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def signature(path):
    s = path.stat()
    return [s.st_size, s.st_mtime_ns]


def command(source, output, codecs):
    return [sys.executable, '-B', '-m', 'auto_optimize', str(source),
            '--output-dir', str(output), '--hardware', 'auto',
            '--playback-verified-codecs', *codecs, '--execute', '--encode-best',
            '--min-free-gib', '12']


def outcome(folder, returncode):
    states = list(folder.glob('auto-*/status.json'))
    if returncode or len(states) != 1:
        return 'failed', 'Worker failed or did not produce exactly one result'
    status = read(states[0])
    if status.get('state') == 'validated-copy-awaiting-playback':
        return 'awaiting-playback', 'Validated copy; original retained; replacement requires approval'
    if status.get('state') == 'trials-completed' and status.get('decision', {}).get('action') == 'keep_original':
        return 'skipped', status['decision'].get('reason', 'No eligible smaller copy')
    if status.get('state') == 'full-output-rejected-insufficient-savings':
        return 'skipped', 'Full output did not meet savings requirement'
    return 'failed', status.get('error', 'Unrecognized worker outcome')


class Queue:
    def __init__(self, media, output, codecs, readonly, busy=lambda: False):
        self.media, self.output = media.resolve(strict=True), output.resolve(strict=True)
        self.scope = (self.media / SCOPE).resolve(strict=True)
        if not self.scope.is_dir() or not self.scope.is_relative_to(self.media):
            raise ValueError('Approved season scope must be inside media')
        if self.media == self.output or self.media in self.output.parents or self.output in self.media.parents:
            raise ValueError('Separate output required')
        if not codecs or any(c not in ('hevc', 'av1') for c in codecs):
            raise ValueError('Declare playback-verified codecs')
        if not readonly(self.media):
            raise ValueError('Queue requires read-only media mount')
        self.readonly, self.codecs = readonly, codecs
        self.busy = busy
        self.root = self.output / 'autonomy'
        self.root.mkdir(exist_ok=True)
        self.file = self.root / 'queue.json'
        self.pause = self.root / 'PAUSE'
        self.stop_event = threading.Event()
        self.child = None
        self.thread = None
        self.lock = None
        self.state = dict(state='starting', scope=str(self.scope), entries={}, failures=0)

    def save(self, state=None, detail=None):
        if state is not None: self.state['state'] = state
        if detail is not None: self.state['detail'] = detail
        self.state['updated'] = time.time()
        write(self.file, self.state)

    def snapshot(self):
        return read(self.file) or self.state

    def history(self):
        """Reuse only terminal, content-hashed outcomes from this approved scope."""
        known = {}
        for file in self.output.rglob('status.json'):
            if self.root in file.parents: continue
            try:
                status = read(file)
                source = Path(status.get('source', '')).resolve()
                if not source.is_relative_to(self.scope): continue
                state = status.get('state')
                eligible = state == 'validated-copy-awaiting-playback' or (
                    state == 'trials-completed' and status.get('decision', {}).get('action') == 'keep_original')
                if not eligible: continue
                digest = status.get('source_sha256') or read(file.parent / 'trials.json').get('source_id')
                if digest: known[digest] = str(file)
                if state == 'validated-copy-awaiting-playback' and status.get('output_sha256'):
                    known[status['output_sha256']] = str(file)
            except (OSError, ValueError, TypeError):
                continue
        for entry in self.state['entries'].values():
            if entry.get('sha256') and entry.get('state') in ('skipped', 'awaiting-playback', 'previously-processed'):
                known[entry['sha256']] = entry.get('output', 'queue history')
        return known

    def files(self):
        for path in sorted(self.scope.rglob('*')):
            if path.suffix.lower() not in EXTENSIONS or not path.is_file(): continue
            resolved = path.resolve(strict=True)
            if path.is_symlink() or not resolved.is_relative_to(self.scope): continue
            yield resolved

    def digest(self, source):
        digest = hashlib.sha256()
        total, done, updated = source.stat().st_size, 0, time.monotonic()
        with source.open('rb') as stream:
            while block := stream.read(4 * 1024 * 1024):
                if self.stop_event.is_set(): raise InterruptedError('Queue stopping')
                digest.update(block)
                done += len(block)
                if time.monotonic() - updated >= 5:
                    self.save('scanning', f'Checking content history: {source.name} ({100*done/max(1,total):.0f}%)')
                    updated = time.monotonic()
        return digest.hexdigest()

    def step(self):
        if self.pause.exists():
            self.save('paused', 'PAUSE marker present; no new work starts')
            return
        if not self.readonly(self.media): raise RuntimeError('Media is no longer mounted read-only')
        if self.busy():
            self.save('waiting', 'Another tracked job is active; waiting before starting queue work')
            return
        if shutil.disk_usage(self.output).free < 12 * 1024**3:
            self.save('paused-low-space', 'Waiting for at least 12 GiB free')
            return
        known = self.history()
        for source in self.files():
            if self.stop_event.is_set() or self.pause.exists(): return
            key = str(source.relative_to(self.scope))
            before = signature(source)
            previous = self.state['entries'].get(key)
            if previous and previous.get('signature') == before: continue
            entry = dict(source=str(source), signature=before, state='hashing')
            self.state['entries'][key] = entry
            self.save('scanning', 'Checking content history: ' + source.name)
            sha = self.digest(source)
            if signature(source) != before: raise RuntimeError('Source changed during scan')
            entry['sha256'] = sha
            if sha in known:
                entry.update(state='previously-processed', reason='Unchanged content already evaluated', report=known[sha])
                self.save()
                continue
            # Reserve ample room for a full output plus trials; the worker also
            # enforces its free-space guard throughout encoding and validation.
            if shutil.disk_usage(self.output).free < max(12 * 1024**3, before[0] * 3):
                del self.state['entries'][key]
                self.save('paused-low-space', 'Insufficient reserve for ' + source.name)
                return
            # Pause/stop may have arrived while hashing a large source.
            if self.stop_event.is_set() or self.pause.exists() or self.busy():
                del self.state['entries'][key]
                self.save('paused', 'No worker started')
                return
            folder = self.root / ('item-' + uuid.uuid4().hex)
            folder.mkdir()
            entry.update(state='running', output=str(folder), started=time.time())
            self.save('processing', source.name)
            with (folder / 'worker.log').open('xb') as log:
                self.child = subprocess.Popen(command(source, folder, self.codecs), stdout=log,
                                              stderr=subprocess.STDOUT, start_new_session=True)
                code = self.child.wait()
                self.child = None
            state, reason = outcome(folder, code)
            entry.update(state=state, reason=reason, finished=time.time())
            self.state['failures'] = self.state.get('failures', 0) + 1 if state == 'failed' else 0
            if self.state['failures'] >= 2:
                self.pause.touch(exist_ok=True)
            self.save('idle', 'Last result: ' + reason)
            return  # One worker per tick, never parallel.
        self.save('idle', 'Scan complete; waiting for new or changed media')

    def loop(self):
        try:
            import fcntl
            self.lock = (self.root / 'queue.lock').open('a')
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.state = read(self.file) or self.state
            for entry in self.state['entries'].values():
                if entry.get('state') in ('running', 'hashing'):
                    entry.update(state='interrupted', reason='Manual review required after restart; not retried automatically')
                    self.pause.touch(exist_ok=True)
            self.save('starting', 'Recovering durable queue')
            while not self.stop_event.is_set():
                self.step()
                self.stop_event.wait(30)
        except BlockingIOError:
            # Do not overwrite another worker's state file.
            print('Queue lock held: another queue owns this output', flush=True)
        except Exception as exc:
            self.pause.touch(exist_ok=True)
            self.save('paused-error', str(exc))
        finally:
            if self.lock is not None: self.lock.close()

    def start(self):
        self.thread = threading.Thread(target=self.loop, name='muxmender-queue', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        child = self.child
        if child is not None and child.poll() is None:
            try: os.killpg(child.pid, signal.SIGINT)
            except ProcessLookupError: pass
            try: child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
        if self.thread is not None: self.thread.join(timeout=20)
