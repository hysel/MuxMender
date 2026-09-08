"""Validate NVIDIA or Intel generated fixtures; optional, separately saved real-media samples."""
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
import job_tracking
from runtime_support import guard_ordered_mux_memory
import mux_integrity as nvidia_mux
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


def copied_subset(original, sample, decoded_audio=None):
    """Require copied packet bytes/durations and one common timestamp shift."""
    offsets = []
    sample_streams = [s for s in sample.get('streams', []) if s.get('codec_type') in ('video', 'audio', 'subtitle')]
    original_streams = [s for s in original.get('streams', []) if s.get('codec_type') in ('video', 'audio', 'subtitle')]
    def same_duration(a, b, index):
        if a.get('duration_time') == b.get('duration_time'):
            return True
        stream = sample_streams[index]
        source_stream = original_streams[index]
        if stream.get('codec_type') != 'audio' or decoded_audio is None:
            return False
        frames = [f for f in decoded_audio if f.get('stream_index') == stream['index'] and f.get('pts_time') == b.get('pts_time')]
        if len(frames) != 1 or not isinstance(frames[0].get('nb_samples'), int):
            return False
        try:
            rate = int(stream['sample_rate'])
            tick = Fraction(stream['time_base'])
            if rate != int(source_stream['sample_rate']) or tick != Fraction(source_stream['time_base']) or not 0 < tick <= Fraction(1, 1000) or frames[0]['nb_samples'] <= 0:
                return False
            duration = Fraction(frames[0]['nb_samples'], rate)
            allowed = {math.floor(duration/tick)*tick, math.ceil(duration/tick)*tick}
            return Fraction(a['duration_time']) in allowed and Fraction(b['duration_time']) in allowed
        except (KeyError, ValueError, ZeroDivisionError):
            return False
    for stream_index, (before, after) in enumerate(zip(packet_groups(original, ('video', 'audio', 'subtitle')),
                             packet_groups(sample, ('video', 'audio', 'subtitle')))):
        if not after:
            continue
        match = None
        for index, packet in enumerate(before):
            if packet.get('data_hash') != after[0].get('data_hash'):
                continue
            chunk = before[index:index + len(after)]
            if len(chunk) != len(after):
                continue
            if any((a.get('data_hash'), a.get('size')) !=
                   (b.get('data_hash'), b.get('size')) or not same_duration(a, b, stream_index) for a, b in zip(chunk, after)):
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


def repair_av1_hdr_research_ivf(source, destination, mastering):
    from mux_integrity import _repair_av1_hdr_bytes
    source, destination = Path(source), Path(destination)
    if source.stat().st_size > 512 * 1024**2:
        raise ValueError('Research IVF exceeds 512 MiB bound')
    data, report = _repair_av1_hdr_bytes(source.read_bytes(), mastering)
    with destination.open('xb') as output:
        output.write(data)
    return report


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


