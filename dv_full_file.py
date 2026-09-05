"""Explicit experimental Profile 8.1 full-file safe-copy test; dry run by default."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

import muxmender as mm
import native_pipeline as np
import dv_preservation_test as dv
from streaming_pipeline import RunGuard, chapter_summary
from run_logged import Tee


def rpu_digest(path, guard=lambda: None):
    """Read a top-level JSON array incrementally; memory bounded per RPU."""
    decoder = json.JSONDecoder()
    digest, count, buffer, eof = hashlib.sha256(), 0, '', False
    with path.open(encoding='utf-8') as stream:
        def fill():
            nonlocal buffer, eof
            chunk = stream.read(65536)
            buffer += chunk
            eof = not chunk
        fill()
        buffer = buffer.lstrip()
        if not buffer.startswith('['):
            raise ValueError('RPU export is not an array')
        buffer = buffer[1:]
        expect_value = True
        while True:
            guard()
            buffer = buffer.lstrip()
            if not buffer and not eof:
                fill()
                continue
            if buffer.startswith(']'):
                if expect_value and count:
                    raise ValueError('Trailing comma in RPU export')
                buffer = buffer[1:]
                if buffer.strip() or stream.read().strip():
                    raise ValueError('Trailing data in RPU export')
                return count, digest.hexdigest()
            if not expect_value:
                if not buffer.startswith(','):
                    raise ValueError('Missing RPU separator')
                buffer = buffer[1:]
                expect_value = True
                continue
            try:
                value, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                if eof or len(buffer) > 8 * 1024**2:
                    raise ValueError('Malformed or oversized RPU entry')
                fill()
                continue
            if not isinstance(value, dict):
                raise ValueError('RPU entry must be an object')
            digest.update(json.dumps(dv.canonical_rpu(value), sort_keys=True, separators=(',', ':')).encode())
            digest.update(b'\n')
            count += 1
            buffer = buffer[end:]
            expect_value = False


def video_packets(ffprobe, path):
    data = np.checked_json([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_packets',
        '-show_entries', 'packet=pts_time,size', '-of', 'json', str(path)], timeout=600)
    packets = data['packets']
    return sorted(float(p['pts_time']) for p in packets), sum(int(p['size']) for p in packets)


def mux_command(ffmpeg, source, injected, output, rate):
    return [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n', '-r', rate,
        '-i', str(injected), '-i', str(source), '-map', '0:v:0', '-map', '1:a?', '-map', '1:s?',
        '-map', '1:t?', '-map_metadata', '1', '-map_chapters', '1', '-c', 'copy',
        '-bsf:v', 'dovi_rpu=compression=none', '-avoid_negative_ts', 'disabled',
        '-progress', 'pipe:1', '-nostats', str(output)]


def run(args):
    info = mm.probe(args.source, args.ffprobe)
    dv.require_candidate(info)
    if not math.isfinite(info.duration_seconds) or not 0 < info.duration_seconds <= 86400:
        raise ValueError('Requires a known duration of at most 24 hours')
    options = dv.experimental_encoder_options(info, args.qp_i, args.qp_p)
    for tool in (args.ffmpeg, args.ffprobe, args.dovi_tool):
        if not shutil.which(tool):
            raise ValueError(f'Missing tool: {tool}; no automatic installation')
    print(f'FULL-FILE PLAN: {info.duration_seconds:.3f}s; {info.width}x{info.height}; AMD QP{args.qp_i}/{args.qp_p}; Profile 8.1', flush=True)
    if not args.execute:
        print('DRY RUN: no encoding or output files created')
        return 0
    if 'hevc_amf' not in mm.ffmpeg_encoder_names(args.ffmpeg):
        raise ValueError('AMF missing; no CPU fallback')
    args.work_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.work_dir).free < 4 * info.size_bytes + 2 * 1024**3:
        raise ValueError('Insufficient reserve for retained compressed intermediates')
    directory = args.work_dir / ('dv-full-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(exist_ok=False)
    guard = RunGuard(directory, reserve=2 * 1024**3)
    before = args.source.stat()
    report = {'status': 'running', 'source': str(args.source), 'commands': [],
              'qp_i': args.qp_i, 'qp_p': args.qp_p, 'scope': 'full-file Profile 8.1 experimental',
              'quality_note': 'Metadata validation does not prove identical visual quality.'}
    terminal = sys.stdout
    with (directory / 'terminal.log').open('x', encoding='utf-8') as log:
        sys.stdout = Tee(terminal, log)
        try:
            print(f'RUN DIRECTORY: {directory.resolve()}', flush=True)
            def stage(command, phase, offset, span, timeout=14400):
                guard.phase = phase
                guard.status(offset)
                guard()
                report['commands'].append([str(c) for c in command])
                print(f'PHASE: {phase}', flush=True)
                return np.stage([str(c) for c in command], info.duration_seconds, offset, span,
                                timeout=timeout, stall=0, guard=guard)
            ff = [args.ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n']
            progress = ['-progress', 'pipe:1', '-nostats']
            guard.phase = 'source inspection'
            guard.status(0)
            source_pts, source_bytes = video_packets(args.ffprobe, args.source)
            stream = next(s for s in dv.stream_info(args.ffprobe, args.source) if s['codec_type'] == 'video')
            rate = stream['r_frame_rate']
            step = 1 / float(dv.Fraction(rate))
            if not source_pts or abs(source_pts[0]) > .002 or any(abs(b-a-step) > .002 for a,b in zip(source_pts, source_pts[1:])):
                raise ValueError('Only continuous constant-rate video starting at zero is supported')
            raw, rpu, encoded, injected, final = [directory / n for n in
                ('original.hevc', 'original-rpu.bin', 'encoded.hevc', 'injected.hevc', 'episode-dolby-vision.mkv')]
            stage(ff + ['-i', args.source, '-map', '0:v:0', '-c', 'copy', '-bsf:v', 'hevc_mp4toannexb', '-f', 'hevc', *progress, raw], 'extract source bitstream', 0, 8)
            stage([args.dovi_tool, 'extract-rpu', '-i', raw, '-o', rpu], 'extract full RPU', 8, 2)
            stage(ff + ['-threads', '2', '-i', args.source, '-map', '0:v:0', *options,
                  '-profile:v', 'main10', '-fps_mode', 'passthrough', '-f', 'hevc', *progress, encoded], 'AMD full encode', 10, 55)
            stage([args.dovi_tool, 'inject-rpu', '-i', encoded, '--rpu-in', rpu, '-o', injected], 'inject full RPU', 65, 5)
            stage(mux_command(args.ffmpeg, args.source, injected, final, rate), 'copy all audio subtitles chapters', 70, 5)
            guard.phase = 'validate streams and timestamps'
            guard.status(75)
            output_info = mm.probe(final, args.ffprobe)
            dv.require_candidate(output_info)
            for field in ('width', 'height', 'bit_depth', 'color_primaries', 'color_transfer', 'color_space', 'color_range', 'audio_codecs', 'subtitle_codecs'):
                if getattr(info, field) != getattr(output_info, field):
                    raise ValueError(f'Changed {field}')
            output_pts, output_bytes = video_packets(args.ffprobe, final)
            if len(source_pts) != len(output_pts) or any(abs(a-b) > .002 for a,b in zip(source_pts,output_pts)):
                raise ValueError('Full frame-packet timeline mismatch')
            for selector in ('a', 's', 't'):
                guard()
                if np.packet_signatures(args.ffprobe, args.source, selector, timeout=600) != np.packet_signatures(args.ffprobe, final, selector, timeout=600):
                    raise ValueError(f'Original {selector} packets changed')
            if chapter_summary(args.ffprobe, args.source, 60) != chapter_summary(args.ffprobe, final, 60):
                raise ValueError('Chapters changed')
            def first_frame(path):
                return np.checked_json([args.ffprobe, '-v', 'error', '-select_streams', 'v:0',
                    '-read_intervals', '%+#1', '-show_frames', '-of', 'json', str(path)])['frames']
            report['static_hdr_rounding_first_frame'] = dv.compare_static_hdr(first_frame(args.source), first_frame(final))
            check_raw, check_rpu = directory / 'final-check.hevc', directory / 'final-rpu.bin'
            stage(ff + ['-i', final, '-map', '0:v:0', '-c', 'copy', '-bsf:v', 'hevc_mp4toannexb', '-f', 'hevc', *progress, check_raw], 'extract final verification video', 75, 3)
            stage([args.dovi_tool, 'extract-rpu', '-i', check_raw, '-o', check_rpu], 'extract final verification RPU', 78, 2)
            digests = []
            for binary, name in ((rpu, 'original-rpu.json'), (check_rpu, 'final-rpu.json')):
                exported = directory / name
                stage([args.dovi_tool, 'export', '-i', binary, '-d', f'all={exported.resolve()}'], 'export metadata for bounded-memory comparison', 80, 0)
                digests.append(rpu_digest(exported, guard))
            if digests[0] != digests[1] or digests[0][0] != len(source_pts):
                raise ValueError('Full RPU content/count/frame order mismatch')
            stage(ff + ['-v', 'error', '-xerror', '-threads', '2', '-i', final, '-map', '0:v:0', '-f', 'null', '-', *progress], 'complete output decode', 80, 20)
            report.update(status='verified-full-file-awaiting-playback', output=str(final.resolve()), frames=len(source_pts),
                rpu_content_digest=digests[0][1], rpu_byte_identical=dv.sha256(rpu)==dv.sha256(check_rpu),
                audio_subtitle_packets_unchanged=True, chapters_unchanged=True,
                source_bytes=info.size_bytes, output_bytes=final.stat().st_size,
                video_savings_percent=100*(1-output_bytes/source_bytes), total_savings_percent=100*(1-final.stat().st_size/info.size_bytes))
            minimum = getattr(args, 'min_savings', None)
            if minimum is not None and report['total_savings_percent'] < minimum:
                raise ValueError(f"Output passed structural checks but saved only {report['total_savings_percent']:.2f}%; requires {minimum}%. Output retained, not accepted.")
        except (Exception, KeyboardInterrupt) as exc:
            report.update(status='failed', error=str(exc) or 'Interrupted')
            print(f'STOPPED: {report["error"]}; all files retained', flush=True)
        finally:
            after = args.source.stat()
            report['original_stat_unchanged'] = (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
            if not report['original_stat_unchanged']:
                report.update(status='failed', error='Source stat changed during execution')
            with (directory/'validation.json').open('x',encoding='utf-8') as out:
                json.dump(report,out,indent=2)
            guard.phase = report['status']
            guard.status(100 if report['status'].startswith('verified') else 0)
            print(f'RESULT: {report["status"]}\nREPORT: {directory / "validation.json"}',flush=True)
            sys.stdout = terminal
    return 0 if report['status'].startswith('verified') else 1


def run_integrated(args, source):
    """Narrow opt-in CLI route; never silently substitute codecs or DV profiles."""
    conflicts = (
        not source.is_file() or args.resolution != 'keep' or args.codec not in ('auto', 'hevc')
        or args.hardware not in ('auto', 'amd') or args.hardware_fallback == 'cpu'
        or args.dolby_vision_policy != 'skip' or args.dolby_preview_backend != 'vulkan'
        or args.native_delivery_test or args.streaming_delivery_test or args.full_file_streaming
        or args.preview_range_explicit or args.report is not None or args.quality != 'balanced'
    )
    if conflicts:
        print('BLOCKED: preservation requires one file, original resolution, AMD/auto HEVC, '
              'balanced quality with --dv-qp-i/--dv-qp-p, and no preview, other DV policy, '
              'CPU fallback, or --report. A validation report is created in the unique output run.')
        return 2
    if not all(0 <= q <= 51 for q in (args.dv_qp_i, args.dv_qp_p)):
        print('BLOCKED: Dolby Vision QPs must be 0..51')
        return 2
    try:
        for label, tool in (('FFmpeg', args.ffmpeg), ('FFprobe', args.ffprobe), ('dovi_tool', args.dovi_tool)):
            if not shutil.which(tool):
                url = 'https://github.com/quietvoid/dovi_tool/releases' if label == 'dovi_tool' else mm.DOWNLOAD_URLS['ffmpeg']
                mm.offer_requirement(mm.HardwareRequirementError(label, f'Missing {label}: {tool}. Install it, then retry.', url), allow_cpu=False)
                return 3
        if args.execute and 'amd' not in mm.gpu_vendors():
            print('BLOCKED: AMD GPU not detected. NVIDIA/Intel preservation is not validated; no CPU fallback.')
            return 3
        print('Experimental preservation: Profile 8.1 only; no scaling or tone mapping. '
              'All originals and intermediate files retained. Playback review remains required.')
        return run(argparse.Namespace(source=source, execute=args.execute, qp_i=args.dv_qp_i,
            qp_p=args.dv_qp_p, work_dir=args.output_dir or Path(__file__).resolve().parent/'reports',
            ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, dovi_tool=args.dovi_tool,
            min_savings=args.min_savings))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'BLOCKED: {exc}; original and any partial output retained')
        return 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--qp-i',type=int,default=21)
    parser.add_argument('--qp-p',type=int,default=23)
    parser.add_argument('--work-dir',type=Path,default=Path('reports'))
    parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--dovi-tool',default=str(Path(__file__).parent/'tools/dovi_tool-2.3.3/dovi_tool.exe'))
    return run(parser.parse_args())


if __name__ == '__main__':
    from job_tracking import tracked_call
    raise SystemExit(tracked_call(main, 'Full Dolby Vision preservation'))
