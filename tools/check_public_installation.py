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


def copy_preview():
    return dict(action='preview',settings=dict(path='Example.mkv',mode='encode',
        codec='hevc',hardware='nvidia',quality='transparent',quality_profile='balanced',
        savings_mode='fixed',minimum_savings=25))


def native_children(parent):
    """Read Linux process ownership; never send probe signals."""
    if sys.platform!='linux':raise RuntimeError('Process inspection is Linux-only')
    rows={}
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            fields=dict(line.split(':',1) for line in path.read_text().splitlines() if ':' in line)
            rows[int(path.parent.name)]=(int(fields['PPid']),fields['Name'].strip())
        except (OSError,KeyError,ValueError):continue
    owned={parent}
    while True:
        added={pid for pid,(ppid,name) in rows.items() if ppid in owned}-owned
        if not added:break
        owned.update(added)
    return {pid for pid in owned if pid!=parent and rows[pid][1] in ('ffmpeg','ffprobe','ffprobe-cuda','mkvmerge')}


def cancel_active_copy(get,post,service_pid):
    deadline=time.monotonic()+120
    while True:
        jobs=get('/api/controls')['jobs']
        if jobs and jobs[0]['state']=='running' and native_children(service_pid):break
        if jobs and jobs[0]['state'] in ('failed','skipped','cancelled','awaiting-playback'):
            raise AssertionError('Cancellation did not intercept an active native stage')
        if time.monotonic()>deadline:raise TimeoutError('No active native stage observed')
        time.sleep(.1)
    preview=post(dict(action='clear-queue-preview',include_running=True))
    assert preview['count']==1
    post(dict(action='clear-queue-confirm',confirmation_id=preview['confirmation_id']))
    deadline=time.monotonic()+45
    while True:
        controls=get('/api/controls')
        if controls['jobs'][0]['state']=='cancelled' and not native_children(service_pid):
            assert controls['paused'] is True
            return controls['jobs'][0]
        if time.monotonic()>deadline:raise TimeoutError('Cancellation did not stop native work')
        time.sleep(.1)


def validated_copy(output):
    output=Path(output).resolve()
    matches=[]
    for path in output.rglob('status.json'):
        if path.is_symlink():continue
        try:record=json.loads(path.read_text())
        except (OSError,ValueError):continue
        if record.get('state')!='validated-copy-awaiting-playback':continue
        candidate=Path(record.get('output',''))
        if candidate.is_symlink() or not candidate.is_file() or not candidate.resolve().is_relative_to(output):
            raise AssertionError('Validated output is missing or unsafe')
        with candidate.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=record.get('output_sha256'):raise AssertionError('Validated output checksum changed')
        matches.append(dict(path=str(candidate.relative_to(output)),sha256=actual))
    if len(matches)!=1:raise AssertionError('Expected one validated output')
    return matches[0]


def check(phase, work):
    if sys.platform != 'linux':
        raise RuntimeError('Installation checks are Linux-only')
    work = Path(work)
    media, output = work / 'media', work / 'output'
    media.mkdir(exist_ok=True)
    output.mkdir(exist_ok=True)
    source = media / 'Example.mkv'
    cancellation=phase in ('initialize-cancel','upgrade-cancel')
    full_copy=phase in ('initialize-copy','upgrade-copy')
    initializing=phase in ('initialize','initialize-copy','initialize-cancel')
    if phase in ('initialize-copy','initialize-cancel'):
        video='testsrc2=s=1280x720:r=24:d=30' if cancellation else 'testsrc2=s=640x360:r=24:d=5'
        audio='sine=frequency=440:sample_rate=48000:duration='+('30' if cancellation else '5')
        subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i',
            video,'-f','lavfi','-i',audio,
            '-c:v','libx264','-preset','ultrafast','-crf','0','-threads','2',
            '-pix_fmt','yuv420p','-color_range','tv','-colorspace','bt709',
            '-color_primaries','bt709','-color_trc','bt709','-c:a','aac','-ac','2',
            '-metadata:s:a:0','language=eng','-shortest',str(source)],check=True,timeout=60)
    elif phase == 'initialize':
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
            expected_state='cancelled' if cancellation else 'awaiting-playback' if full_copy else 'kept-original'
            if initializing:
                preview = post(copy_preview() if full_copy or cancellation else history_preview())
                submitted = post(dict(action='submit', preview_id=preview['preview_id']))
                assert submitted['queued'] == 1
                if cancellation:cancel_active_copy(get,post,process.pid)
                deadline=time.monotonic()+(600 if full_copy else 90)
                while True:
                    jobs = get('/api/controls')['jobs']
                    if jobs and jobs[0]['state'] == expected_state:
                        break
                    if jobs and jobs[0]['state'] in ('failed', 'skipped', 'cancelled'):
                        raise AssertionError('Generated request did not complete: '+str(jobs[0].get('reason')))
                    if time.monotonic() > deadline:
                        state = get('/api/controls')
                        raise TimeoutError('Generated request did not finish: ' + str(state.get('wait_reason')))
                    time.sleep(.5)
                post(dict(action='pause'))
                if full_copy:
                    assert 0<jobs[0]['output_bytes']<jobs[0]['original_bytes']
                    assert jobs[0]['original_bytes']-jobs[0]['output_bytes']>=jobs[0]['original_bytes']*.25
                receipt = dict(request_id=jobs[0]['id'], source_sha256=source_hash,
                               original_app_version=api['app_version'])
                if full_copy:receipt['validated_output']=validated_copy(output)
                (work / 'installation-receipt.json').write_text(json.dumps(receipt))
            else:
                receipt = json.loads((work / 'installation-receipt.json').read_text())
                controls = get('/api/controls')
                assert controls['paused'] is True
                assert any(j['id'] == receipt['request_id'] and j['state'] == expected_state
                           for j in controls['jobs']), 'History missing after upgrade'
                assert receipt['source_sha256'] == source_hash
                if full_copy:assert receipt['validated_output']==validated_copy(output), 'Copy changed across recreation'
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
                  scope='generated native-stage cancellation and retained history; no replacement' if cancellation else
                        'generated safe-copy workflow and history; normal quality gates retained' if full_copy else
                        'service API and explicit keep history; no processing worker exercised')
    (work / (phase + '-result.json')).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('initialize', 'upgrade','initialize-copy','upgrade-copy','initialize-cancel','upgrade-cancel'))
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    check(args.phase, args.work)
