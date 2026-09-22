"""Read-only localhost dashboard for MuxMender. Python standard library only."""

from ui import HTML
import argparse
import ctypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
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
        # Read recent throughput from old running processes without restarting them.
        end, value = float(elapsed), float(percent)
        recent = []
        for name, p, t, _ in reversed(bars):
            if name != label or float(t) > end or float(p) > value:
                break
            if end - float(t) > 120:
                break
            recent.append((float(t), float(p)))
        if len(recent) > 1:
            start, initial = recent[-1]
            if end - start >= 10 and value > initial:
                result['stage_eta'] = round((100-value)*(end-start)/(value-initial))
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
    if not candidates:
        status_path=directory/'status.json'
        status=read_json(status_path) if contained(status_path,root) else {}
        state=status.get('state')
        if state=='trials-completed':
            decision=status.get('decision',{})
            return dict(status='skipped' if decision.get('action')=='keep_original' else 'completed',
                        detail=decision.get('reason'), decision=decision, original_retained=True),False
        if state=='validated-copy-awaiting-playback':
            return dict(status='verified-awaiting-playback', output=status.get('output'),
                        total_savings_percent=status.get('saved_percent'), original_retained=True),False
        if state in ('stopped-original-retained','full-output-rejected-insufficient-savings'):
            return dict(status='failed' if state=='stopped-original-retained' else 'skipped',
                        error=status.get('error'), detail=state, original_retained=True),False
        return {},False
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
    data['execution_state']=initial.get('state',data.get('execution_state',data.get('state')))
    data['execution_error']=initial.get('error')
    data['result']=report
    if report.get('status') in ('running','queued','cancelling'):
        data['validation_pending']=True
        data['detail']='Process ended without a final validation report; no validation pass inferred.'
        return data
    data['state']='playback-approved' if approved else ('verified' if str(report.get('status','')).startswith('verified') else report.get('status',data.get('state')))
    data['phase']='Playback approved' if approved else report.get('status',data.get('phase'))
    data['error']=report.get('error')
    if report.get('detail'):data['detail']=report['detail']
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


def file_savings(report):
    """Final whole-file reduction only; never infer savings from partial media."""
    status = str(report.get('status', ''))
    if not status.startswith(('verified', 'validated-', 'experimental-preview-awaiting-playback')):
        return None
    value = report.get('total_savings_percent')
    if type(value) not in (int, float) or not math.isfinite(value) or value > 100:
        return None
    return value


def batch_savings(batch):
    """Size-weighted reduction for newly validated copies, not pending/skipped files."""
    source_bytes = reduced_bytes = count = 0
    for row in batch.get('entries', []):
        if not isinstance(row, dict) or row.get('status') != 'validated-copy':
            continue
        size = row.get('fingerprint', {}).get('size')
        value = row.get('savings_percent')
        if (type(size) not in (int, float) or not math.isfinite(size) or size <= 0
                or type(value) not in (int, float) or not math.isfinite(value) or value > 100):
            continue
        source_bytes += size
        reduced_bytes += size * value / 100
        count += 1
    return dict(percent=100 * reduced_bytes / source_bytes, files=count) if count else None


