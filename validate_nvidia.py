"""Validate NVIDIA with generated fixtures and optional, separately saved samples."""
import argparse
from collections import deque
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid

import job_tracking as jobs
import muxmender as mm
import nvidia_validation
import nvidia_mux
from mux_integrity import startup_audio_lead, MAX_STARTUP_AUDIO_LEAD


def find_tool(name, explicit=None):
    if explicit:
        found = shutil.which(explicit)
        if not found:
            raise ValueError(f'{name} not found at {explicit}')
        return found
    found = shutil.which(name)
    if found:
        return found
    # Read known installation locations only. Never install or alter PATH.
    packages = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft/WinGet/Packages'
    candidates = sorted(packages.glob(f'*FFmpeg*/*/bin/{name}.exe')) if packages.is_dir() else []
    if len(candidates) == 1:
        return str(candidates[0])
    raise ValueError(f'Specify --{name} PATH: no unambiguous installed {name} was found.')


def first_video(data):
    videos = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
    if len(videos) != 1:
        raise ValueError('Validation requires exactly one video stream.')
    return videos[0]


def validate_source(data, kind):
    video = first_video(data)
    description = json.dumps(data).lower()
    if 'dovi' in description or 'dolby vision' in description:
        raise ValueError('Dolby Vision is blocked: NVIDIA preservation has not been validated.')
    expected = ('bt709', 'bt709') if kind == 'SDR' else ('bt2020', 'smpte2084')
    if (video.get('color_primaries'), video.get('color_transfer')) != expected:
        raise ValueError(f'{kind} sample needs explicit {expected[0]}/{expected[1]} tags; unknown color is not assumed.')
    if video.get('color_range') not in ('tv', 'pc') or video.get('color_space') not in ('bt709', 'bt2020nc'):
        raise ValueError('Known color range and matrix are required.')
    if video.get('pix_fmt') not in ('yuv420p', 'yuv420p10le'):
        raise ValueError('This validation route supports 4:2:0 8-bit or 10-bit video only.')
    if kind == 'HDR' and video.get('pix_fmt') != 'yuv420p10le':
        raise ValueError('HDR validation requires 10-bit input.')
    if video.get('field_order') not in (None, 'unknown', 'progressive'):
        raise ValueError('Interlaced video needs separate validation; no deinterlacing is implied.')
    return video


def packet_groups(data, types=('audio', 'subtitle')):
    streams = [s for s in data.get('streams', []) if s.get('codec_type') in types]
    return [[p for p in data.get('packets', []) if p['stream_index'] == s['index']] for s in streams]


def packet_signature(packet):
    return tuple(packet.get(k) for k in ('pts_time', 'duration_time', 'size', 'data_hash'))


def copied_subset(original, sample):
    """Require copied packet bytes/durations and one common timestamp shift."""
    offsets = []
    for before, after in zip(packet_groups(original, ('video', 'audio', 'subtitle')),
                             packet_groups(sample, ('video', 'audio', 'subtitle'))):
        if not after:
            continue
        match = None
        for index, packet in enumerate(before):
            if packet.get('data_hash') != after[0].get('data_hash'):
                continue
            chunk = before[index:index + len(after)]
            if len(chunk) != len(after):
                continue
            if any((a.get('data_hash'), a.get('size'), a.get('duration_time')) !=
                   (b.get('data_hash'), b.get('size'), b.get('duration_time')) for a, b in zip(chunk, after)):
                continue
            shifts = [float(a['pts_time']) - float(b['pts_time']) for a, b in zip(chunk, after)]
            if max(shifts) - min(shifts) <= .003:
                match = shifts[0]
                break
        if match is None:
            raise ValueError('Copied sample packets are not a matching contiguous source interval.')
        offsets.append(match)
    if not offsets or max(offsets) - min(offsets) > .003:
        raise ValueError('Copied sample stream timing does not share one source offset.')
    return offsets[0]