def av1_quantized_frames(frames):
    """Expected AV1 MDCV precision only; keep all other evidence unchanged."""
    import copy
    result = copy.deepcopy(frames)
    for frame in result:
        for side in frame.get('side_data_list', []):
            if side.get('side_data_type') != 'Mastering display metadata':
                continue
            for field in list(side):
                if field == 'side_data_type':
                    continue
                scale = 256 if field == 'max_luminance' else 16384 if field == 'min_luminance' else 65536
                value = Fraction(str(side[field])) * scale + Fraction(1, 2)
                side[field] = str(Fraction(value.numerator // value.denominator, scale))
    return result


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
        self.hardware = getattr(args, 'hardware', 'nvidia')
        self.vendor_label = mm.VENDOR_LABELS[self.hardware]
        self.root = Path(__file__).resolve().parent.parent
        self.directory = self.root / 'reports' / (self.hardware + '-validation-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        self.directory.mkdir(parents=True, exist_ok=False)
        self.completed = 0
        self.total = 8 + 2 * bool(args.source) + 2 * bool(args.hdr_source)
        self.counter = 0
        self.report = dict(status='running', scope=self.vendor_label + ' capability validation on this GPU/driver/FFmpeg build',
                           capabilities=[], results=[], source=str(args.source) if args.source else None,
                           limitations=['Short samples are not full-file or sustained-load validation.',
                                        'No identical visual-quality claim. Playback review is required.',
                                        'Hardware decoding is not tested. Dolby Vision remains blocked.'])
        for mode in ('sdr1080', 'pq1080', 'pq2160', 'irregular360'):
            for codec in ('hevc', 'av1'):
                self.capability(mode + '-' + codec, 'not-tested', 'Generated fixture not yet run.')
        for kind in ('SDR', 'HDR'):
            for codec in ('hevc', 'av1'):
                self.capability(kind + ' sample ' + codec.upper(), 'not-tested', 'No real sample validated yet.')
        self.capability('Dolby Vision preservation', 'not-tested', 'Blocked in this validator; normal AMD-only gate unchanged.')
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
                    guard_ordered_mux_memory(process, cmd)
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
        try:
            offset = copied_subset(original_packets, before)
        except ValueError:
            decoded, _ = self.command([self.args.ffprobe, '-v', 'error', '-select_streams', 'a', '-show_frames', '-show_entries', 'frame=stream_index,pts_time,nb_samples', '-of', 'json', sample], kind + '-reference-audio-samples')
            offset = copied_subset(original_packets, before, json.loads(decoded).get('frames', []))
            self.report['reference_audio_duration_rounding'] = 'Verified from identical packet bytes, sample counts and unchanged shifted PTS; no tolerance added to video timing.'
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
                selection = mm.select_encoder(codec, self.hardware, mm.ffmpeg_encoder_names(self.args.ffmpeg), mm.gpu_vendors())
                cmd = mm.build_ffmpeg_command(sample, output, info, codec, 'balanced', self.args.ffmpeg, selection.encoder, 'keep')
                cmd[cmd.index('-i'):cmd.index('-i')] = ['-copyts']
                cmd[-1:-1] = (['-gpu', str(self.args.gpu)] if self.hardware == 'nvidia' else []) + ['-fps_mode', 'passthrough',
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
            validate_generated_fixtures(['--ffmpeg', self.args.ffmpeg, '--ffprobe', self.args.ffprobe,
                                    '--gpu', str(self.args.gpu), '--hardware', self.hardware], self.directory/'fixtures', fixture_progress, self.guard)
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
            lines = ['# ' + self.vendor_label + ' validation', '', self.report['status'], '',
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
            print('\n' + self.vendor_label + ' validation results:', flush=True)
            for c in self.report['capabilities']:
                print(f"  {c['status'].upper():10} {c['label']}", flush=True)
            print(f'Report: {self.directory / "REPORT.md"}', flush=True)
        return 130 if self.report['status'] == 'cancelled' else 1 if self.report['status'] == 'failed' else 0


def validate_generated_fixtures(argv=None, run_directory=None, progress_callback=None, guard=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffprobe', required=True)
    parser.add_argument('--gpu', type=int, default=0)
    parser.add_argument('--hardware', choices=('nvidia', 'intel'), default='nvidia')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    run = Path(run_directory) if run_directory else root / 'reports' / (args.hardware + '-fixtures-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
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
        if args.hardware == 'nvidia':
            report['gpu'], _ = command(['nvidia-smi', '--query-gpu=index,name,driver_version,memory.total', '--format=csv'], 'gpu')
        else:
            report['gpu'], _ = command(['powershell', '-NoProfile', '-Command', 'Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,PNPDeviceID,Status | ConvertTo-Json'], 'gpu')
        report['hardware'] = args.hardware
        report['ffmpeg'], _ = command([args.ffmpeg, '-version'], 'ffmpeg-version')
        report['ffprobe'], _ = command([args.ffprobe, '-version'], 'ffprobe-version')
        report['encoders'], _ = command([args.ffmpeg, '-hide_banner', '-encoders'], 'encoders')
        report['vendors'] = mm.gpu_vendors()
        available = mm.ffmpeg_encoder_names(args.ffmpeg)
        subtitles = run / 'generated.srt'
        with subtitles.open('x', encoding='utf-8') as stream:
            stream.write('1\n00:00:00,000 --> 00:00:01,500\nGenerated hardware validation fixture\n')
        metadata = run / 'generated.ffmeta'
        with metadata.open('x', encoding='utf-8') as stream:
            stream.write(';FFMETADATA1\ntitle=Generated validation\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=2000\ntitle=Generated chapter\n')
        for mode, size, pixel, primaries, transfer, space in [
            ('irregular360', '640x360', 'yuv420p', 'bt709', 'bt709', 'bt709'),
            ('sdr1080', '1920x1080', 'yuv420p', 'bt709', 'bt709', 'bt709'),
            ('pq1080', '1920x1080', 'yuv420p10le', 'bt2020', 'smpte2084', 'bt2020nc'),
            ('pq2160', '3840x2160', 'yuv420p10le', 'bt2020', 'smpte2084', 'bt2020nc'),
        ]:
            source = run / (mode + '-generated.mkv')
            generate = [args.ffmpeg, '-hide_banner', '-nostdin', '-n', '-f', 'lavfi', '-i', f'testsrc2=size={size}:rate=24:duration=2,format={pixel},setparams=range=limited:color_primaries={primaries}:color_trc={transfer}:colorspace={space}', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=2', '-i', subtitles, '-f', 'ffmetadata', '-i', metadata, '-map', '0:v', '-map', '1:a', '-map', '2:s', '-map_metadata', '3', '-map_chapters', '3', '-c:v', 'libx265', '-preset', 'ultrafast', '-x265-params', f'lossless=1:colorprim={primaries}:transfer={transfer}:colormatrix={space}', '-pix_fmt', pixel, '-color_primaries', primaries, '-color_trc', transfer, '-colorspace', space, '-color_range', 'tv', '-c:a', 'pcm_s16le', '-c:s', 'srt', '-progress', 'pipe:1', '-nostats', source]
            if mode == 'irregular360':
                generate[-1:-1] = ['-vf', r'setpts=(N+4*eq(N\,47))/(24*TB)', '-fps_mode', 'passthrough']
            command(generate, mode + '-generate', 2)
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
                    selection = mm.select_encoder(codec, args.hardware, available, report['vendors'])
                    output = run / (label + '.mkv')
                    cmd = mm.build_ffmpeg_command(source, output, info, codec, 'balanced', args.ffmpeg, selection.encoder, 'keep',
                        experimental_av1_hdr=selection.encoder == 'av1_qsv' and info.hdr)
                    cmd[-1:-1] = (['-gpu', str(args.gpu)] if args.hardware == 'nvidia' else []) + ['-progress', 'pipe:1', '-nostats']
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
        report['passed'] = len(report['results']) == 8 and all(e['passed'] for e in report['results'])
    except Exception as exc:
        report.update(passed=False, error=str(exc))
        print(str(exc), flush=True)
    finally:
        with (run / 'validation.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
        update('Fixture validation complete' if report.get('passed') else 'Fixture validation failed', 100)
        print(f'Report: {run / "validation.json"}', flush=True)
    return 0 if report.get('passed') else 1

def verify_full_file(args):
    def read_live_json(path):
        # Windows may briefly deny reads during an atomic status-file replacement.
        for attempt in range(20):
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (PermissionError, json.JSONDecodeError):
                if attempt == 19:
                    raise
                time.sleep(0.1)
    v = sys.modules[__name__]
    run = args.run.resolve()
    evidence = run / ('full-verification-' + time.strftime('%H%M%S') + '-' + uuid.uuid4().hex[:8])
    evidence.mkdir(exist_ok=False)
    source = args.source.resolve()
    baseline = (source.stat().st_size, source.stat().st_mtime_ns)
    baseline_path = run / 'source-baseline.json'
    if baseline_path.exists():
        captured = json.loads(baseline_path.read_text(encoding='utf-8'))
        if Path(captured['source']).resolve() != source:
            raise ValueError('Pre-encode baseline source mismatch')
        baseline = (captured['size'], captured['mtime_ns'])
    kind = 'HDR' if getattr(args, 'hdr', False) else 'SDR'
    report = dict(status='running', source=str(source), color_scope=kind, checks={},
                  source_stat_capture='Before encoding' if baseline_path.exists() else 'During encoding, before verification',
                  limitations=['Playback and visual-quality review required.',
                               'This result covers only its reported color scope and encoder/codec; not Dolby Vision.'])
    def save():
        (evidence / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    def guard(start, limit=1800):
        if (run / 'STOP').exists():
            raise RuntimeError('STOP requested; all files retained.')
        if time.monotonic() - start > limit:
            raise RuntimeError('Diagnostic time limit reached; all files retained.')
        if shutil.disk_usage(run).free < 2 * 1024**3:
            raise RuntimeError('Less than 2 GiB free; diagnostic stopped.')
    def command(argv, label, completed):
        jobs.progress(label, completed, 6, directory=evidence)
        print(label, flush=True)
        started = time.monotonic()
        output = evidence / (label + '.json')
        with output.open('xb') as out, (evidence / (label + '.log')).open('xb') as err:
            process = subprocess.Popen(argv, stdout=out, stderr=err)
            try:
                last = started
                while process.poll() is None:
                    guard(started)
                    if time.monotonic() - last >= 15:
                        print(f'{label}: {time.monotonic()-started:.0f}s elapsed', flush=True)
                        last = time.monotonic()
                    time.sleep(.5)
                if process.returncode:
                    raise RuntimeError(f'{label} failed: see retained log')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        return output
    save()
    try:
        jobs.progress('Waiting for full-file encode and mux', 0, 6, directory=evidence)
        started = time.monotonic()
        while not (run / 'cli-report.json').exists():
            guard(started, 7200)
            state = read_live_json(args.job)
            if state.get('state') in ('failed', 'cancelled'):
                raise RuntimeError('Encoding job did not complete successfully.')
            time.sleep(2)
        cli = read_live_json(run / 'cli-report.json')
        if cli.get('errors') or len(cli.get('files', [])) != 1 or cli['files'][0].get('status') != 'complete':
            raise RuntimeError('Normal CLI did not accept exactly one output.')
        entry = cli['files'][0]
        output = Path(entry['output'])
        comparison_output = output
        if entry.get('playback_command'):
            if not entry.get('playback_verification') or not all(entry['playback_verification'].values()):
                raise RuntimeError('Compatibility output has no successful preservation verification')
            cmd = entry['playback_command']
            comparison_output = Path(cmd[cmd.index('-i') + 1])
        codec = cli.get('target_codec', 'hevc')
        if codec not in ('hevc', 'av1'):
            raise RuntimeError('Full verification requires HEVC or AV1 output')
        av1_research = getattr(args, 'experimental_av1_hdr', False)
        if av1_research and (kind != 'HDR' or codec != 'av1' or
                entry.get('encoder', {}).get('encoder') != 'av1_qsv' or not entry.get('av1_hdr_repair')):
            raise RuntimeError('AV1 HDR verification requires explicit Intel repair evidence')
        if kind == 'HDR' and codec != 'hevc' and not av1_research:
            raise RuntimeError('AV1 HDR requires the explicit experimental repair verifier')
        report.update(codec=codec, encoder=entry.get('encoder'), comparison_output=str(comparison_output))
        if Path(entry['path']).resolve() != source:
            raise RuntimeError('CLI source does not match verification source.')
        report['output'] = str(output)
        ffprobe, ffmpeg = v.find_tool('ffprobe', getattr(args, 'ffprobe', None)), v.find_tool('ffmpeg', getattr(args, 'ffmpeg', None))
        packets = []
        frames = []
        for index, (label, path) in enumerate((('source', source), ('output', comparison_output))):
            result = command([ffprobe, '-v', 'error', '-show_streams', '-show_format',
                              '-show_chapters', '-show_packets', '-show_data_hash', 'sha256',
                              '-of', 'json', str(path)], label + '-packets', index*2)
            packets.append(json.loads(result.read_text(encoding='utf-8')))
            v.validate_source(packets[-1], kind)
            result = command([ffprobe, '-v', 'error', '-threads', '0', '-select_streams', 'v:0', '-show_frames',
                              '-show_entries', 'frame=best_effort_timestamp_time,interlaced_frame,repeat_pict:frame_side_data',
                              '-of', 'json', str(path)], label + '-frames', index*2+1)
            frames.append(json.loads(result.read_text(encoding='utf-8'))['frames'])
            for frame in frames[-1]:
                for side in frame.get('side_data_list', []):
                    name = side.get('side_data_type', '').lower()
                    if 'dolby' in name or 'dovi' in name or 'smpte2094' in name or ('dynamic' in name and 'hdr' in name):
                        raise RuntimeError('Dynamic HDR requires separate preservation validation')
        comparison_frames = av1_quantized_frames(frames[0]) if av1_research else frames[0]
        checks = v.compare_sample(*packets, comparison_frames, frames[1], codec)
        if av1_research:
            report['metadata_precision'] = 'AV1 MDCV nearest representable units; all other fields exact'
        if kind == 'HDR':
            checks['source_static_hdr_present'] = bool(frames[0]) and any(v.static_metadata(f) for f in frames[0])
        if comparison_output != output:
            final_probe = v.mm.run_json([ffprobe, '-v', 'error', '-show_streams', '-show_chapters', '-of', 'json', str(output)])
            plan_data = entry['playback_plan']
            plan = nvidia_mux.playback_plan(packets[1], plan_data['audio_ordinal'], plan_data['subtitle_track'])
            jobs.progress('Verifying final compatibility track mapping', 4, 6, directory=evidence)
            preserved = nvidia_mux.verify_playback_copy(comparison_output, output, packets[1], final_probe, plan, ffprobe)
            checks['final_compatibility_preservation'] = all(preserved.values())
        duration = float(packets[0]['format']['duration'])
        seek_positions = sorted(set((0, min(60, duration*.1), duration/2,
                                     max(duration*.9, duration-60))))
        passed, seek_checks = nvidia_mux.verify_seek_interleaving(output, ffprobe, seek_positions)
        checks['full_file_seek_interleaving'] = passed
        report['seek_checks'] = seek_checks
        command([ffmpeg, '-v', 'error', '-xerror', '-i', str(output),
                 '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'], 'full-output-decode', 4)
        checks['full_video_audio_decode'] = True
        checks['source_size_mtime_unchanged_since_capture'] = baseline == (source.stat().st_size, source.stat().st_mtime_ns)
        report.update(checks=checks, source_bytes=source.stat().st_size, output_bytes=output.stat().st_size,
                      saved_percent=100*(1-output.stat().st_size/source.stat().st_size),
                      duration_seconds=float(packets[0]['format']['duration']),
                      source_frames=len(frames[0]), output_frames=len(frames[1]))
        state = read_live_json(args.job)
        if state.get('finished'):
            report['cli_elapsed_seconds'] = state['finished'] - state['started']
            report['cli_speed_x_including_mux'] = report['duration_seconds'] / report['cli_elapsed_seconds']
        if not all(checks.values()):
            raise RuntimeError('Failed checks: ' + ', '.join(k for k, value in checks.items() if not value))
        report['status'] = 'verified-full-file-awaiting-playback'
        jobs.progress('Full ' + kind + ' ' + codec.upper() + ' checks passed; playback review pending', 6, 6, directory=evidence)
        print(json.dumps(report, indent=2), flush=True)
        return 0
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        print(f'FAILED: {exc}', flush=True)
        return 1
    finally:
        save()

def run_av1_hdr_integrated(args, source, destination):
    """Use the audited HDR10 route; publish only after independent full verification."""
    if (args.resolution != 'keep' or args.compatibility_audio != 'preserve'
            or args.hardware_fallback == 'cpu' or args.delete_originals or args.overwrite_output):
        raise ValueError('Intel AV1 HDR requires original resolution/tracks, retained originals and no CPU fallback or overwrite')
    if destination.exists():
        raise ValueError('Output exists; choose a fresh output directory')
    work_parent = destination.parent.parent if args.video_only_folder else destination.parent
    work = work_parent / '.MuxMender-work' / ('av1-hdr-' + uuid.uuid4().hex)
    options = argparse.Namespace(source=source, run=work, execute=args.execute,
                                 ffmpeg=args.ffmpeg, ffprobe=args.ffprobe,
                                 quality=args.quality, min_savings=args.min_savings)
    if av1_hdr_research(options):
        raise RuntimeError(f'Intel AV1 HDR encoding/repair failed; retained evidence: {work}')
    if not args.execute:
        return dict(status='planned', output=str(destination),
                    result='Intel AV1 HDR: repair, full preservation/decode verification, then publication')
    # The verifier accepts an encode-job snapshot even when this function is called
    # by an untracked embedding application. It never waits on its own parent job.
    snapshot = work / 'encode-completed.json'
    snapshot.write_text(json.dumps(dict(state='completed')), encoding='utf-8')
    verify = argparse.Namespace(source=source, run=work, job=snapshot, hdr=True,
                                experimental_av1_hdr=True, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
    if verify_full_file(verify):
        raise RuntimeError(f'Intel AV1 HDR full verification failed; output not published: {work}')
    reports = list(work.glob('full-verification-*/validation.json'))
    if len(reports) != 1:
        raise RuntimeError('Ambiguous full verification evidence; no publication')
    proof = json.loads(reports[0].read_text(encoding='utf-8'))
    if not proof.get('status', '').startswith('verified') or not proof.get('checks') or not all(proof['checks'].values()):
        raise RuntimeError('Incomplete full verification; no publication')
    output = Path(proof['output'])
    destination.parent.mkdir(parents=True, exist_ok=True)
    mm.publish_output(output, destination)
    return dict(status='complete', output=str(destination), output_size_bytes=output.stat().st_size,
                saved_percent=proof['saved_percent'], verification=str(reports[0]),
                recovery_files=[str(work)], result='Intel AV1 HDR repair and full preservation/decode checks passed; playback review recommended')


def av1_hdr_research(args):
    """Separate-output Intel HDR10 experiment. No production gate or source writes."""
    import native_pipeline
    from runtime_support import frame_evidence_percent, TerminalProgress
    source, directory = args.source.resolve(), args.run.resolve()
    ffmpeg, ffprobe = find_tool('ffmpeg', getattr(args, 'ffmpeg', None)), find_tool('ffprobe', getattr(args, 'ffprobe', None))
    quality, minimum = getattr(args, 'quality', 'transparent'), getattr(args, 'min_savings', 5.)
    if quality not in ('transparent', 'balanced', 'compact') or not math.isfinite(minimum) or not 0 <= minimum < 100:
        raise ValueError('Invalid quality or minimum savings')
    info = mm.probe(source, ffprobe)
    probe = mm.run_json([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-show_chapters', '-of', 'json', str(source)])
    video = validate_source(probe, 'HDR')
    if 'intel' not in mm.gpu_vendors() or 'av1_qsv' not in mm.ffmpeg_encoder_names(ffmpeg):
        raise ValueError('Intel AV1 capability unavailable; no fallback')
    if not math.isfinite(info.duration_seconds) or not 0 < info.duration_seconds <= 14400:
        raise ValueError('Research duration must be known and at most four hours')
    print(f'AV1 HDR RESEARCH: {source}; exact {info.width}x{info.height}; separate output {directory}', flush=True)
    if not args.execute:
        return 0
    directory.mkdir(parents=True, exist_ok=False)
    baseline = source.stat()
    (directory/'source-baseline.json').write_text(json.dumps(dict(source=str(source), size=baseline.st_size, mtime_ns=baseline.st_mtime_ns)), encoding='utf-8')
    report = dict(target_codec='av1', mode='experimental-research', files=[], errors=[])
    entry = dict(path=str(source), encoder=dict(encoder='av1_qsv', vendor='intel'), status='running')
    report['files'].append(entry)
    def guard():
        if (directory/'STOP').exists() or shutil.disk_usage(directory).free < 2*1024**3:
            raise RuntimeError('Stop requested or disk reserve reached; generated files retained')
    def stage(command, label, offset, span):
        jobs.progress(label, offset, 100, directory=directory)
        print(label, flush=True)
        entry.setdefault('commands', []).append([str(x) for x in command])
        native_pipeline.stage([str(x) for x in command], info.duration_seconds, offset, span,
                              timeout=14400, stall=180, guard=guard)
    try:
        if shutil.disk_usage(directory).free < 4*info.size_bytes + 2*1024**3:
            raise ValueError('Insufficient reserve for retained AV1 research intermediates')
        jobs.progress('Checking every source HDR frame', 0, 100, directory=directory)
        frame_file = directory/'source-hdr-frames.json'
        command = [ffprobe, '-v', 'error', '-threads', '0', '-select_streams', 'v:0', '-show_frames',
                   '-show_entries', 'frame=best_effort_timestamp_time,interlaced_frame,repeat_pict:frame_side_data', '-of', 'json', str(source)]
        started = time.monotonic()
        display = TerminalProgress(label='Source HDR frame audit', machine=False)
        with frame_file.open('xb') as out, (directory/'source-hdr-frames.log').open('xb') as err:
            process = subprocess.Popen(command, stdout=out, stderr=err)
            try:
                last = started
                while process.poll() is None:
                    guard()
                    if time.monotonic()-started > 3600:
                        raise RuntimeError('Source frame audit time limit')
                    if time.monotonic()-last > 15:
                        percent = frame_evidence_percent(frame_file, info.duration_seconds)
                        if percent is None:
                            print(f'Source HDR frame audit: {time.monotonic()-started:.0f}s elapsed', flush=True)
                        else:
                            display.update(percent)
                            jobs.stage_progress(percent, display.eta_seconds)
                        last = time.monotonic()
                    time.sleep(.5)
                if process.returncode:
                    raise RuntimeError('Source frame audit failed')
            finally:
                if process.poll() is None:
                    process.kill(); process.wait()
        frames = json.loads(frame_file.read_text(encoding='utf-8'))['frames']
        reference = static_metadata(frames[0]) if frames else {}
        if 'Mastering display metadata' not in reference or not all(metadata_equal(reference, static_metadata(f)) for f in frames):
            raise ValueError('Research requires constant mastering/static HDR metadata on every frame')
        if any(any(x in s.get('side_data_type','').lower() for x in ('dovi','dolby','dynamic','smpte2094')) for f in frames for s in f.get('side_data_list', [])):
            raise ValueError('Dynamic HDR is outside this HDR10 route')
        entry['source_frame_count'] = len(frames)
        first_pts = float(frames[0]['best_effort_timestamp_time'])
        del frames
        options = mm.encoder_options('av1', quality, info, 'av1_qsv', experimental_av1_hdr=True)
        raw, fixed = directory/'encoded.ivf', directory/'repaired.ivf'
        output = directory/source.with_suffix('.mkv').name
        common = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n']
        progress = ['-progress','pipe:1','-nostats']
        gop = max(1, round(float(Fraction(video['r_frame_rate']))*2))
        stage(common+['-copyts','-i',source,'-map','0:v:0',*options,'-g',str(gop),'-fps_mode','passthrough','-avoid_negative_ts','disabled',*progress,'-f','ivf',raw], 'Encoding Intel AV1 HDR10', 10, 55)
        jobs.progress('Validating and repairing AV1 HDR metadata', 65, 100, directory=directory)
        def repair_progress(percent):
            guard()
            jobs.stage_progress(percent, None)
        entry['av1_hdr_repair'] = nvidia_mux.repair_av1_hdr_stream(raw, fixed, reference['Mastering display metadata'], repair_progress)
        packet = mm.run_json([ffprobe,'-v','error','-read_intervals','%+#1','-show_packets','-of','json',str(fixed)])['packets'][0]
        offset = first_pts-float(packet['pts_time'])
        entry['ivf_timestamp_offset_seconds'] = offset
        mux = nvidia_mux.finalize_command(fixed, source, output, probe, ffmpeg)
        mux[mux.index('-i'):mux.index('-i')] = ['-itsoffset',format(offset,'.9f')]
        mux[-1:-1] = progress
        stage(mux, 'Ordered mux with all original tracks', 70, 25)
        accepted, reason = mm.verify_output(info, output, ffprobe, minimum, 'av1')
        if not accepted:
            raise RuntimeError(reason)
        if output.stat().st_size >= info.size_bytes or 100*(1-output.stat().st_size/info.size_bytes) < minimum:
            raise RuntimeError('Output fails requested savings threshold; keep original')
        if (source.stat().st_size,source.stat().st_mtime_ns) != (baseline.st_size,baseline.st_mtime_ns):
            raise RuntimeError('Source changed during research')
        entry.update(output=str(output), status='complete', saved_percent=100*(1-output.stat().st_size/info.size_bytes))
        jobs.progress('AV1 research encoded; full verification required before Plex', 100, 100, directory=directory)
        return 0
    except Exception as exc:
        entry.update(status='failed', error=str(exc)); report['errors'].append(str(exc))
        print('FAILED: '+str(exc), flush=True)
        return 1
    finally:
        (directory/'cli-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path, help='optional SDR file for a separately saved sample')
    parser.add_argument('--hdr-source', type=Path, help='optional non-Dolby-Vision PQ file')
    parser.add_argument('--start', type=float, default=300, help='seek near this second (default 300)')
    parser.add_argument('--seconds', type=float, default=30, help='requested sample length, 1–60 seconds (default 30)')
    parser.add_argument('--hardware', choices=('nvidia', 'intel'), default='nvidia', help='hardware vendor for generated fixtures and separately saved samples')
    parser.add_argument('--gpu', type=int, default=0, help='NVIDIA device index (default 0); actual encodes validate it')
    parser.add_argument('--ffmpeg')
    parser.add_argument('--ffprobe')
    args = parser.parse_args(argv)
    if args.hardware == 'intel' and args.gpu != 0:
        parser.error('Intel currently uses the default QSV device; explicit device selection needs separate validation.')
    if not math.isfinite(args.start) or args.start < 0 or not math.isfinite(args.seconds) or not 1 <= args.seconds <= 60 or args.gpu < 0:
        parser.error('start must be nonnegative, seconds must be 1–60, and GPU index nonnegative')
    return args


def cli():
    if len(sys.argv) > 1 and sys.argv[1] == 'av1-hdr-research':
        parser = argparse.ArgumentParser(description='Explicit Intel AV1 HDR10 research; general preservation gate remains closed')
        parser.add_argument('source', type=Path)
        parser.add_argument('--run', required=True, type=Path)
        parser.add_argument('--execute', action='store_true')
        args = parser.parse_args(sys.argv[2:])
        return jobs.tracked_call(lambda: av1_hdr_research(args), 'Intel AV1 HDR research')
    if len(sys.argv) > 1 and sys.argv[1] == 'verify-full':
        parser = argparse.ArgumentParser(description='Verify an existing full hardware output without encoding')
        parser.add_argument('source', type=Path)
        parser.add_argument('run', type=Path)
        parser.add_argument('--job', required=True, type=Path)
        parser.add_argument('--hdr', action='store_true', help='Explicit HEVC HDR10 full-file validation; excludes AV1 HDR and Dolby Vision')
        parser.add_argument('--experimental-av1-hdr', action='store_true', help='Explicit repaired Intel AV1 HDR10 evidence; requires --hdr')
        args = parser.parse_args(sys.argv[2:])
        return jobs.tracked_call(lambda: verify_full_file(args), 'Hardware full-file verification')
    args = parse_args()
    return jobs.tracked_call(lambda: Validation(args).run(), 'Validate ' + mm.VENDOR_LABELS[args.hardware])


if __name__ == '__main__':
    raise SystemExit(cli())
