"""Read-only localhost dashboard for MuxMender. Python standard library only."""
import argparse
import ctypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlparse, parse_qs


def read_json(path):
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def tail(path, limit=65536):
    try:
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - limit))
            return stream.read(limit).decode('utf-8', errors='replace')
    except OSError:
        return ''


def alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == 'nt':
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x1000, False, pid)
        if not handle:
            return None if ctypes.get_last_error() == 5 else False
        try:
            code = wintypes.DWORD()
            return code.value == 259 if api.GetExitCodeProcess(handle, ctypes.byref(code)) else None
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return None


def progress(log):
    matches = re.findall(r'MUXMENDER_PROGRESS=(\d+(?:\.\d+)?)', log)
    bars = re.findall(r'([^\r\n]+?)\s+\[[= ]+\]\s*([\d.]+)%\s*\| elapsed (\d+)s \| ETA (\d+)s', log)
    result = {}
    if matches:
        result['percent'] = min(100, float(matches[-1]))
    if bars:
        label, percent, elapsed, eta = bars[-1]
        result.update(progress_label=label.strip(), stage_percent=float(percent), stage_eta=int(eta))
    return result


def contained(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def latest_outcome(directory,root):
    """Read append-only validation/review records; never rewrite execution history."""
    candidates=[]
    for path in [directory/'validation.json',*directory.glob('revalidation-*.json')]:
        if not contained(path,root):continue
        report=read_json(path)
        if report:
            stamp=report.get('finished',path.stat().st_mtime)
            if isinstance(stamp,(int,float)):
                candidates.append((stamp,path.name,report))
    if not candidates:return {},False
    _,name,report=max(candidates,key=lambda item:(item[0],item[1]))
    review=read_json(directory/'playback-review.json') if contained(directory/'playback-review.json',root) else {}
    approved=(review.get('approved') is True and review.get('validation_report')==name
              and str(report.get('status','')).startswith('verified'))
    return report,approved


def apply_outcome(data,directory,root):
    if data.get('state') in ('running','queued','cancelling'):return data
    report,approved=latest_outcome(directory,root)
    if not report:return data
    data=dict(data)
    initial=read_json(directory/'job.json')
    data['execution_state']=initial.get('state')
    data['execution_error']=initial.get('error')
    data['result']=report
    data['state']='playback-approved' if approved else ('verified' if str(report.get('status','')).startswith('verified') else report.get('status',data.get('state')))
    data['phase']='Playback approved' if approved else report.get('status',data.get('phase'))
    data['error']=report.get('error')
    output=report.get('output')
    if output:
        target=Path(output)
        if not target.is_absolute():target=root/target
        missing=contained(target,root) and not target.is_file()
        data['output_state']='Not present (historical result retained)' if missing else 'Available' if contained(target,root) else 'Outside project (not checked)'
        if missing:data['phase']+=' · output removed/not present'
    if data['execution_error'] and not data.get('error'):
        data['error']='Earlier execution: '+str(data['execution_error'])+' (retained history; latest validation passed)'
    if approved or data['state']=='verified':data['percent']=100
    data['awaiting_playback']=not approved and 'awaiting' in str(report.get('status'))
    return data


class Catalog:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.Lock()
        self.cached_at = 0
        self.jobs = []
        self.logs = {}

    def read(self, path):
        return read_json(path) if contained(path, self.root) else {}

    def snapshot(self):
        with self.lock:
            if time.time() - self.cached_at < 3:
                return self.jobs
            directories = set()
            # Only known artifact roots; never enumerate source drives or media contents.
            for name in ('reports', 'test-output'):
                base = self.root / name
                if not base.is_dir() or not contained(base, self.root):
                    continue
                for parent, children, files in os.walk(base, followlinks=False):
                    children[:] = [c for c in children if contained(Path(parent)/c, base)
                                   and not (Path(parent)/c).is_symlink()]
                    if {'job.json', 'status.json', 'validation.json'} & set(files):
                        directories.add(Path(parent))
            records = [(d, self.read(d/'job.json')) for d in directories]
            linked = {str(Path(j['linked_run']).resolve()) for _, j in records if j.get('linked_run')}
            jobs, logs = [], {}
            for directory, job in records:
                if not job and any(contained(directory, Path(parent)) for parent in linked):
                    continue
                run = Path(job.get('linked_run', directory))
                if not contained(run, self.root):
                    run = directory
                status = self.read(run/'status.json')
                report, _ = latest_outcome(run,self.root)
                publication = self.read(run/'publication.json')
                logpath = directory/'terminal.log'
                if not logpath.is_file():
                    logpath = run/'terminal.log'
                log = tail(logpath) if contained(logpath, self.root) else ''
                stamps = [p.stat().st_mtime for p in (run/'status.json', run/'validation.json', logpath)
                          if p.is_file() and contained(p, self.root)]
                updated = max(stamps + [job.get('updated', 0)])
                phase = report.get('status') or status.get('phase') or job.get('phase') or 'Starting'
                if report.get('status') == 'running' and job.get('progress_kind') == 'structured':
                    phase = job.get('phase') or 'Preparing validation'
                state = job.get('state', 'unknown')
                structured = job.get('progress_kind') == 'structured'
                if str(phase).startswith('verified'):
                    state = 'verified'
                elif str(phase).lower() in ('failed', 'cancelled'):
                    state = str(phase).lower()
                elif phase == 'skipped':
                    state = 'skipped'
                elif state == 'running' or (not job and status.get('pid')):
                    running = alive(job.get('pid', status.get('pid')))
                    state = 'interrupted' if running is False else 'running' if running and time.time()-updated < 90 else 'stale'
                parsed = progress(log)
                if (run/'status.json').is_file() and logpath.is_file() and (run/'status.json').stat().st_mtime > logpath.stat().st_mtime:
                    parsed = {}  # The log may still contain the previous stage's 100%/ETA.
                percent = parsed.get('percent', status.get('percent', job.get('percent')))
                if structured:
                    percent = job.get('percent')
                if state in ('verified', 'completed', 'skipped'):
                    percent = 100
                if phase == 'Starting':
                    phase = parsed.get('progress_label') if state == 'running' else state.capitalize()
                    phase = phase or 'Starting'
                started = job.get('started')
                if not started:
                    match = re.search(r'(20\d{6})-(\d{6})', directory.name)
                    if match:
                        try:
                            started = time.mktime(time.strptime(''.join(match.groups()), '%Y%m%d%H%M%S'))
                        except ValueError:
                            pass
                output = report.get('output')
                output_state = 'Not yet reported'
                if output:
                    target = Path(output)
                    if not target.is_absolute():
                        target = self.root/target
                    output_state = ('Available' if target.is_file() else 'Not present (historical result retained)') if contained(target,self.root) else 'Outside project (not checked)'
                identifier = hashlib.sha256(str(directory).encode()).hexdigest()[:20]
                if log and contained(logpath, self.root):
                    logs[identifier] = logpath
                title = job.get('title') or ('Full Dolby Vision preservation' if directory.name.startswith('dv-full-') else report.get('scope')) or directory.name
                jobs.append(apply_outcome(dict(id=identifier, title=title,
                    directory=str(directory.relative_to(self.root)), state=state, phase=phase, percent=percent,
                    stage_eta=(job.get('stage_eta') if structured else parsed.get('stage_eta')) if state == 'running' else None,
                    stage_percent=job.get('stage_percent') if structured else parsed.get('stage_percent'),
                    progress_kind=job.get('progress_kind', 'legacy'),
                    completed=job.get('completed'), total=job.get('total'), unit=job.get('unit', 'steps'),
                    detail=job.get('detail'), results=report.get('capabilities', []),
                    samples=[{k:r.get(k) for k in ('test','passed','output','speed_x','size_change_percent','output_bytes')}
                             for r in report.get('results', []) if 'speed_x' in r],
                    environment=report.get('environment', {}),
                    progress_label=parsed.get('progress_label'), updated=updated, started=started,
                    elapsed=max(0, (job.get('finished') or (time.time() if state=='running' else updated))-(started or updated)),
                    source=report.get('source'), output=output, output_state=output_state,
                    savings=publication.get('video_savings_percent', report.get('video_savings_percent',report.get('video_payload_saving_percent'))),
                    error=report.get('error'), has_log=identifier in logs,
                    awaiting_playback='awaiting' in str(phase), original_unchanged=report.get('original_stat_unchanged',report.get('media_stat_unchanged'))),run,self.root))
            self.jobs = sorted(jobs, key=lambda j:(j['state']=='running', j['started'] or j['updated']), reverse=True)
            self.logs = logs
            self.cached_at = time.time()
            return self.jobs


def make_handler(catalog):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            # Loopback only plus Host validation blocks DNS-rebinding access.
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                self.send_error(403)
                return
            url = urlparse(self.path)
            kind = 'application/json; charset=utf-8'
            if url.path == '/':
                body = HTML.encode()
                kind = 'text/html; charset=utf-8'
            elif url.path == '/api/jobs':
                body = json.dumps(dict(jobs=catalog.snapshot(), now=time.time())).encode()
            elif url.path == '/api/log':
                catalog.snapshot()
                identifier = parse_qs(url.query).get('id', [''])[0]
                path = catalog.logs.get(identifier)
                if not path or not contained(path, catalog.root):
                    self.send_error(404)
                    return
                body = json.dumps(dict(text=tail(path))).encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)
    return Handler


from dashboard_ui import HTML


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(Catalog(args.root)))
    print(f'MuxMender dashboard: http://127.0.0.1:{server.server_port} (read-only; Ctrl+C stops monitoring only)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
