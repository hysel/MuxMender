"""Linux-only service checks with generated media and isolated persistent storage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request


def history_preview():
    # This checks API/history migration, not worker throughput. An explicit keep
    # decision avoids competing with production or bypassing admission controls.
    return dict(action='preview', settings=dict(path='Example.mkv', mode='keep'))


def check(phase, work):
    if sys.platform != 'linux':
        raise RuntimeError('Installation checks are Linux-only')
    work = Path(work)
    media, output = work / 'media', work / 'output'
    media.mkdir(exist_ok=True)
    output.mkdir(exist_ok=True)
    source = media / 'Example.mkv'
    if phase == 'initialize':
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
                        'color=c=black:s=192x192:r=5:d=1', '-c:v', 'libx264', str(source)],
                       check=True, timeout=30)
    with source.open('rb') as stream:
        source_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    base = 'http://127.0.0.1:18765'
    env = dict(os.environ, MUXMENDER_MEDIA_ROOT=str(media), MUXMENDER_OUTPUT_ROOT=str(output),
               MUXMENDER_BIND='127.0.0.1', MUXMENDER_PORT='18765',
               MUXMENDER_ALLOWED_HOSTS='127.0.0.1:18765', MUXMENDER_CONTROLS_ENABLED='true',
               MUXMENDER_QUEUE_ENABLED='false', MUXMENDER_SOURCE='',
               MUXMENDER_PLAYBACK_CODECS='hevc,av1,h264')
    def get(path):
        return json.load(urllib.request.urlopen(base + path, timeout=10))
    def post(data):
        token = get('/api/controls')['csrf_token']
        request = urllib.request.Request(base + '/api/control',
            data=json.dumps(data).encode(), headers={'Content-Type': 'application/json',
            'Origin': base, 'X-MuxMender-CSRF': token})
        try:
            return json.load(urllib.request.urlopen(request, timeout=10))
        except urllib.error.HTTPError as exc:
            raise RuntimeError('API rejected ' + data.get('action', 'request') + ': ' + exc.read().decode()) from exc
    with (work / (phase + '-service.log')).open('w') as log:
        process = subprocess.Popen([sys.executable, '-B', '-m', 'app_service'],
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            while True:
                try:
                    api = get('/api')
                    break
                except (OSError, urllib.error.URLError):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Service did not start')
                    time.sleep(.25)
            assert api['controls_enabled'] is True
            assert b'MuxMender' in urllib.request.urlopen(base, timeout=10).read()
            assert isinstance(get('/api/jobs')['jobs'], list)
            assert get('/api/media?path=.&videos=true&recursive=true')
            # Cross-site writes must fail even with a valid token.
            request = urllib.request.Request(base + '/api/control', data=b'{"action":"pause"}',
                headers={'Content-Type': 'application/json', 'Origin': 'http://invalid.example',
                         'X-MuxMender-CSRF': get('/api/controls')['csrf_token']})
            try:
                urllib.request.urlopen(request, timeout=10)
                raise AssertionError('Cross-site write was accepted')
            except urllib.error.HTTPError as exc:
                assert exc.code == 403
            if phase == 'initialize':
                preview = post(history_preview())
                submitted = post(dict(action='submit', preview_id=preview['preview_id']))
                assert submitted['queued'] == 1
                while True:
                    jobs = get('/api/controls')['jobs']
                    if jobs and jobs[0]['state'] == 'kept-original':
                        break
                    if jobs and jobs[0]['state'] in ('failed', 'skipped', 'cancelled'):
                        raise AssertionError('Generated keep decision did not complete')
                    if time.monotonic() > deadline:
                        state = get('/api/controls')
                        raise TimeoutError('Keep decision did not finish: ' + str(state.get('wait_reason')))
                    time.sleep(.5)
                post(dict(action='pause'))
                receipt = dict(request_id=jobs[0]['id'], source_sha256=source_hash,
                               original_app_version=api['app_version'])
                (work / 'installation-receipt.json').write_text(json.dumps(receipt))
            else:
                receipt = json.loads((work / 'installation-receipt.json').read_text())
                controls = get('/api/controls')
                assert controls['paused'] is True
                assert any(j['id'] == receipt['request_id'] and j['state'] == 'kept-original'
                           for j in controls['jobs']), 'History missing after upgrade'
                assert receipt['source_sha256'] == source_hash
            with source.open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == source_hash
        finally:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise
        assert process.returncode == 0, 'Service did not shut down cleanly'
    result = dict(phase=phase, passed=True, app_version=api['app_version'],
                  source_unchanged=True, persistent_history=True,
                  scope='service API and explicit keep history; no processing worker exercised')
    (work / (phase + '-result.json')).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('initialize', 'upgrade'))
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    check(args.phase, args.work)