class Catalog:
    def __init__(self, root, artifact_roots=()):
        self.root = Path(root).resolve()
        self.artifact_roots = [self.root, *(Path(p).resolve() for p in artifact_roots)]
        self.lock = threading.Lock()
        self.cached_at = 0
        self.jobs = []
        self.logs = {}

    def read(self, path):
        return read_json(path) if self.allowed_root(path) else {}

    def allowed_root(self, path):
        return next((root for root in self.artifact_roots if contained(path, root)), None)

    def snapshot(self):
        with self.lock:
            if time.time() - self.cached_at < 3:
                return self.jobs
            directories = set()
            # Only known artifact roots; never enumerate source drives or media contents.
            bases = [self.root/'reports', self.root/'test-output', *self.artifact_roots[1:]]
            for base in dict.fromkeys(bases):
                try:accessible=bool(self.allowed_root(base)) and base.is_dir()
                except OSError:accessible=False
                if not accessible:
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
                if not self.allowed_root(run):
                    run = directory
                run_root = self.allowed_root(run)
                status = self.read(run/'status.json')
                plan = self.read(run/'plan.json')
                report, _ = latest_outcome(run,run_root)
                savings_percent = file_savings(report)
                savings_scope = 'Validated file'
                batch = self.read(run/'batch.json') or self.read(run.parent/'batch.json')
                aggregate = batch_savings(batch)
                if aggregate:
                    savings_percent = aggregate['percent']
                    savings_scope = f"{aggregate['files']} validated batch file(s)"
                publication = self.read(run/'publication.json')
                logpath = directory/'terminal.log'
                if not logpath.is_file():
                    logpath = run/'terminal.log'
                log = tail(logpath) if self.allowed_root(logpath) else ''
                stamps = [p.stat().st_mtime for p in (run/'status.json', run/'validation.json', logpath)
                          if p.is_file() and self.allowed_root(p)]
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
                stage_percent = job.get('stage_percent') if structured else parsed.get('stage_percent')
                stage_eta = job.get('stage_eta') if structured else parsed.get('stage_eta')
                current_encode_log = ((phase == 'Encoding video' and parsed.get('progress_label') == 'Encoding') or
                    (phase == 'Encoding Intel AV1 HDR10' and parsed.get('progress_label') == 'Stage (10-65% overall)'))
                if (structured and stage_percent is None and current_encode_log and logpath.is_file()
                        and time.time() - logpath.stat().st_mtime < 90):
                    stage_percent, stage_eta = parsed.get('stage_percent'), parsed.get('stage_eta')
                if job.get('stage_updated') and time.time() - job['stage_updated'] > 30:
                    stage_eta = None
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
                if log and self.allowed_root(logpath):
                    logs[identifier] = logpath
                title = job.get('title') or ('Full Dolby Vision preservation' if directory.name.startswith('dv-full-') else report.get('scope')) or directory.name
                source = report.get('source') or status.get('source') or plan.get('source')
                if title == 'Measured codec selection':
                    modes = plan.get('hevc_nvenc_cq')
                    mode = 'HEVC CQ '+ '/'.join(map(str,modes)) if modes else 'Codec comparison'
                    if plan.get('adaptive'):mode='Adaptive '+mode
                    filename = str(source).replace('\\', '/').rsplit('/',1)[-1] if source else 'Unknown source'
                    title = mode+' · '+filename+' · '+directory.name.removeprefix('job-')
                jobs.append(apply_outcome(dict(id=identifier, title=title,
                    execution_state=job.get('state',state),
                    directory=str(directory.relative_to(self.root)) if contained(directory,self.root) else str(directory), state=state, phase=phase, percent=percent,
                    stage_eta=stage_eta if state == 'running' else None,
                    stage_percent=stage_percent,
                    stage_started=job.get('stage_started'),
                    workflow_stage=job.get('workflow_stage'),
                    performance_seconds=job.get('performance_seconds',{}),
                    performance_scope=job.get('performance_scope'),
                    progress_kind=job.get('progress_kind', 'legacy'),
                    completed=job.get('completed'), total=job.get('total'), unit=job.get('unit', 'steps'),
                    detail=job.get('detail'), results=report.get('capabilities', []),
                    samples=[{k:r.get(k) for k in ('test','passed','output','speed_x','size_change_percent','output_bytes')}
                             for r in report.get('results', []) if 'speed_x' in r],
                    environment=report.get('environment', {}),
                    progress_label=parsed.get('progress_label'), updated=updated, started=started,
                    elapsed=max(0, (job.get('finished') or (time.time() if state=='running' else updated))-(started or updated)),
                    source=source, output=output, output_state=output_state,
                    file_savings_percent=savings_percent, savings_scope=savings_scope,
                    savings=publication.get('video_savings_percent', report.get('video_savings_percent',report.get('video_payload_saving_percent'))),
                    error=report.get('error'), has_log=identifier in logs,
                    awaiting_playback='awaiting' in str(phase), original_unchanged=report.get('original_size_mtime_unchanged',report.get('original_stat_unchanged',report.get('media_stat_unchanged')))),run,run_root))
            self.jobs = sorted(jobs, key=lambda j:(j['state']=='running', j['started'] or j['updated']), reverse=True)
            self.logs = logs
            self.cached_at = time.time()
            return self.jobs


def make_handler(catalog, page=HTML, batch_provider=None, review_writer=None, allowed_hosts=(), authorize=None, app_provider=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def permitted(self):
            hosts=(f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}', *allowed_hosts)
            if self.headers.get('Host') not in hosts:
                self.send_error(403);return False
            if authorize is not None and not authorize(self.headers.get('Authorization','')):
                self.send_response(401)
                self.send_header('WWW-Authenticate','Basic realm="MuxMender", charset="UTF-8"')
                self.send_header('Content-Length','0')
                self.send_header('Cache-Control','no-store')
                self.end_headers();return False
            return True

        def do_POST(self):
            if not self.permitted():return
            if review_writer is None:
                self.send_error(501);return
            host=self.headers.get('Host','')
            if host not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}') or self.headers.get('Origin')!='http://'+host:
                self.send_error(403);return
            if self.path!='/api/review' or review_writer is None:
                self.send_error(404);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8192 or self.headers.get('Content-Type')!='application/json':raise ValueError('Invalid request')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('Invalid object')
                body=json.dumps(review_writer(data)).encode()
            except (ValueError,OSError,StopIteration):
                self.send_error(400);return
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.end_headers();self.wfile.write(body)

        def do_GET(self):
            # Loopback only plus Host validation blocks DNS-rebinding access.
            if not self.permitted():return
            url = urlparse(self.path)
            kind = 'application/json; charset=utf-8'
            if url.path == '/':
                body = page.encode()
                kind = 'text/html; charset=utf-8'
            elif url.path == '/api/jobs':
                body = json.dumps(dict(jobs=catalog.snapshot(), now=time.time())).encode()
            elif url.path == '/api/app' and app_provider is not None:
                body = json.dumps(app_provider()).encode()
            elif url.path == '/api/batches' and batch_provider is not None:
                body = json.dumps(dict(batches=batch_provider(), now=time.time())).encode()
            elif url.path == '/api/log':
                catalog.snapshot()
                identifier = parse_qs(url.query).get('id', [''])[0]
                path = catalog.logs.get(identifier)
                if not path or not catalog.allowed_root(path):
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




def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--artifact-root', type=Path, action='append', default=[],
                        help='Additional trusted output directory for linked validation reports (repeatable)')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(Catalog(args.root, args.artifact_root)))
    print(f'MuxMender dashboard: http://127.0.0.1:{server.server_port} (read-only; Ctrl+C stops monitoring only)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
