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
                if not job and str(directory.resolve()) in linked:
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
                state = job.get('state', 'unknown')
                if str(phase).startswith('verified'):
                    state = 'verified'
                elif str(phase).lower() in ('failed', 'cancelled'):
                    state = str(phase).lower()
                elif state == 'running' or (not job and status.get('pid')):
                    running = alive(job.get('pid', status.get('pid')))
                    state = 'interrupted' if running is False else 'running' if running and time.time()-updated < 90 else 'stale'
                parsed = progress(log)
                if (run/'status.json').is_file() and logpath.is_file() and (run/'status.json').stat().st_mtime > logpath.stat().st_mtime:
                    parsed = {}  # The log may still contain the previous stage's 100%/ETA.
                percent = parsed.get('percent', status.get('percent', job.get('percent')))
                if state in ('verified', 'completed'):
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
                    stage_eta=parsed.get('stage_eta') if state == 'running' else None,
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


HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MuxMender · Jobs</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#10151d;color:#edf3fa;font-size:16px}*{box-sizing:border-box}body{margin:0}header{border-bottom:1px solid #334151;padding:24px 5%;display:flex;align-items:center;gap:20px;flex-wrap:wrap}h1{font-size:24px;margin:0}header span{color:#acbacb}main{max-width:1400px;margin:auto;padding:28px 5%}.summary{display:flex;gap:32px;flex-wrap:wrap;margin-bottom:28px}.summary strong{font-size:30px;display:block}.summary span,.muted{color:#aebdce}.notice{border-left:3px solid #56d6ad;padding:8px 16px;margin-bottom:24px;color:#bdcbd9}article{border:1px solid #344353;border-radius:10px;background:#18212c;margin:0 0 18px;padding:22px}article.running{border-left:4px solid #56d6ad}.row{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}h2{font-size:18px;margin:0;overflow-wrap:anywhere}.badge{border:1px solid #597086;border-radius:30px;padding:4px 12px;font-size:14px}.running .badge{color:#77edc4}.failed .badge,.interrupted .badge{color:#ffb3a7}.phase{margin:18px 0 10px;color:#d3deeb}.meter{display:flex;align-items:center;gap:14px}progress{width:100%;height:15px;accent-color:#56d6ad}.metrics{display:flex;gap:24px;flex-wrap:wrap;font-size:14px;color:#b6c7d9;margin-top:12px}details{margin-top:18px;font-size:14px}summary,button{cursor:pointer}dl{display:grid;grid-template-columns:130px 1fr;gap:10px}dt{color:#aebdce}dd{margin:0;overflow-wrap:anywhere}button{border:1px solid #70859a;background:#263648;color:#eef5ff;padding:8px 14px;border-radius:5px;font:inherit}pre{background:#0c1118;border:1px solid #344353;padding:14px;max-height:320px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 monospace}#connection{margin-left:auto;font-size:14px}#error{color:#ffc0b3}footer{font-size:14px;color:#adbed0;padding:12px 0 24px}@media(max-width:600px){main{padding:20px 16px}article{padding:16px}dl{grid-template-columns:1fr}dd{margin-bottom:10px}.summary{gap:20px}}
/* Text-only job status; shared by the queue and history views. */
progress{display:none}
</style><header><h1>MuxMender</h1><span>Job monitor</span><span id="connection" role="status">Connecting…</span></header>
<main><div class="summary" id="summary"></div><div class="notice">Local, read-only monitoring. Original media is never changed by this dashboard.</div><p id="error" role="alert"></p><section id="jobs" aria-label="Jobs"><p>Loading job history…</p></section><footer>Refreshes every 3 seconds. ETA is for the current stage, not the entire workflow. Verification does not replace playback review.</footer></main>
<script>
const jobs=document.querySelector('#jobs'), nodes=new Map();
const duration=s=>s==null?'Unknown':s<60?Math.round(s)+'s':s<3600?Math.floor(s/60)+'m '+Math.round(s%60)+'s':Math.floor(s/3600)+'h '+Math.floor(s%3600/60)+'m';
function el(tag,text,cls){const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n}
async function fetchLog(id,pre){try{const r=await fetch('/api/log?id='+encodeURIComponent(id));if(!r.ok)throw Error('Log unavailable');pre.textContent=(await r.json()).text;pre.scrollTop=pre.scrollHeight}catch(e){pre.textContent=e.message}}
function render(j){let entry=nodes.get(j.id);let open=entry?.querySelector('details')?.open, oldLog=entry?.querySelector('pre');const a=el('article',null,j.state);const row=el('div',null,'row');row.append(el('h2',j.title),el('span',j.state.replaceAll('-',' '),'badge'));a.append(row,el('p',j.phase,'phase'));const meter=el('div',null,'meter'),bar=el('progress');bar.max=100;if(j.percent!=null)bar.value=j.percent;bar.setAttribute('aria-label','Job progress');meter.append(bar,el('span',j.percent==null?'—':Number(j.percent).toFixed(1)+'%'));a.append(meter);const m=el('div',null,'metrics');m.append(el('span','Elapsed '+duration(j.elapsed)),el('span',j.stage_eta==null?'Stage ETA unavailable':'Stage ETA ~'+duration(j.stage_eta)),el('span','Updated '+new Date(j.updated*1000).toLocaleString()));if(j.savings!=null)m.append(el('span','Video savings '+Number(j.savings).toFixed(1)+'%'));a.append(m);if(j.state==='stale')a.append(el('p','No recent update; progress may be stale. This does not prove the job failed.','muted'));if(j.awaiting_playback)a.append(el('p','Validation passed · playback review still required','muted'));if(j.error)a.append(el('p',j.error));const d=el('details');d.open=!!open;d.append(el('summary','Details & log'));const dl=el('dl');for(const [k,v] of [['Run',j.directory],['Source',j.source],['Output',j.output],['Output status',j.output_state],['Source check',j.original_unchanged===true?'Size / modification time unchanged':j.original_unchanged===false?'Changed — review required':'Not reported']]){if(v){dl.append(el('dt',k),el('dd',v))}}d.append(dl);if(j.has_log){const b=el('button','Show latest log'),pre=oldLog||el('pre');pre.hidden=!oldLog||oldLog.hidden;b.onclick=()=>{pre.hidden=false;fetchLog(j.id,pre)};d.append(b,pre);if(!pre.hidden)fetchLog(j.id,pre)}a.append(d);if(entry)entry.replaceWith(a);else jobs.append(a);nodes.set(j.id,a);return a}
async function refresh(){try{const r=await fetch('/api/jobs');if(!r.ok)throw Error('Dashboard unavailable');const data=await r.json();document.querySelector('#error').textContent='';document.querySelector('#connection').textContent='Live · '+new Date().toLocaleTimeString();const summary=document.querySelector('#summary');summary.replaceChildren();for(const [label,count] of [['Running',data.jobs.filter(j=>j.state==='running').length],['Verified / completed',data.jobs.filter(j=>['verified','completed'].includes(j.state)).length],['Needs attention',data.jobs.filter(j=>['failed','interrupted','stale','unknown'].includes(j.state)).length],['Total jobs',data.jobs.length]]){const n=el('div');n.append(el('strong',count),el('span',label));summary.append(n)}if(!nodes.size)jobs.replaceChildren();const ids=new Set(data.jobs.map(j=>j.id));for(const [id,node] of nodes)if(!ids.has(id)){node.remove();nodes.delete(id)}for(const j of data.jobs)jobs.append(render(j));if(!data.jobs.length)jobs.replaceChildren(el('p','No jobs yet. New MuxMender command-line runs will appear here.'));}catch(e){document.querySelector('#connection').textContent='Disconnected';document.querySelector('#error').textContent='Cannot refresh. Last displayed values may be stale. Keep the dashboard server running.'}finally{setTimeout(refresh,3000)}}refresh();
</script></html>'''


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
