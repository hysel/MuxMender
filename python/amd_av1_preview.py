"""Opt-in AMD AV1 QP80 preview/full-file copy. Never deletes or replaces source media."""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import muxmender as mm
import native_pipeline as np
import workflow_worker as worker
from library_planner import probe_with_frame_color, classify
from mux_integrity import conversion_preflight, verify_av1_display_geometry
from job_tracking import tracked_call, phase
from streaming_pipeline import chapter_summary


def reject_integrity_warning(line):
    lowered = line.casefold()
    markers = ('invalid as first byte of an ebml number', 'exceeds containing master element',
               'exceeds max length', 'truncating packet', 'packet corrupt',
               'corrupt decoded frame', 'error while decoding', 'invalid nal unit')
    if any(marker in lowered for marker in markers):
        raise ValueError('Source/container integrity warning; review required: '+line.strip())
    return False


def checksum(path, ctx, offset=0, span=10):
    digest = hashlib.sha256()
    size = path.stat().st_size
    done, last = 0, 0
    with path.open('rb') as stream:
        while block := stream.read(8*1024**2):
            digest.update(block)
            done += len(block)
            if time.monotonic()-last >= 3:
                ctx.guard()
                last = time.monotonic()
                ctx.update('Verify original checksum', offset+span*done/max(1,size))
    ctx.update('Verify original checksum', offset+span)
    return digest.hexdigest()


def disposition_options(streams):
    """Explicit flags prevent FFmpeg from automatically selecting a default track."""
    options = []
    for index, stream in enumerate(streams):
        flags = stream.get('disposition')
        if not isinstance(flags, dict):
            raise ValueError('Missing stream disposition metadata')
        enabled = [key for key, value in flags.items() if value == 1]
        options.extend([f'-disposition:{index}', '+'.join(enabled) or '0'])
    return options


def verify_tracks(original, encoded):
    if len(original) != len(encoded):
        raise ValueError('Track count changed')
    for a, b in zip(original, encoded):
        for key in ('index', 'codec_type', 'disposition'):
            if a.get(key) != b.get(key):
                raise ValueError('Track '+key+' changed')
        for tag in ('language', 'title', 'filename', 'mimetype'):
            if a.get('tags', {}).get(tag) != b.get('tags', {}).get(tag):
                raise ValueError('Track '+tag+' changed')
        if a.get('codec_type') != 'video':
            for key in ('codec_name', 'extradata_hash'):
                if a.get(key) != b.get(key):
                    raise ValueError('Copied track '+key+' changed')


def verify_geometry(original, encoded, decoded_sizes):
    """Explicit narrow exception, not a generic crop-metadata bypass."""
    if (original.get('width'), original.get('height')) != (1920, 1080):
        raise ValueError('Experimental crop-aware route is limited to 1920x1080')
    if original.get('side_data_list'):
        raise ValueError('Source geometry side data requires separate review')
    if original.get('field_order') != 'progressive':
        raise ValueError('Only progressive source video is supported')
    if any(s.get('side_data_type') == 'Display Matrix' for s in encoded.get('side_data_list', [])):
        raise ValueError('Output rotation requires separate review')
    if encoded.get('codec_name') != 'av1':
        raise ValueError('Expected AV1 output')
    if original.get('sample_aspect_ratio') != '1:1' or encoded.get('sample_aspect_ratio') != '1:1':
        raise ValueError('Non-square pixels require separate review')
    coded = (encoded.get('width'), encoded.get('height'))
    crops = [x for x in encoded.get('side_data_list', []) if x.get('side_data_type') == 'Frame Cropping']
    if coded == (1920, 1080):
        if crops:
            raise ValueError('Unexpected crop on exact-size output')
    elif coded == (1920, 1082):
        if len(crops) != 1 or any(type(crops[0].get('crop_'+k)) is not int or crops[0]['crop_'+k] != v
                                  for k, v in dict(top=0, bottom=2, left=0, right=0).items()):
            raise ValueError('Only two bottom padding rows are permitted')
    else:
        raise ValueError('Unexpected coded dimensions; no resize is allowed')
    if not decoded_sizes or any(size != (1920, 1080) for size in decoded_sizes):
        raise ValueError('Every decoded displayed frame must remain 1920x1080')
    return verify_av1_display_geometry(original, encoded, decoded_sizes)


