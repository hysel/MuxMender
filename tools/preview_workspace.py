"""Loopback-only UI preview with invented data and no media or Docker access."""
import argparse
import importlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))


def sample_state(empty=False):
    now = time.time()
    jobs = []
    for i, (state, name, size, output) in enumerate([
        ('running', 'Library item 001.mkv', 11800000000, None),
        ('running', 'Archive recording 014.mkv', 6200000000, None),
        ('pending', 'Library item 002.mp4', 7400000000, None),
        ('pending', 'Library item 003.mkv', 9800000000, None),
        ('pending', 'Library item 004.avi', 3400000000, None),
        ('replaced', 'Library item 005.mkv', 12600000000, 7400000000),
        ('skipped', 'Library item 006.mkv', 2300000000, None),
        ('failed', 'Archive recording 011.mkv', 4100000000, None),
        ('replaced', 'Library item 007.mkv', 8200000000, 4900000000),
        ('skipped', 'Library item 008.mkv', 970000000, None),
    ]):
        if empty:
            break
        job = dict(id=f'preview-{i}', source='/media/Film archive/' + name,
                   state=state, settings={'mode': 'replace'}, batch_id='preview-batch',
                   created=now - 10000 + i * 50, started=now - 1800,
                   original_bytes=size, app_version='Design preview')
        if state not in ('pending', 'running'):
            job['finished'] = now - 300 - i * 40
        if output:
            job.update(output_bytes=output, saved_bytes=size-output)
        if state == 'skipped':
            job.update(reason='Already efficient for current settings: no tested option saved enough space.',
                       decision_code='already_efficient_for_settings')
        if state == 'failed':
            job['reason'] = 'Source audio could not be decoded; original retained.'
        jobs.append(job)
    counts = {s: sum(j['state'] == s for j in jobs) for s in ('running', 'pending', 'replaced', 'skipped', 'failed')}
    return dict(jobs=jobs, counts=counts, ready=True, paused=False, csrf_token='preview-only', app_version='Design preview',
                replacement_enabled=True, resource_profile='shared',
                gpu_yield={'enabled': True, 'reason': 'No competing GPU activity'},
                resources={'active': counts['running'], 'reason': 'Shared-host profile',
                           'telemetry': {'cpu_percent': 28, 'gpu_encode_percent': 72,
                                         'gpu_compute_percent': 42, 'gpu_decode_percent': 37,
                                         'available_gib': 46.2, 'vram_free_gib': 3.1}},
                lifetime_savings={'saved_bytes': 63210000000, 'replaced_files': 18, 'percent': 38.4},
                view={'preferences': {}, 'archived_ids': [], 'undo_archive': []},
                wait_reason='Queue running' if jobs else 'No jobs in the queue.')


class Handler(BaseHTTPRequestHandler):
    def send(self, body, code=200, mime='application/json'):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        from ui import workspace, workbench, app
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        state = sample_state(self.server.empty)
        if url.path == '/':
            importlib.reload(workspace)
            importlib.reload(workbench)
            importlib.reload(app)
            html = app.HTML.replace('<body>', '<body><div class="preview-notice" role="note">Design preview · sample data only. No access to your media or production queue.</div>', 1)
            self.send(html, mime='text/html')
        elif url.path == '/favicon.ico':
            self.send('', code=204, mime='image/x-icon')
        elif url.path == '/api/controls':
            self.send(state)
        elif url.path == '/api/jobs':
            tracks = []
            for i, request in enumerate(state['jobs'][:2]):
                tracks.append(dict(id='tracked-' + request['id'],
                                   directory='/preview/request-' + request['id'] + '/job-active',
                                   state='running', phase='full-encode' if i else 'Checking copied tracks',
                                   workflow_stage='encode' if i else 'validate', stage_percent=71 if i else 54,
                                   stage_eta=720 if i else 240, updated=time.time(), stage_updated=time.time(),
                                   started=request['started'], detail='Preview progress; not a real conversion'))
            self.send({'jobs': tracks, 'catalog_updated': time.time()})
        elif url.path == '/api/media':
            path = query.get('path', [''])[0] or '.'
            if path not in ('.', 'Film archive', 'Series', 'Home video'):
                self.send({'error': 'This preview contains example folders only.'}, 400)
                return
            videos = query.get('videos') == ['true']
            entries = ([dict(name=f'Library item {n:03}.mkv', path=path+f'/Library item {n:03}.mkv', directory=False) for n in range(1, 4)]
                       if videos else [dict(name=n, path=n, directory=True) for n in ('Film archive', 'Series', 'Home video')] if path == '.' else [])
            self.send(dict(path=path, parent=None if path == '.' else '.', next_offset=None, entries=entries))
        else:
            self.send({'error': 'Preview endpoint unavailable'}, 404)

    def do_POST(self):
        if self.path != '/api/control':
            self.send({'error': 'Preview actions only'}, 403)
            return
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 16384:
            self.send({'error': 'Invalid preview request'}, 400)
            return
        body = json.loads(self.rfile.read(length))
        if body.get('action') == 'preview':
            settings = body['settings']
            files = [dict(path=settings['path']+f'/Library item {n:03}.mkv', signature=[n*3200000000, 0]) for n in range(1, 4)]
            self.send(dict(preview_id='design-only', settings=settings, files=files,
                           note='Design preview only. These files do not exist.'))
        elif body.get('action') == 'clear-queue-preview':
            self.send(dict(confirmation_id='design-only', count=5, running=2, pending=3))
        elif body.get('action') == 'view-preferences':
            # Acknowledge display-only choices. No production or file writes.
            self.send(dict(message='Preview display updated'))
        else:
            self.send({'error': 'Design preview only — no jobs, settings or files were changed.'}, 403)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--empty', action='store_true')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.empty = args.empty
    print(f'Design preview: http://127.0.0.1:{args.port}/ (invented data, no media access)', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