def stream_inventory(data):
    return [(s.get('codec_type'), s.get('codec_name'), s.get('sample_rate'),
             s.get('channels'), s.get('channel_layout'), s.get('disposition'),
             {k: s.get('tags', {}).get(k) for k in ('language', 'title', 'filename', 'mimetype')},
             s.get('extradata_hash') if s.get('codec_type') == 'attachment' else None)
            for s in data['streams'] if s.get('codec_type') != 'video']


def disposition_options(data):
    """Prevent FFmpeg from inventing a default audio/subtitle selection."""
    options = []
    for index, stream in enumerate(data['streams']):
        flags = '+'.join(k for k, v in stream.get('disposition', {}).items() if v)
        options += [f'-disposition:{index}', flags or '0']
    return options


def static_metadata(frame):
    return {s['side_data_type']: {k: v for k, v in s.items() if k != 'side_data_type'}
            for s in frame.get('side_data_list', [])
            if s.get('side_data_type') in ('Mastering display metadata', 'Content light level metadata')}


def metadata_equal(left, right):
    if left.keys() != right.keys():
        return False
    for kind, fields in left.items():
        if fields.keys() != right[kind].keys():
            return False
        for key, value in fields.items():
            try:
                if Fraction(str(value)) != Fraction(str(right[kind][key])):
                    return False
            except (ValueError, ZeroDivisionError):
                if value != right[kind][key]:
                    return False
    return True


def compare_sample(before, after, before_frames, after_frames, codec):
    source, output = first_video(before), first_video(after)
    checks = {key: source.get(key) == output.get(key) for key in
              ('width', 'height', 'pix_fmt', 'color_primaries', 'color_transfer', 'color_space',
               'color_range', 'sample_aspect_ratio', 'field_order')}
    checks['codec'] = output.get('codec_name') == codec
    checks['stream_inventory'] = stream_inventory(before) == stream_inventory(after)
    checks['audio_subtitle_packets'] = [[packet_signature(p) for p in group] for group in packet_groups(before)] == [[packet_signature(p) for p in group] for group in packet_groups(after)]
    # Conservative short-sample certification guard, not a universal mux limit.
    # Large audio prefixes can be skipped when Plex seeks to the first video cue.
    lead = startup_audio_lead(after)
    checks['startup_interleaving'] = lead is not None and lead <= MAX_STARTUP_AUDIO_LEAD
    checks['chapters'] = before.get('chapters', []) == after.get('chapters', [])
    checks['frame_count'] = bool(before_frames) and len(before_frames) == len(after_frames)
    progressive = checks['frame_count'] and all(f.get('interlaced_frame') == 0 and f.get('repeat_pict', 0) == 0 for f in before_frames + after_frames)
    checks['progressive_frames'] = progressive
    if source.get('field_order') in (None, 'unknown') and output.get('field_order') == 'progressive':
        checks['field_order'] = progressive
    checks['frame_timing'] = checks['frame_count'] and all(abs(float(a['best_effort_timestamp_time']) - float(b['best_effort_timestamp_time'])) <= .002 for a, b in zip(before_frames, after_frames))
    checks['static_hdr_metadata'] = checks['frame_count'] and all(metadata_equal(static_metadata(a), static_metadata(b)) for a, b in zip(before_frames, after_frames))
    return checks