def validate_args(args):
    if not math.isfinite(args.start) or args.start < 0 or not 1 <= args.seconds <= 30:
        raise ValueError('Start must be finite and nonnegative; duration must be 1..30 seconds')
    if args.execute and args.dry_run:
        raise ValueError('--execute and --dry-run cannot be combined')


def decoded_timestamps(path, ffprobe, diagnostics, timeout):
    command = [ffprobe, '-v', 'error', '-threads', '2', '-select_streams', 'v:0',
               '-show_frames', '-show_entries', 'frame=pts_time', '-of', 'json', str(path)]
    diagnostics.update(path=str(path), command=command)
    completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                               errors='replace', timeout=timeout)
    diagnostics.update(returncode=completed.returncode, stderr=completed.stderr[-16000:])
    if completed.returncode or completed.stderr.strip():
        raise ValueError('Frame decoder reported errors; see timeline diagnostics')
    frames = json.loads(completed.stdout)['frames']
    diagnostics['frame_count'] = len(frames)
    values = sorted(float(frame['pts_time']) for frame in frames)
    if any(not math.isfinite(value) for value in values):
        raise ValueError('Non-finite frame timestamp')
    return values


def compare_timestamps(a, b, diagnostics):
    differences = [(i, x, y, y-x) for i, (x, y) in enumerate(zip(a, b)) if abs(x-y) > .002]
    diagnostics.update(source_count=len(a), output_count=len(b), tolerance_seconds=.002,
                       mismatch_count=len(differences), first_mismatches=differences[:20])
    if not a or len(a) != len(b) or differences:
        raise ValueError('Decoded frame timeline changed; see timeline diagnostics')
    diagnostics['passed'] = True


def validate_output(args, source, reference, output, directory, ctx, result, full):
    """Shared checks for new encodes and read-only revalidation."""
    ref_info = probe_with_frame_color(reference, args.ffprobe)
    telemetry = ['-progress', 'pipe:1', '-nostats']
    phase(directory, 'Validate streams and timeline', 60)
    actual = probe_with_frame_color(output, args.ffprobe)
    if actual.hdr or actual.dolby_vision:
        raise ValueError('Unexpected HDR or Dolby Vision signaling')
    for field in ('bit_depth', 'color_range', 'color_space', 'color_transfer', 'color_primaries', 'audio_codecs', 'subtitle_codecs'):
        if getattr(ref_info, field) != getattr(actual, field):
            raise ValueError('Changed '+field)
    for selector in ('a', 's'):
        result['packets_'+selector] = worker.compare_media_packets(args.ffprobe, reference, output, selector, ctx.guard)
    def probe(path, frames=False):
        command = [args.ffprobe, '-v', 'error', '-threads', '2', '-select_streams', 'v:0']
        command += ['-show_frames', '-show_entries', 'frame=pts_time'] if frames else ['-show_streams']
        return np.checked_json(command+['-of', 'json', str(path)], timeout=14400 if full else 180)
    result['timeline'] = timeline = dict(source={}, output={})
    try:
        phase(directory, 'Decode source frame timeline', 65)
        a = decoded_timestamps(reference, args.ffprobe, timeline['source'], 14400 if full else 180)
        phase(directory, 'Decode output frame timeline', 70)
        b = decoded_timestamps(output, args.ffprobe, timeline['output'], 14400 if full else 180)
        compare_timestamps(a, b, timeline)
    finally:
        worker.save(directory/'timeline-diagnostics.json', timeline)
    phase(directory, 'Decode every displayed frame and audio track', 80)
    command = [args.ffmpeg, '-hide_banner', '-v', 'info', '-xerror', '-nostdin', '-threads', '2',
               '-noautorotate', '-apply_cropping', 'all', '-i', str(output), '-map', '0:v:0', '-map', '0:a?',
               '-vf', 'showinfo', '-threads', '2', '-f', 'null', '-']
    sizes = []
    def observe(line):
        match = re.search(r'\bs:(\d+)x(\d+)\b', line)
        if match:
            size = tuple(map(int, match.groups()))
            if size != (1920, 1080):
                raise ValueError('Decoded displayed dimensions changed')
            sizes.append(size)
        return 'showinfo' in line
    np.stage(command+telemetry, ref_info.duration_seconds, 80, 15,
             timeout=14400 if full else 180, stall=120, guard=ctx.guard, observe=observe)
    if len(sizes) != len(a):
        raise ValueError('Full decode frame count differs')
    original_stream, encoded_stream = probe(reference)['streams'][0], probe(output)['streams'][0]
    # Non-geometry codec side data is not relevant to geometry verification.
    original_stream['side_data_list'] = [x for x in original_stream.get('side_data_list', [])
                                        if x.get('side_data_type') in ('Frame Cropping', 'Display Matrix')]
    result['geometry'] = verify_geometry(original_stream, encoded_stream, sizes)
    savings = 100*(1-output.stat().st_size/reference.stat().st_size)
    if full:
        def tracks(path):
            return np.checked_json([args.ffprobe, '-v', 'error', '-show_streams', '-show_data_hash',
                                    'sha256', '-of', 'json', str(path)], timeout=120)['streams']
        verify_tracks(tracks(source), tracks(output))
        if chapter_summary(args.ffprobe, source, 600) != chapter_summary(args.ffprobe, output, 600):
            raise ValueError('Chapters changed')
        phase(directory, 'Checksum original after validation', 95)
        result['source_sha256_after'] = checksum(source, ctx, 95, 5)
        if result['source_sha256_before'] != result['source_sha256_after']:
            raise ValueError('Original checksum changed')
        if savings < 5:
            raise ValueError('Less than 5% savings; output retained but not approved')
    result.update(status='experimental-preview-awaiting-playback', frames=len(a), full_decode='passed',
                  total_savings_percent=savings, savings_acceptable=savings >= 5,
                  note='Preview only; no automatic promotion, replacement, deletion or universal compatibility claim.')
    if full:
        result.update(status='validated-experimental-full-file-awaiting-playback',
                      note='Full-file copy; originals retained. Visual playback review still required.')


