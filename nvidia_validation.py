"""Generated-media-only NVENC validation; no installations or real-media inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

import job_tracking
import muxmender as mm


def main(argv=None, run_directory=None, progress_callback=None, guard=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffprobe', required=True)
    parser.add_argument('--gpu', type=int, default=0)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    run = Path(run_directory) if run_directory else root / 'reports' / ('nvidia-fixtures-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    report = dict(scope='Generated fixtures only; no Dolby Vision or static HDR metadata validation; no visual-quality equivalence claim.', results=[])

    def update(label, percent):
        if progress_callback:
            progress_callback(label, percent)
        else:
            job_tracking.phase(run, label, percent)

    def command(cmd, label, duration=None):
        if guard:
            guard()
        update(label, 0)
        print(label, flush=True)
        if not progress_callback:
            print(subprocess.list2cmdline([str(x) for x in cmd]), flush=True)
        started = time.monotonic()
        process = subprocess.Popen([str(x) for x in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        lines = queue.Queue()
        def reader():
            for line in process.stdout:
                lines.put(line)
            lines.put(None)
        worker = threading.Thread(target=reader, daemon=True)
        worker.start()
        output = []
        last_percent = 0
        try:
            while True:
                if guard:
                    guard()
                if time.monotonic() - started > 120:
                    raise TimeoutError(label + ' exceeded 120 seconds')
                try:
                    line = lines.get(timeout=0.25)
                except queue.Empty:
                    continue
                if line is None:
                    break
                output.append(line)
                if duration and line.startswith('out_time_us='):
                    percent = max(last_percent, min(100, float(line.split('=')[1]) / (duration * 10000)))
                    last_percent = percent
                    update(label, percent)
                    print(f'{label}: {percent:.1f}% | elapsed {time.monotonic()-started:.1f}s', flush=True)
                elif not duration:
                    pass
            code = process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            worker.join(timeout=2)
            process.stdout.close()
            with (run / (label + '.log')).open('x', encoding='utf-8') as stream:
                stream.write(''.join(output))
        elapsed = time.monotonic() - started
        if code:
            raise RuntimeError(f'{label} exited {code}: ' + ''.join(output)[-3000:])
        return ''.join(output), elapsed

    def probe(path):
        result = subprocess.run([args.ffprobe, '-v', 'error', '-show_streams', '-show_format', '-show_chapters', '-show_packets', '-show_data_hash', 'sha256', '-of', 'json', str(path)], capture_output=True, text=True, encoding='utf-8', check=True, timeout=60)
        return json.loads(result.stdout)

    def digest(path):
        value = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                value.update(block)
        return value.hexdigest()

    def nonvideo(data):
        indices = {s['index'] for s in data['streams'] if s['codec_type'] in ('audio', 'subtitle')}
        return [{k: p.get(k) for k in ('stream_index', 'pts_time', 'duration_time', 'size', 'data_hash')} for p in data['packets'] if p['stream_index'] in indices]

    try:
        report['python'] = sys.version
        report['gpu'], _ = command(['nvidia-smi', '--query-gpu=index,name,driver_version,memory.total', '--format=csv'], 'gpu')
        report['ffmpeg'], _ = command([args.ffmpeg, '-version'], 'ffmpeg-version')
        report['ffprobe'], _ = command([args.ffprobe, '-version'], 'ffprobe-version')
        report['encoders'], _ = command([args.ffmpeg, '-hide_banner', '-encoders'], 'encoders')
        report['vendors'] = mm.gpu_vendors()
        available = mm.ffmpeg_encoder_names(args.ffmpeg)
        subtitles = run / 'generated.srt'
        with subtitles.open('x', encoding='utf-8') as stream:
            stream.write('1\n00:00:00,000 --> 00:00:01,500\nGenerated NVENC validation fixture\n')
        metadata = run / 'generated.ffmeta'
        with metadata.open('x', encoding='utf-8') as stream:
            stream.write(';FFMETADATA1\ntitle=Generated validation\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=2000\ntitle=Generated chapter\n')
        for mode, size, pixel, primaries, transfer, space in [
            ('sdr1080', '1920x1080', 'yuv420p', 'bt709', 'bt709', 'bt709'),
            ('pq1080', '1920x1080', 'yuv420p10le', 'bt2020', 'smpte2084', 'bt2020nc'),
            ('pq2160', '3840x2160', 'yuv420p10le', 'bt2020', 'smpte2084', 'bt2020nc'),
        ]:
            source = run / (mode + '-generated.mkv')
            command([args.ffmpeg, '-hide_banner', '-nostdin', '-n', '-f', 'lavfi', '-i', f'testsrc2=size={size}:rate=24:duration=2,format={pixel},setparams=range=limited:color_primaries={primaries}:color_trc={transfer}:colorspace={space}', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=2', '-i', subtitles, '-f', 'ffmetadata', '-i', metadata, '-map', '0:v', '-map', '1:a', '-map', '2:s', '-map_metadata', '3', '-map_chapters', '3', '-c:v', 'libx265', '-preset', 'ultrafast', '-x265-params', f'lossless=1:colorprim={primaries}:transfer={transfer}:colormatrix={space}', '-pix_fmt', pixel, '-color_primaries', primaries, '-color_trc', transfer, '-colorspace', space, '-color_range', 'tv', '-c:a', 'pcm_s16le', '-c:s', 'srt', '-progress', 'pipe:1', '-nostats', source], mode + '-generate', 2)
            before = digest(source)
            original = probe(source)
            fixture_video = next(s for s in original['streams'] if s['codec_type'] == 'video')
            expected = dict(width=int(size.split('x')[0]), height=int(size.split('x')[1]), pix_fmt=pixel, color_primaries=primaries, color_transfer=transfer, color_space=space, color_range='tv')
            if any(fixture_video.get(k) != v for k, v in expected.items()):
                raise ValueError(f'Invalid fixture tags: expected {expected}, got {fixture_video}')
            info = mm.probe(source, args.ffprobe)
            info.recommendation = 'transcode'
            for codec in ('hevc', 'av1'):
                label = mode + '-' + codec
                entry = dict(test=label, source=str(source))
                report['results'].append(entry)
                try:
                    selection = mm.select_encoder(codec, 'nvidia', available, report['vendors'])
                    output = run / (label + '.mkv')
                    cmd = mm.build_ffmpeg_command(source, output, info, codec, 'balanced', args.ffmpeg, selection.encoder, 'keep')
                    cmd[-1:-1] = ['-gpu', str(args.gpu), '-progress', 'pipe:1', '-nostats']
                    _, elapsed = command(cmd, label + '-encode', 2)
                    actual = probe(output)
                    video = next(s for s in actual['streams'] if s['codec_type'] == 'video')
                    original_video = next(s for s in original['streams'] if s['codec_type'] == 'video')
                    checks = {key: video.get(key) == original_video.get(key) for key in ('width', 'height', 'pix_fmt', 'color_primaries', 'color_transfer', 'color_space', 'color_range')}
                    checks['codec'] = video['codec_name'] == codec
                    checks['audio_subtitle_streams'] = [(s['codec_type'], s['codec_name']) for s in actual['streams'] if s['codec_type'] != 'video'] == [(s['codec_type'], s['codec_name']) for s in original['streams'] if s['codec_type'] != 'video']
                    checks['audio_subtitle_packets'] = nonvideo(actual) == nonvideo(original)
                    checks['chapters'] = actual['chapters'] == original['chapters']
                    checks['video_frames_48'] = sum(p['stream_index'] == video['index'] for p in actual['packets']) == 48
                    checks['video_pts'] = sorted(p['pts_time'] for p in actual['packets'] if p['stream_index'] == video['index']) == sorted(p['pts_time'] for p in original['packets'] if p['stream_index'] == original_video['index'])
                    command([args.ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-xerror', '-err_detect', 'explode', '-i', output, '-map', '0:v', '-map', '0:a', '-f', 'null', '-'], label + '-decode')
                    checks['software_decode'] = True
                    checks['source_sha256_unchanged'] = digest(source) == before
                    entry.update(checks=checks, passed=all(checks.values()), encoder=selection.encoder, output=str(output), encode_seconds=elapsed, end_to_end_speed_x=2/elapsed, source_bytes=source.stat().st_size, output_bytes=output.stat().st_size, source_sha256=before, video={k: video.get(k) for k in ('codec_name', 'profile', 'width', 'height', 'pix_fmt', 'color_primaries', 'color_transfer', 'color_space', 'color_range')})
                    with (run / (label + '-probe.json')).open('x', encoding='utf-8') as stream:
                        json.dump(actual, stream, indent=2)
                    if not progress_callback:
                        print(json.dumps(entry), flush=True)
                except Exception as exc:
                    entry.update(passed=False, error=str(exc))
                    print(f'FAILED {label}: {exc}', flush=True)
                update(label + '-complete', 100)
        report['passed'] = len(report['results']) == 6 and all(e['passed'] for e in report['results'])
    except Exception as exc:
        report.update(passed=False, error=str(exc))
        print(str(exc), flush=True)
    finally:
        with (run / 'validation.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
        update('Fixture validation complete' if report.get('passed') else 'Fixture validation failed', 100)
        print(f'Report: {run / "validation.json"}', flush=True)
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(job_tracking.tracked_call(main, 'NVIDIA generated fixture validation'))