class Validation:
    def __init__(self, args):
        self.args = args
        self.root = Path(__file__).resolve().parent
        self.directory = self.root / 'reports' / ('nvidia-validation-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        self.directory.mkdir(parents=True, exist_ok=False)
        self.completed = 0
        self.total = 6 + 2 * bool(args.source) + 2 * bool(args.hdr_source)
        self.counter = 0
        self.report = dict(status='running', scope='NVIDIA capability validation on this GPU/driver/FFmpeg build',
                           capabilities=[], results=[], source=str(args.source) if args.source else None,
                           limitations=['Short samples are not full-file or sustained-load validation.',
                                        'No identical visual-quality claim. Playback review is required.',
                                        'Hardware decoding is not tested. Dolby Vision remains blocked.'])
        for mode in ('sdr1080', 'pq1080', 'pq2160'):
            for codec in ('hevc', 'av1'):
                self.capability(mode + '-' + codec, 'not-tested', 'Generated fixture not yet run.')
        for kind in ('SDR', 'HDR'):
            for codec in ('hevc', 'av1'):
                self.capability(kind + ' sample ' + codec.upper(), 'not-tested', 'No real sample validated yet.')
        self.capability('Dolby Vision preservation', 'not-tested', 'Blocked on NVIDIA; AMD-only gate unchanged.')
        self.save()

    def capability(self, label, status, note):
        entry = next((x for x in self.report['capabilities'] if x['label'] == label), None)
        if entry is None:
            entry = dict(label=label)
            self.report['capabilities'].append(entry)
        entry.update(status=status, note=note)

    def save(self):
        # Only our run-owned status report is replaced; media never is.
        temporary = self.directory / 'validation.json.tmp'
        temporary.write_text(json.dumps(self.report, indent=2), encoding='utf-8')
        temporary.replace(self.directory / 'validation.json')

    def guard(self):
        if (self.directory / 'STOP').exists():
            raise KeyboardInterrupt('STOP requested')
        if shutil.disk_usage(self.directory).free < 2 * 1024**3:
            raise RuntimeError('Less than 2 GiB free; all generated files retained.')

    def progress(self, label, percent=None, eta=None):
        jobs.progress(label, self.completed, self.total, percent, eta, self.directory,
                      detail='Overall count is completed tests, not an estimate of remaining time.', unit='tests')

    def command(self, cmd, label, seconds=None, timeout=180):
        self.guard()
        self.counter += 1
        logfile = self.directory / f'{self.counter:02d}-{label}.log'
        self.progress(label)
        print(f'[{self.completed}/{self.total} tests] {label}', flush=True)
        events = queue.Queue()
        started = last_advanced = time.monotonic()
        high = -1.
        output, recent = [], deque(maxlen=12)
        with logfile.open('x', encoding='utf-8') as log:
            log.write(subprocess.list2cmdline([str(x) for x in cmd]) + '\n')
            process = subprocess.Popen([str(x) for x in cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding='utf-8', errors='replace')
            def reader(stream, channel):
                for line in stream:
                    events.put((channel, line))
                events.put((channel, None))
            workers = [threading.Thread(target=reader, args=(stream, channel), daemon=True)
                       for channel, stream in (('out', process.stdout), ('err', process.stderr))]
            for worker in workers:
                worker.start()
            ended = set()
            try:
                while len(ended) < 2 or process.poll() is None:
                    self.guard()
                    now = time.monotonic()
                    if now - started > timeout or (seconds and now - last_advanced > 45):
                        raise TimeoutError(label + ': timeout/no advancing media time; partials retained.')
                    try:
                        channel, line = events.get(timeout=.2)
                    except queue.Empty:
                        continue
                    if line is None:
                        ended.add(channel)
                        continue
                    log.write(line)
                    log.flush()
                    if channel == 'out':
                        output.append(line)
                    else:
                        recent.append(line)
                    if seconds and line.startswith('out_time_us='):
                        try:
                            value = max(0, min(99, float(line.split('=')[1]) / (seconds * 10000)))
                        except ValueError:
                            continue
                        if value > high:
                            high = value
                            last_advanced = now
                            eta = (now-started)*(100-value)/value if value > 0 else None
                            self.progress(label, value, eta)
                            print(f'  {label}: {value:.1f}% | elapsed {now-started:.0f}s', flush=True)
                code = process.wait(timeout=5)
                if code:
                    raise RuntimeError(f'{label} exited {code}: ' + ''.join(recent)[-1800:])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                for worker in workers:
                    worker.join(timeout=2)
                process.stdout.close()
                process.stderr.close()
        self.progress(label, 100)
        return ''.join(output), time.monotonic() - started

    def probe(self, path, label, packets=False, frames=False, interval=None):
        cmd = [self.args.ffprobe, '-v', 'error']
        if interval:
            cmd += ['-read_intervals', interval]
        if frames:
            cmd += ['-select_streams', 'v:0', '-show_frames', '-show_entries',
                    'frame=best_effort_timestamp_time,pix_fmt,color_primaries,color_transfer,color_space,color_range,interlaced_frame,top_field_first,repeat_pict,side_data_list']
        else:
            cmd += ['-show_streams', '-show_format', '-show_chapters', '-show_data_hash', 'sha256']
            if packets:
                cmd += ['-show_packets']
        cmd += ['-of', 'json', str(path)]
        data, _ = self.command(cmd, label)
        return json.loads(data)

    def decode(self, path, label, seconds):
        self.command([self.args.ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-xerror',
                      '-err_detect', 'explode', '-i', path, '-map', '0:v', '-map', '0:a?',
                      '-progress', 'pipe:1', '-nostats', '-f', 'null', '-'], label, seconds)

    def sample(self, path, kind):
        source = path.resolve(strict=True)
        if not source.is_file():
            raise ValueError('Provide a single media file, not a directory.')
        original_stat = (source.stat().st_size, source.stat().st_mtime_ns)
        data = self.probe(source, kind + '-source-info')
        validate_source(data, kind)
        duration = float(data.get('format', {}).get('duration', 0))
        if not math.isfinite(duration) or duration < self.args.start + self.args.seconds + 15:
            raise ValueError('Source is too short for the selected sample interval plus a 15-second margin.')
        if abs(float(first_video(data).get('start_time', 0))) > .001:
            raise ValueError('Nonzero source video start times need separate validation.')
        estimated = original_stat[0] / duration * self.args.seconds * 8 + 2 * 1024**3
        if shutil.disk_usage(self.directory).free < estimated:
            raise ValueError('Insufficient free space for retained sample/reference/output files.')
        sample = self.directory / (kind.lower() + '-reference.mkv')
        ff = [self.args.ffmpeg, '-hide_banner', '-nostdin', '-n']
        self.command(ff + ['-ss', str(self.args.start), '-i', source, '-t', str(self.args.seconds),
                          '-map', '0', '-map_metadata', '0', '-map_chapters', '0', '-c', 'copy',
                          *disposition_options(data), '-avoid_negative_ts', 'make_zero', '-progress', 'pipe:1', '-nostats', sample],
                     kind + '-save-reference', self.args.seconds)
        before = self.probe(sample, kind + '-reference-packets', packets=True)
        validate_source(before, kind)
        frames = self.probe(sample, kind + '-reference-frames', frames=True)['frames']
        if not frames or 'dolby vision' in json.dumps(frames).lower() or 'dovi' in json.dumps(frames).lower():
            raise ValueError('Sample has no video frames or contains blocked Dolby Vision metadata.')
        if any(f.get('interlaced_frame') != 0 or f.get('repeat_pict', 0) != 0 for f in frames):
            raise ValueError('Sample is not confirmed progressive video; no field conversion is allowed.')
        if any('dynamic' in s.get('side_data_type', '').lower() and 'hdr' in s.get('side_data_type', '').lower()
               for f in frames for s in f.get('side_data_list', [])):
            raise ValueError('Dynamic HDR metadata requires a separately validated preservation path.')
        actual_duration = float(before['format']['duration'])
        if not 0 < actual_duration <= self.args.seconds + 15:
            raise ValueError('Keyframe-aligned reference exceeds the allowed sample bound.')
        self.decode(sample, kind + '-reference-decode', actual_duration)
        original_packets = self.probe(source, kind + '-source-packets', packets=True,
                                     interval=f'{max(0, self.args.start-30)}%+{self.args.seconds+90}')
        if stream_inventory(original_packets) != stream_inventory(before):
            raise ValueError('Reference extraction changed the non-video stream inventory.')
        offset = copied_subset(original_packets, before)
        info = mm.probe(sample, self.args.ffprobe)
        info.recommendation = 'transcode'
        reference_hash = hashlib.sha256(sample.read_bytes()).hexdigest()
        for codec in ('hevc', 'av1'):
            label = kind + ' sample ' + codec.upper()
            entry = dict(test=label, source=str(source), reference=str(sample), source_offset=offset,
                         requested_seconds=self.args.seconds, actual_seconds=actual_duration)
            self.report['results'].append(entry)
            try:
                output = self.directory / (kind.lower() + '-' + codec + '-sample.mkv')
                cmd = mm.build_ffmpeg_command(sample, output, info, codec, 'balanced', self.args.ffmpeg, codec + '_nvenc', 'keep')
                cmd[cmd.index('-i'):cmd.index('-i')] = ['-copyts']
                cmd[-1:-1] = ['-gpu', str(self.args.gpu), '-fps_mode', 'passthrough',
                              *disposition_options(before), '-avoid_negative_ts', 'disabled', '-progress', 'pipe:1', '-nostats']
                video_stage = self.directory / (kind.lower() + '-' + codec + '-video-stage.mkv')
                cmd[-1] = str(video_stage)
                cmd = nvidia_mux.video_stage_command(cmd)
                _, elapsed = self.command(cmd, kind + '-' + codec + '-encode', actual_duration)
                mux_cmd = nvidia_mux.finalize_command(video_stage, sample, output, before, self.args.ffmpeg)
                mux_cmd[-1:-1] = ['-progress', 'pipe:1', '-nostats']
                _, mux_elapsed = self.command(mux_cmd, kind + '-' + codec + '-finalize', actual_duration)
                entry.update(video_stage=str(video_stage), mux_seconds=mux_elapsed)
                after = self.probe(output, kind + '-' + codec + '-packets', packets=True)
                output_frames = self.probe(output, kind + '-' + codec + '-frames', frames=True)['frames']
                checks = compare_sample(before, after, frames, output_frames, codec)
                self.decode(output, kind + '-' + codec + '-decode', actual_duration)
                checks['full_sample_decode'] = True
                checks['original_size_mtime_unchanged'] = (source.stat().st_size, source.stat().st_mtime_ns) == original_stat
                checks['reference_sha256_unchanged'] = hashlib.sha256(sample.read_bytes()).hexdigest() == reference_hash
                checks['reference_packets_match_source'] = True
                failed = [name for name, passed in checks.items() if not passed]
                entry.update(checks=checks, output=str(output), passed=not failed,
                             encode_seconds=elapsed, speed_x=actual_duration/elapsed,
                             reference_bytes=sample.stat().st_size, output_bytes=output.stat().st_size,
                             size_change_percent=100*(output.stat().st_size/sample.stat().st_size-1),
                             static_hdr_present=any(static_metadata(f) for f in frames))
                note = ', '.join(failed) if failed else 'Automated sample checks passed; playback review required.'
                if kind == 'HDR' and not entry['static_hdr_present']:
                    note += ' No static HDR metadata was present to test.'
                self.capability(label, 'failed' if failed else 'passed', note)
            except Exception as exc:
                entry.update(passed=False, error=str(exc))
                self.capability(label, 'failed', str(exc))
                print(f'FAILED: {label}: {exc}', flush=True)
            self.completed += 1
            self.save()
            self.progress(label + ' checked')
        self.report['original_stat_unchanged'] = (source.stat().st_size, source.stat().st_mtime_ns) == original_stat

    def run(self):
        try:
            self.args.ffmpeg = find_tool('ffmpeg', self.args.ffmpeg)
            self.args.ffprobe = find_tool('ffprobe', self.args.ffprobe)
            self.report['tools'] = dict(ffmpeg=self.args.ffmpeg, ffprobe=self.args.ffprobe)
            def fixture_progress(label, percent):
                self.guard()
                if label.endswith('-complete'):
                    self.completed += 1
                self.progress('Generated: ' + label, percent)
            nvidia_validation.main(['--ffmpeg', self.args.ffmpeg, '--ffprobe', self.args.ffprobe,
                                    '--gpu', str(self.args.gpu)], self.directory/'fixtures', fixture_progress, self.guard)
            fixture = json.loads((self.directory/'fixtures'/'validation.json').read_text(encoding='utf-8'))
            self.report['environment'] = {k: fixture.get(k) for k in ('python', 'gpu', 'ffmpeg', 'ffprobe')}
            self.report['gpu_index'] = self.args.gpu
            for result in fixture['results']:
                self.capability(result['test'], 'passed' if result['passed'] else 'failed', result.get('error', 'Generated encode, preservation and software decode checks.'))
            self.report['fixture_report'] = str(self.directory/'fixtures'/'validation.json')
            self.save()
            if not fixture.get('passed'):
                raise ValueError('Generated tests did not all pass. Real-media tests were not started.')
            for kind, path in (('SDR', self.args.source), ('HDR', self.args.hdr_source)):
                if path:
                    try:
                        self.sample(path, kind)
                    except Exception as exc:
                        for codec in ('HEVC', 'AV1'):
                            self.capability(kind + ' sample ' + codec, 'failed', str(exc))
                        raise
            failed = any(c['status'] == 'failed' for c in self.report['capabilities'])
            self.report['status'] = 'failed' if failed else 'verified-samples-awaiting-playback' if self.report['results'] else 'verified-generated-only'
        except KeyboardInterrupt:
            self.report.update(status='cancelled', error='Cancelled; sources and generated files retained.')
        except Exception as exc:
            self.report.update(status='failed', error=str(exc))
            print(f'FAILED: {exc}', flush=True)
        finally:
            self.save()
            self.progress(self.report['status'])
            lines = ['# NVIDIA validation', '', self.report['status'], '',
                     'Validated only on the recorded GPU, driver and FFmpeg build. Playback review is separate.', '',
                     '| Capability | Result | Notes |', '|---|---|---|']
            for c in self.report['capabilities']:
                note = c['note'].replace('|', '/').replace('\n', ' ')
                lines.append(f"| {c['label']} | {c['status']} | {note} |")
            lines += ['', '## Samples', '']
            for r in self.report['results']:
                lines.append(f"- {r['test']}: {r.get('output', 'No accepted output')}")
                if 'speed_x' in r:
                    lines.append(f"  {r['speed_x']:.2f}x; reference {r['reference_bytes']:,} bytes; output {r['output_bytes']:,} bytes; size change {r['size_change_percent']:+.1f}%. Passed: {r['passed']}.")
            lines += ['', *self.report['limitations'], '', 'Detailed evidence: validation.json and numbered logs in this folder.']
            (self.directory/'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
            print('\nNVIDIA validation results:', flush=True)
            for c in self.report['capabilities']:
                print(f"  {c['status'].upper():10} {c['label']}", flush=True)
            print(f'Report: {self.directory / "REPORT.md"}', flush=True)
        return 130 if self.report['status'] == 'cancelled' else 1 if self.report['status'] == 'failed' else 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path, help='optional SDR file for a separately saved sample')
    parser.add_argument('--hdr-source', type=Path, help='optional non-Dolby-Vision PQ file')
    parser.add_argument('--start', type=float, default=300, help='seek near this second (default 300)')
    parser.add_argument('--seconds', type=float, default=30, help='requested sample length, 1–60 seconds (default 30)')
    parser.add_argument('--gpu', type=int, default=0, help='NVIDIA device index (default 0); actual encodes validate it')
    parser.add_argument('--ffmpeg')
    parser.add_argument('--ffprobe')
    args = parser.parse_args(argv)
    if not math.isfinite(args.start) or args.start < 0 or not math.isfinite(args.seconds) or not 1 <= args.seconds <= 60 or args.gpu < 0:
        parser.error('start must be nonnegative, seconds must be 1–60, and GPU index nonnegative')
    return args


def cli():
    args = parse_args()
    return jobs.tracked_call(lambda: Validation(args).run(), 'Validate NVIDIA')


if __name__ == '__main__':
    raise SystemExit(cli())