def run(args, on_result=None, guard=None):
    validate_args(args)
    full = getattr(args, 'full', False)
    source = args.source.resolve(strict=True)
    info = probe_with_frame_color(source, args.ffprobe)
    if (info.width, info.height) != (1920, 1080) or info.bit_depth != 8 or info.hdr or info.dolby_vision:
        raise ValueError('Research preview requires 1080p 8-bit SDR, not HDR/Dolby Vision')
    if classify(info)[0] != 'preview-candidate' or (not full and args.start >= info.duration_seconds):
        raise ValueError('Source is not an eligible preview candidate or start exceeds duration')
    options = mm.encoder_options('av1', 'balanced', info, 'av1_amf', experimental_amd_av1_qp80=True)
    source_shape = worker.shape(source, args.ffprobe)
    if source_shape.get('field_order') != 'progressive' or source_shape.get('sample_aspect_ratio') != '1:1' or source_shape.get('side_data_list'):
        raise ValueError('Source must be progressive, square-pixel and unrotated')
    if not args.execute:
        print(json.dumps(dict(mode='dry-run', source=str(source), output_root=str(args.output_dir),
                              encoder_options=options, start=args.start, seconds=args.seconds,
                              scope='full-file' if full else 'preview',
                              warning='Experimental crop-aware output; original always retained'), indent=2))
        return 0
    if 'amd' not in mm.gpu_vendors() or 'av1_amf' not in mm.ffmpeg_encoder_names(args.ffmpeg):
        raise ValueError('AMD AV1 encoder unavailable; no CPU fallback or installation')
    preflight = conversion_preflight(info, args.ffprobe, mm.run_json)
    if preflight['status'] != 'passed-sampled-checks':
        raise ValueError(str(preflight['reasons']))
    before = source.stat()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    required = before.st_size*2+5*1024**3 if full else 4*1024**3
    if shutil.disk_usage(args.output_dir).free < required:
        raise ValueError('Insufficient space for output and safety reserve')
    directory = args.output_dir / ('AMD-AV1-QP80-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(exist_ok=False)
    title = 'Experimental AMD AV1 QP80 '+('full-file copy' if full else 'preview')
    worker.save(directory/'job.json', dict(title=title, state='running', updated=time.time()))
    ctx = worker.Context(directory)
    if guard is not None:
        original_guard = ctx.guard
        def combined_guard():
            original_guard()
            guard()
        ctx.guard = combined_guard
    if full:
        ctx.minimum = 5*1024**3
    output = directory / (source.stem + '.AV1-QP80.mkv')
    reference = directory / 'Reference.mkv'
    result = dict(status='running', source=str(source), output=str(output), preflight=preflight)
    prefix = [args.ffmpeg, '-hide_banner', '-v', 'warning', '-xerror', '-nostdin', '-n']
    telemetry = ['-progress', 'pipe:1', '-nostats']
    try:
        if full:
            phase(directory, 'Checksum original before encoding', 0)
            result['source_sha256_before'] = checksum(source, ctx)
            reference = source
        else:
            phase(directory, 'Extract reference', 0)
            ctx.update('Extract reference', 0)
            np.stage(prefix+['-ss', str(args.start), '-i', str(source), '-t', str(args.seconds), '-map', '0',
                          '-map_chapters', '-1', '-c', 'copy', '-avoid_negative_ts', 'make_zero', *telemetry, str(reference)],
                  args.seconds, 0, 10, timeout=14400, stall=120, guard=ctx.guard, observe=reject_integrity_warning)
        ref_info = probe_with_frame_color(reference, args.ffprobe)
        if not full and ref_info.duration_seconds > args.seconds+15:
            raise ValueError('Reference exceeds bounded preview duration')
        expected_frames = None
        if full:
            phase(directory, 'Count source video packets for encode progress', 10)
            source_pts, _ = worker.video_summary(source, args.ffprobe)
            expected_frames = len(source_pts)
            result['progress_basis'] = 'Encoded frames / source video packet count; decoded-frame validation remains separate'
            result['progress_expected_frames'] = expected_frames
        phase(directory, 'Encode AMD AV1 QP80', 10)
        ctx.update('Encode AMD AV1 QP80', 10)
        streams = np.checked_json([args.ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(reference)], timeout=120)['streams']
        np.stage(prefix+['-threads', '2', '-noautorotate', '-copyts', '-i', str(reference), '-map', '0',
                          '-map_metadata', '0', '-map_chapters', '0', '-c', 'copy', *options, *disposition_options(streams),
                          '-fps_mode', 'passthrough', '-avoid_negative_ts', 'disabled', *telemetry, str(output)],
                  ref_info.duration_seconds, 10, 50, timeout=14400, stall=120, guard=ctx.guard,
                  observe=reject_integrity_warning, expected_frames=expected_frames)
        validate_output(args, source, reference, output, directory, ctx, result, full)
        phase(directory, 'Ready for playback review', 100)
        ctx.update('Preview ready for review', 100, state='completed')
        return 0
    except BaseException as exc:
        result.update(status='failed-all-files-retained', error=str(exc))
        ctx.update('Failed; files retained', state='failed', error=str(exc))
        raise
    finally:
        after = source.stat()
        result['original_size_mtime_unchanged'] = (before.st_size,before.st_mtime_ns) == (after.st_size,after.st_mtime_ns)
        if not result['original_size_mtime_unchanged']:
            result.update(status='failed', error='Source changed during preview')
            ctx.update('Source changed; all files retained', state='failed', error=result['error'])
        worker.save(directory/'validation.json', result)
        if on_result is not None:
            on_result(dict(result))
        print(json.dumps(result, indent=2), flush=True)
        if not result['original_size_mtime_unchanged']:
            raise ValueError('Source changed during preview')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--start', type=float, default=300)
    parser.add_argument('--seconds', type=int, default=30)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--full', action='store_true', help='Opt-in full-file validation; ignores preview start/duration')
    args = parser.parse_args(argv)
    validate_args(args)
    if not args.execute:
        return run(args)
    return tracked_call(lambda: run(args), 'Experimental AMD AV1 QP80 '+('full-file copy' if args.full else 'preview'))


if __name__ == '__main__':
    raise SystemExit(main())
