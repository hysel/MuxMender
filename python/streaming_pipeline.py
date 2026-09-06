"""Bounded DV5 -> PQ -> HEVC pipe test. No lossless media written to disk."""
import json
import copy
import math
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import replace

import muxmender as mm
import native_pipeline as np
from runtime_support import TerminalProgress


class EncoderFailure(RuntimeError):
    pass


def full_remux_command(ffmpeg, source, video, output):
    # No seeking, time limit, shortest, or chapter trimming in whole-file mode.
    return [ffmpeg, '-hide_banner', '-nostdin', '-n', '-i', str(source), '-i', str(video),
            '-map', '1:v:0', '-map', '0:a?', '-map', '0:s?', '-map', '0:t?',
            '-map_metadata', '0', '-map_chapters', '0', '-c', 'copy',
            '-avoid_negative_ts', 'disabled', '-progress', 'pipe:1', '-nostats', str(output)]


class RunGuard:
    def __init__(self, directory, reserve=1024**3):
        self.directory = directory
        self.reserve = reserve
        self.checked = 0
        self.phase = 'encoding'

    def __call__(self):
        if (self.directory / 'STOP').exists():
            raise RuntimeError('Stop requested by STOP file; all media retained')
        now = time.monotonic()
        if now - self.checked >= 5:
            self.checked = now
            if shutil.disk_usage(self.directory).free < self.reserve:
                raise RuntimeError('Free space fell below safety reserve; all media retained')

    def status(self, percent):
        from job_tracking import phase
        phase(self.directory, self.phase, percent)
        # Only a status file in this run's exclusively-created directory.
        with (self.directory / 'status.json').open('w', encoding='utf-8') as out:
            json.dump({'phase': self.phase, 'percent': percent, 'pid': os.getpid(), 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S')}, out)


def full_range(args, info):
    if args.preview_range_explicit:
        raise ValueError('Full-file mode rejects preview range options')
    if not math.isfinite(info.duration_seconds) or not 0 < info.duration_seconds <= 86400:
        raise ValueError('Full-file mode requires a known positive duration of at most 24 hours')
    return 0, info.duration_seconds


def chapter_summary(ffprobe, path, timeout):
    data = np.checked_json([ffprobe, '-v', 'error', '-show_chapters', '-of', 'json', str(path)], timeout=timeout)
    return [(round(float(c['start_time']), 6), round(float(c['end_time']), 6), c.get('tags', {})) for c in data.get('chapters', [])]


def pipe_encode(producer_command, consumer_command, seconds, timeout, stall, guard=None):
    """OS pipe supplies backpressure; Python never buffers video frames."""
    producer = consumer = None
    events = queue.Queue()
    logs = []
    summary = None
    progress = TerminalProgress('Streaming HDR + encoding')
    started = advanced = time.monotonic()
    last = {'producer': -1.0, 'consumer': -1.0}
    heartbeat = 0
    def read(label, stream):
        try:
            for line in iter(stream.readline, b''):
                events.put((label, line.decode('utf-8', errors='replace').strip()))
        finally:
            events.put((label, None))
    try:
        producer = subprocess.Popen(producer_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        consumer = subprocess.Popen(consumer_command, stdin=producer.stdout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        producer.stdout.close()
        for label, stream in (('producer', producer.stderr), ('consumer', consumer.stdout)):
            threading.Thread(target=read, args=(label, stream), daemon=True).start()
        finished = set()
        while len(finished) < 2 or producer.poll() is None or consumer.poll() is None:
            if guard:
                guard()
            # Prefer the encoder error when it closes the pipe and causes a
            # secondary producer broken-pipe error.
            for label, process in (('consumer', consumer), ('producer', producer)):
                if process.poll() not in (None, 0):
                    error = EncoderFailure if label == 'consumer' else RuntimeError
                    raise error(f'{label} exited {process.returncode}; ' + '\n'.join(logs[-12:]))
            now = time.monotonic()
            if guard and now - heartbeat >= 15:
                heartbeat = now
                percent = max(0, last['consumer']) * .8
                guard.status(percent)
                print(f'STATUS: encoding {percent:.2f}% overall; elapsed {(now-started)/60:.1f} min; originals protected', flush=True)
            if now - started > timeout or now - advanced > stall:
                raise RuntimeError('Streaming pipeline timed out or stopped advancing; partial retained')
            try:
                label, line = events.get(timeout=.2)
            except queue.Empty:
                continue
            if line is None:
                finished.add(label)
                continue
            logs.append(f'{label}: {line}')
            logs = logs[-100:]
            value = np.progress(line, seconds)
            if value is not None:
                if value > last[label]:
                    last[label] = value
                    advanced = now
                if label == 'consumer':
                    progress.update(min(80, value * .8))
            elif line.startswith('MUXMENDER_DV_PREVIEW='):
                summary = json.loads(line.split('=', 1)[1])
            elif line and not line.startswith(('frame=', 'fps=', 'bitrate=', 'total_size=', 'out_time', 'dup_frames=', 'drop_frames=', 'speed=', 'progress=', 'stream_', '[')):
                print(f'{label}: {line}', flush=True)
        if not summary or not summary.get('ok'):
            raise RuntimeError('Native producer did not confirm successful completion')
        return summary
    finally:
        for process in (consumer, producer):
            if process is not None and process.poll() is None:
                mm.stop_process_tree(process)
        for process in (consumer, producer):
            if process is not None:
                process.wait(timeout=10)
                for stream in (process.stdout, process.stderr):
                    if stream and not stream.closed:
                        stream.close()


def source_stream_packets(ffprobe, source, kind, start, seconds):
    data = np.checked_json([ffprobe, '-v', 'error', '-select_streams', kind, '-read_intervals',
        f'{max(0, start - 30):g}%{start + seconds + 5:g}', '-show_packets', '-show_data_hash', 'sha256',
        '-show_entries', 'packet=stream_index,pts_time,duration_time,data_hash', '-of', 'json', str(source)])
    selected = []
    for packet in data.get('packets', []):
        pts = float(packet.get('pts_time', '-inf'))
        if start <= pts < start + seconds:
            packet = dict(packet)
            packet['pts_time'] = f'{pts - start:.6f}'
            selected.append(packet)
    return selected


def run(args, source):
    directory = None
    full = getattr(args, 'full_file_streaming', False)
    report = {'status': 'initializing', 'source': str(source), 'scope': '1..60s streaming HDR PQ; Dolby Vision metadata not retained',
              'lossless_disk_intermediates': False, 'requested_hardware': args.hardware,
              'preview_start': args.preview_start, 'preview_seconds': args.preview_seconds}
    try:
        if not math.isfinite(args.max_runtime_hours) or not 0 < args.max_runtime_hours <= 72:
            raise ValueError('Runtime limit must be finite, greater than 0 and at most 72 hours')
        np.validate_options(args, source, max_seconds=60)
        for tool in (args.ffmpeg, args.ffprobe):
            if not shutil.which(tool):
                raise RuntimeError(f'Missing {tool}; run --check-dependencies first')
        helper = args.d3d11_helper.resolve()
        help_result = subprocess.run([str(helper), '--help'], capture_output=True, text=True, timeout=15)
        if help_result.returncode or '--stream-output' not in help_result.stdout:
            raise RuntimeError('Native helper lacks streaming support; rebuild native runtime')
        if full and '--full-file' not in help_result.stdout:
            raise RuntimeError('Native helper lacks full-file support; rebuild native runtime')
        info = mm.probe(source, args.ffprobe)
        if info.dolby_vision_profile != 5 or info.dolby_vision_el_present:
            raise ValueError('Streaming currently accepts only single-layer Dolby Vision profile 5')
        # Native seek is relative to stream start; reject unvalidated offsets.
        stream_info = np.checked_json([args.ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=start_time', '-of', 'json', str(source)])
        if float(stream_info['streams'][0].get('start_time', '0')) != 0:
            raise ValueError('Nonzero source video start time needs separate alignment validation')
        available = mm.ffmpeg_encoder_names(args.ffmpeg)
        try:
            selection = mm.select_encoder('hevc', args.hardware, available, mm.gpu_vendors())
        except mm.HardwareRequirementError as exc:
            if args.execute and np.allow_cpu(args, str(exc), 'libx265' in available, args.hardware):
                retry = copy.copy(args)
                retry.hardware = 'cpu'
                retry.hardware_fallback = 'never'
                return run(retry, source)
            raise
        if selection.vendor == 'cpu' and args.hardware != 'cpu':
            raise RuntimeError('No GPU selected; choose CPU explicitly if wanted')
        report['encoder'] = selection.encoder
        start, seconds = full_range(args, info) if full else (args.preview_start, args.preview_seconds)
        if full:
            report.update(scope='full-file HDR PQ; Dolby Vision metadata not retained', preview_start=0, preview_seconds=seconds)
        print(f'PLAN: streaming {seconds:g}s from {start:g}s, {info.width}x{info.height}, {selection.label}; HDR PQ, audio/subtitle copy', flush=True)
        if not args.execute:
            print('DRY RUN: no GPU initialized, no output created. No lossless disk intermediates.')
            return 0
        before = source.stat()
        np.stage([str(helper.with_name('muxmender-color-test.exe'))], 1, timeout=30, stall=0)
        clean_info = replace(info, dolby_vision=False)
        if selection.hardware:
            try:
                np.stage([args.ffmpeg, '-hide_banner', '-nostdin', '-f', 'lavfi', '-i', 'testsrc2=size=256x144:rate=24',
                          '-frames:v', '24', *mm.encoder_options('hevc', args.quality, clean_info, selection.encoder), '-f', 'null', '-'], 1, timeout=30, stall=0)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                raise EncoderFailure(str(exc)) from exc
        parent = args.output_dir.resolve() if args.output_dir else source.parent / 'muxmender-tests'
        parent.mkdir(parents=True, exist_ok=True)
        reserve = 2 * 1024**3 if full else 1024**3
        required = 2 * info.size_bytes + reserve if full else reserve
        if shutil.disk_usage(parent).free < required:
            raise RuntimeError(f'Insufficient space: require {required/1024**3:.1f} GiB for retained compressed outputs and reserve')
        directory = parent / (('stream-full-' if full else 'stream-test-') + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        directory.mkdir(exist_ok=False)
        guard = RunGuard(directory, reserve)
        guard.status(0)
        video = directory / 'encoded-video.mkv'
        output = directory / ('episode-hevc.mkv' if full else 'preview-hevc.mkv')
        print(f'RUN DIRECTORY: {directory}', flush=True)
        print(f'To stop safely, create an empty file named STOP in that directory. Originals and partials remain.', flush=True)
        range_args = ['--full-file'] if full else ['--start', f'{start:g}', '--seconds', f'{seconds:g}']
        producer = [str(helper), '--input', str(source), '--stream-output', '--hdr-preview', *range_args, '--progress-machine']
        consumer = np.encode_command(args.ffmpeg, 'pipe:0', video, clean_info, selection.encoder, args.quality)
        consumer[consumer.index('-i'):consumer.index('-i')] = ['-threads', '2']
        report['producer_command'] = producer
        report['encoder_command'] = consumer
        native_result = pipe_encode(producer, consumer, seconds, timeout=min(args.max_runtime_hours * 3600, max(180, seconds * 15)), stall=max(40, args.hardware_stall_timeout), guard=guard)
        report['native'] = native_result
        guard.phase = 'copying audio/subtitles'
        guard.status(80)
        remux = full_remux_command(args.ffmpeg, source, video, output) if full else np.remux_command(args.ffmpeg, source, video, output, start, seconds)
        np.stage(remux, seconds, 80, 10, timeout=max(120, seconds * 2), stall=60, guard=guard)
        guard.phase = 'validating'
        guard.status(90)
        guard()
        check_timeout = max(60, min(7200, seconds * 2))
        if full and chapter_summary(args.ffprobe, source, check_timeout) != chapter_summary(args.ffprobe, output, check_timeout):
            raise RuntimeError('Chapter timestamps or metadata changed')
        actual = mm.probe(output, args.ffprobe)
        if (actual.width, actual.height, actual.color_primaries, actual.color_transfer, actual.color_space) != (info.width, info.height, 'bt2020', 'smpte2084', 'bt2020nc'):
            raise RuntimeError('Resolution/color verification failed')
        if actual.video_codec != 'hevc' or actual.bit_depth != 10 or actual.audio_codecs != info.audio_codecs or actual.subtitle_codecs != info.subtitle_codecs:
            raise RuntimeError('Codec/bit-depth or audio/subtitle stream layout changed')
        if np.packet_signatures(args.ffprobe, video, 'v', timeout=check_timeout) != np.packet_signatures(args.ffprobe, output, 'v', timeout=check_timeout):
            raise RuntimeError('Compressed video packets/timestamps changed during stream copy')
        for kind in ('a', 's'):
            guard()
            original_packets = np.packet_signatures(args.ffprobe, source, kind, timeout=check_timeout) if full else source_stream_packets(args.ffprobe, source, kind, start, seconds)
            if original_packets != np.packet_signatures(args.ffprobe, output, kind, timeout=check_timeout):
                raise RuntimeError(f'{kind}: original packet hashes/timestamps differ after clip alignment')
        guard()
        src = np.packet_summary(args.ffprobe, source, None if full else np.comparison_window(start, seconds), timeout=check_timeout)
        dst = np.packet_summary(args.ffprobe, output, timeout=check_timeout)
        src_count, src_bytes = np.video_payload(src) if full else np.video_payload(src, start, start + seconds)
        dst_count, dst_bytes = np.video_payload(dst)
        if src_count != dst_count or dst_count != native_result['frames'] or not np.matching_timeline(src, dst, start, float('inf') if full else start + seconds):
            raise RuntimeError('Frame count or presentation timeline does not match original interval')
        guard.phase = 'full decode verification'
        guard.status(95)
        np.stage([args.ffmpeg, '-v', 'error', '-nostdin', '-xerror', '-i', str(output), '-f', 'null', '-'], seconds, timeout=max(120, seconds * 5), stall=0, guard=guard)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('Source size/mtime changed externally during test')
        saving = (1 - dst_bytes / src_bytes) * 100
        report.update(status='verified-full-file' if full else 'verified-streaming-test', output=str(output), original_stat_unchanged=True,
            width=actual.width, height=actual.height, audio_subtitle_packets_unchanged=True,
            source_video_bytes=src_bytes, output_video_bytes=dst_bytes, video_payload_saving_percent=saving,
            matching_frames=dst_count, min_savings_met=saving >= args.min_savings,
            quality_note='No lossless quality reference retained. Packet/decode validation is not proof of perceptually identical quality; review playback.')
        guard.phase = report['status']
        guard.status(100)
        print(f'VERIFIED: {output}\nVideo-payload saving: {saving:.2f}% for this interval only\nMUXMENDER_PROGRESS=100', flush=True)
        return 0
    except EncoderFailure as exc:
        report.update(status='encoder-failed', error=str(exc))
        if selection.hardware and np.allow_cpu(args, str(exc), 'libx265' in available, selection.vendor):
            retry = copy.copy(args)
            retry.hardware = 'cpu'
            retry.hardware_fallback = 'never'
            print('Restarting with explicitly authorized CPU encoding in a NEW directory; failed GPU output retained.', flush=True)
            return run(retry, source)
        print(f'FAILED: {exc}. Originals untouched; partials retained.', flush=True)
        return 4
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        report.update(status='failed', error=str(exc))
        print(f'FAILED: {exc}. Originals untouched; partials retained.', flush=True)
        return 4
    except KeyboardInterrupt:
        report.update(status='cancelled')
        raise
    finally:
        if directory:
            if report['status'].startswith(('failed', 'encoder-failed', 'cancelled')):
                guard.phase = report['status']
                guard.status(None)
            with (directory / 'validation.json').open('x', encoding='utf-8') as stream:
                json.dump(report, stream, indent=2)
            print(f'Validation report: {directory / "validation.json"}', flush=True)
