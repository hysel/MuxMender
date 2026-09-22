"""Experimental, bounded Profile 8.1 test. No original writes or file deletion.

Run with --help. Dry run by default; only --execute creates new outputs.
This is not the general optimizer and never claims lossless visual quality.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
import uuid
from fractions import Fraction

import muxmender as mm
import native_pipeline as np
from streaming_pipeline import RunGuard
from mux_integrity import verify_startup_interleaving
import validate_nvidia as nv
import job_tracking as jobs


def require_candidate(info):
    plan = mm.assess_dolby_preservation(info)
    if not plan or plan['route'] != 'profile8.1-research-candidate':
        raise ValueError('This experiment requires single-layer HEVC Dolby Vision Profile 8.1 with confirmed RPU')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def stream_info(ffprobe, path):
    return np.checked_json([ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(path)])['streams']


def frame_info(ffprobe, path):
    from hdr10plus_validation import preserve_json_pairs
    result=subprocess.run([ffprobe, '-v', 'error', '-threads','2','-select_streams', 'v:0',
                           '-show_frames', '-of', 'json', str(path)],timeout=120,
                          capture_output=True,text=True,check=True)
    if result.stderr.strip():raise ValueError('Decoder errors in DV frame evidence: '+result.stderr[-1000:])
    return json.loads(result.stdout,object_pairs_hook=preserve_json_pairs)['frames']


def static_hdr(frames):
    return [s for s in frames[0].get('side_data_list', [])
            if s.get('side_data_type') in ('Mastering display metadata', 'Content light level metadata')]


def compare_static_hdr(source, output):
    """Allow at most one ST2086 chromaticity quantization unit; report it."""
    a, b = static_hdr(source), static_hdr(output)
    if len(a) != len(b):
        raise ValueError('Static HDR metadata missing')
    rounding = []
    for left, right in zip(a, b):
        if left.keys() != right.keys():
            raise ValueError('Static HDR metadata fields changed')
        for key in left:
            if left[key] == right[key]:
                continue
            if key in ('red_x', 'red_y', 'green_x', 'green_y', 'blue_x', 'blue_y', 'white_point_x', 'white_point_y') \
                    and abs(Fraction(left[key])-Fraction(right[key])) <= Fraction(1, 50000):
                rounding.append({'field': key, 'source': left[key], 'output': right[key]})
            else:
                raise ValueError(f'Static HDR metadata changed: {key}')
    return rounding


def validate_timeline(source, output):
    src = [Fraction(f['best_effort_timestamp_time']) for f in source]
    dst = [Fraction(f['best_effort_timestamp_time']) for f in output]
    if (not src or len(src) != len(dst) or any(abs(a-b)>Fraction(1,500) for a,b in zip(src,dst))
            or any(b<=a for rows in (src,dst) for a,b in zip(rows,rows[1:]))):
        raise ValueError('Frame count or absolute presentation timestamps changed')


def canonical_rpu(value):
    """Ignore only RPU CRC and extension-block ordering, never frame ordering."""
    if isinstance(value, list):
        return [canonical_rpu(v) for v in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == 'rpu_data_crc32':
                continue
            normalized = canonical_rpu(item)
            if key == 'ext_metadata_blocks':
                normalized = sorted(normalized, key=lambda v: json.dumps(v, sort_keys=True))
            result[key] = normalized
        return result
    return value


def experimental_encoder_options(info, qp_i=18, qp_p=20):
    for value in (qp_i, qp_p):
        if type(value) is not int or not 0 <= value <= 51:
            raise ValueError('QP values must be integers from 0 to 51')
    options = mm.encoder_options('hevc', 'transparent', info, 'hevc_amf')
    options[options.index('-qp_i') + 1] = str(qp_i)
    options[options.index('-qp_p') + 1] = str(qp_p)
    return options


def sample_encoder_options(info, experimental_nvidia=False, experimental_intel=False, nvenc_cq=None):
    """Separate opt-in sample route; the integrated/full-file AMD gate is unchanged."""
    if experimental_nvidia and experimental_intel:
        raise ValueError("Choose only one experimental hardware vendor")
    if nvenc_cq is not None and (not experimental_nvidia or type(nvenc_cq) is not int or nvenc_cq not in range(18,33)):
        raise ValueError('DV NVENC CQ requires NVIDIA and a bounded tested-search value')
    if experimental_intel:
        require_candidate(info)
        return mm.encoder_options("hevc", "transparent", info, "hevc_qsv")
    if not experimental_nvidia:
        return experimental_encoder_options(info)
    require_candidate(info)
    # No B frames in the initial raw-HEVC/RPU experiment: retain a simple
    # presentation/decode order. This is not a new general NVENC preset.
    options=mm.encoder_options('hevc', 'transparent', info, 'hevc_nvenc') + ['-bf', '0']
    if nvenc_cq is not None:options[options.index('-cq')+1]=str(nvenc_cq)
    return options


def hdr10plus_metadata(frame):
    return [s for s in frame.get('side_data_list',[]) if
            '2094-40' in s.get('side_data_type','') or 'HDR10+' in s.get('side_data_type','')]


def require_nvidia_frames(frames,allow_hdr10plus=False):
    for frame in frames:
        if frame.get('interlaced_frame') != 0 or frame.get('repeat_pict', 0) != 0:
            raise ValueError('Hardware research sample requires progressive frames without repeats')
        for side in frame.get('side_data_list', []):
            name = side.get('side_data_type', '').lower()
            if 'hdr10+' in name or 'smpte2094' in name or ('dynamic' in name and 'hdr' in name):
                if allow_hdr10plus and ('2094-40' in name or 'hdr10+' in name):continue
                raise ValueError('Additional dynamic HDR metadata needs a separate preservation test')


class NvidiaSampleGuard(RunGuard):
    def __call__(self):
        getattr(self,'source_guard',lambda:None)()
        return super().__call__()

    def status(self, percent):
        super().status(percent)
        overall = getattr(self, 'overall_offset', 0) + percent*getattr(self, 'overall_span', 100)/100
        jobs.progress(self.phase, overall, 100, directory=self.directory,
                      unit='validation checkpoints', detail=getattr(self, 'detail',
                      'Experimental DV sample; integrated opt-in supports AMD/Intel Profile 8.1.'))


def run(args):
    if not math.isfinite(args.seconds) or not 1 <= args.seconds <= 30:
        raise ValueError('Duration must be 1..30 seconds')
    start = getattr(args, 'start', 0)
    if not math.isfinite(start) or start < 0:
        raise ValueError('Start must be finite and nonnegative')
    minimum_savings=getattr(args,'minimum_savings_percent',10)
    if not math.isfinite(minimum_savings) or not 0<=minimum_savings<100:
        raise ValueError('Minimum savings must be finite and between zero and 100')
    source = args.source.resolve(strict=True)
    for tool in (args.ffmpeg, args.ffprobe, args.dovi_tool):
        if not shutil.which(str(tool)):
            raise ValueError(f'Missing dependency: {tool}; no automatic installation')
    info = mm.probe(source, args.ffprobe)
    require_candidate(info)
    qp_i, qp_p = getattr(args, 'qp_i', 18), getattr(args, 'qp_p', 20)
    nvidia = getattr(args, 'experimental_nvidia', False)
    intel = getattr(args, 'experimental_intel', False)
    experimental = nvidia or intel
    combined=getattr(args,'experimental_hdr10plus',False)
    if combined and not nvidia:raise ValueError('Combined DV/HDR10+ research currently requires explicit NVIDIA mode')
    if combined and not shutil.which('hdr10plus_tool'):raise ValueError('Missing dependency: hdr10plus_tool')
    options = sample_encoder_options(info, nvidia, intel, getattr(args,'nvenc_cq',None)) if experimental else experimental_encoder_options(info, qp_i, qp_p)
    encoder = 'hevc_qsv' if intel else 'hevc_nvenc' if nvidia else 'hevc_amf'
    print(f'PLAN: {args.seconds:g}s near {start:g}s, exact {info.width}x{info.height}, {encoder}, original RPU; no tone mapping', flush=True)
    print(f'ENCODER OPTIONS: {options}; visual review required', flush=True)
    if not args.execute:
        print('DRY RUN: no encoding or output files created', flush=True)
        return 0
    if encoder not in mm.ffmpeg_encoder_names(args.ffmpeg):
        raise ValueError(f'{encoder} unavailable; no automatic CPU fallback')
    if intel and 'intel' not in mm.gpu_vendors():
        raise ValueError('Intel GPU not detected; no automatic CPU fallback')
    if nvidia and 'nvidia' not in mm.gpu_vendors():
        raise ValueError('NVIDIA GPU not detected; no automatic CPU fallback')
    run_id = 'dv81-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    directory = args.work_dir.resolve() / run_id
    directory.mkdir(parents=True, exist_ok=False)
    guard = (NvidiaSampleGuard if experimental else RunGuard)(directory, reserve=1024**3)
    if experimental:guard.source_guard=getattr(args,'source_guard',lambda:None)
    if experimental:
        guard.overall_offset = getattr(args, 'overall_offset', 0)
        guard.overall_span = getattr(args, 'overall_span', 100)
    before = source.stat()
    report = {'status': 'running', 'source': str(source), 'scope': 'experimental keyframe-seek sample, not full episode',
              'requested_start': start, 'requested_seconds': args.seconds,
              'encoder_settings': ({'encoder': encoder, 'options': options} if experimental else
                                   {'encoder': 'hevc_amf', 'preset': 'quality', 'qp_i': qp_i, 'qp_p': qp_p}),
              'commands': [], 'quality_note': 'Metadata and decode checks do not prove identical visual quality.'}
    def stage(command, phase, offset, span):
        guard.phase = phase
        guard.status(offset)
        guard()
        report['commands'].append([str(c) for c in command])
        print(f'PHASE: {phase}', flush=True)
        return np.stage([str(c) for c in command], args.seconds, offset, span,
                        timeout=300, stall=90, guard=guard,
                        strict_decode=phase == 'decode validation')
    ff = [args.ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n']
    progress = ['-progress', 'pipe:1', '-nostats']
    clip = directory / 'reference-clip.mkv'
    raw = directory / 'reference.hevc'
    rpu = directory / 'original-rpu.bin'
    encoded = directory / 'encoded.hevc'
    injected = directory / 'injected.hevc'
    final = directory / 'candidate-dolby-vision.mkv'
    try:
        original_streams = stream_info(args.ffprobe, source) if experimental else []
        if experimental and (sum(s['codec_type'] == 'video' for s in original_streams) != 1
                       or any(s['codec_type'] not in ('video', 'audio', 'subtitle', 'attachment') for s in original_streams)):
            raise ValueError('Hardware research sample requires one video and supported original track types')
        source_dispositions = nv.disposition_options({'streams': original_streams}) if experimental else []
        # Keep all packets in the bounded, keyframe-starting reference; no seek
        # or trim after extraction can silently change RPU/frame correspondence.
        stage(ff + ['-ss', str(start), '-i', source, '-t', str(args.seconds + 8), '-map', '0:v:0', '-map', '0:a?', '-map', '0:s?',
                    '-map', '0:t?', '-map_metadata', '0', '-map_chapters', '-1', '-c', 'copy',
                    '-avoid_negative_ts', 'make_zero', *source_dispositions, *progress, clip], 'copy reference clip', 0, 10)
        frames = frame_info(args.ffprobe, clip)
        if experimental:
            require_nvidia_frames(frames,allow_hdr10plus=combined)
            if combined and not any(hdr10plus_metadata(f) for f in frames):
                raise ValueError('Combined research source has no decoded HDR10+ metadata')
        video = next(s for s in stream_info(args.ffprobe, clip) if s['codec_type'] == 'video')
        pts = sorted(float(f['best_effort_timestamp_time']) for f in frames)
        rate = video['r_frame_rate']
        numerator, denominator = map(int, rate.split('/'))
        if numerator <= 0 or denominator <= 0:
            raise ValueError('Unknown frame rate')
        step = denominator / numerator
        if len(pts) < 2 or any(abs((b-a)-step) > .002 for a,b in zip(pts, pts[1:])):
            # Stream-copy duration cuts can retain reordered frames beyond the
            # boundary. Use a complete prefix ending before a later keyframe,
            # and re-check the decoded timeline rather than dropping arbitrary RPUs.
            packets = np.checked_json([args.ffprobe, '-v', 'error', '-select_streams', 'v:0',
                '-show_packets', '-show_entries', 'packet=pts_time,flags', '-of', 'json', str(clip)])['packets']
            boundaries = [i for i,p in enumerate(packets) if i > 0 and 'K' in p.get('flags', '')]
            if not boundaries:
                raise ValueError('No complete keyframe-bounded sample available within requested duration')
            count = boundaries[-1]
            prefix = sorted(float(p['pts_time']) for p in packets[:count])
            if any(abs((b-a)-step) > .002 for a,b in zip(prefix, prefix[1:])):
                raise ValueError('Keyframe prefix still has unsupported frame timing')
            bounded = directory / 'keyframe-reference.mkv'
            stage(ff + ['-i', clip, '-map', '0', '-c', 'copy', '-frames:v', str(count),
                        '-avoid_negative_ts', 'disabled', *source_dispositions, *progress, bounded], 'align sample boundary', 10, 0)
            clip = bounded
            frames = frame_info(args.ffprobe, clip)
            pts = sorted(float(f['best_effort_timestamp_time']) for f in frames)
            if len(pts) != count or any(abs((b-a)-step) > .002 for a,b in zip(pts, pts[1:])):
                raise ValueError('Decoded keyframe-bounded sample timeline invalid')
            print(f'Prepared complete {len(pts)}-frame reference before sample trimming', flush=True)
        all_frame_count = len(frames)
        count = round(args.seconds / step)
        if len(frames) < count:
            raise ValueError('Not enough complete frames for requested sample')
        frames = frames[:count]
        pts = sorted(float(f['best_effort_timestamp_time']) for f in frames)
        end_time = pts[-1] + step
        if any(abs((b-a)-step) > .002 for a,b in zip(pts, pts[1:])):
            raise ValueError('Selected frame timeline is not continuous')
        report['sample_frames'] = len(frames)
        report['sample_seconds'] = len(frames) * step
        print(f'Selected {len(frames)} presentation frames ({len(frames)*step:.3f}s)', flush=True)
        reference_packets = np.checked_json([args.ffprobe, '-v', 'error', '-select_streams', 'v:0',
            '-show_packets', '-show_entries', 'packet=pts_time,size', '-of', 'json', str(clip)])['packets']
        sample_video_bytes = sum(int(p['size']) for p in reference_packets
                                 if pts[0] <= float(p.get('pts_time', 'inf')) < end_time - .002)
        stage(ff + ['-i', clip, '-map', '0:v:0', '-c', 'copy', '-bsf:v', 'hevc_mp4toannexb',
                    '-f', 'hevc', *progress, raw], 'extract original HEVC', 10, 5)
        stage([args.dovi_tool, 'extract-rpu', '-i', raw, '-o', rpu], 'extract original RPU', 15, 5)
        if count < all_frame_count:
            trim_config = directory / 'rpu-frame-range.json'
            with trim_config.open('x', encoding='utf-8') as out:
                json.dump({'remove': [f'{count}-{all_frame_count-1}']}, out)
            trimmed = directory / 'sample-rpu.bin'
            stage([args.dovi_tool, 'editor', '-i', rpu, '-j', trim_config, '-o', trimmed],
                  'align RPU to selected presentation frames', 20, 0)
            rpu = trimmed
        stage(ff + ['-threads', '2', '-i', clip, '-map', '0:v:0', '-an', '-sn', '-dn',
                    *options,
                    '-profile:v', 'main10', '-frames:v', str(count),
                    '-fps_mode', 'passthrough', '-f', 'hevc', *progress, encoded], f'{encoder} experimental encode', 20, 45)
        if combined:
            metadata=directory/'original-hdr10plus.json'
            stage(['hdr10plus_tool','extract',raw,'-o',metadata],'extract original HDR10+',65,0)
            if count<all_frame_count:
                bounded_metadata=directory/'sample-hdr10plus.json'
                stage(['hdr10plus_tool','editor',metadata,'-j',trim_config,'-o',bounded_metadata],
                      'align HDR10+ to selected presentation frames',65,0)
                metadata=bounded_metadata
            restored=directory/'encoded-hdr10plus.hevc'
            stage(['hdr10plus_tool','inject','-i',encoded,'-j',metadata,'-o',restored],
                  'restore original HDR10+',65,0)
            encoded=restored
        stage([args.dovi_tool, 'inject-rpu', '-i', encoded, '--rpu-in', rpu, '-o', injected],
              'inject unchanged RPU', 65, 5)
        video_input = ['-r', rate, '-i', injected]
        if experimental:
            from dv_full_file import timestamped_video_command
            timestamped = directory / 'timestamped-sample-video.mkv'
            timestamp_command = timestamped_video_command(args.ffmpeg, injected, timestamped, rate, intel=intel)
            stage(timestamp_command,
                  'materialize sample video timestamps', 70, 0)
            video_input = ['-i', timestamped]
        stage(ff + ['-copyts', '-itsoffset', str(pts[0]), *video_input, '-i', clip,
                    '-map', '0:v:0', '-map', '1:a?', '-map', '1:s?', '-map', '1:t?', '-map_metadata', '1',
                    '-map_chapters', '-1', '-t', str(end_time), '-c', 'copy', '-bsf:v', 'dovi_rpu=compression=none',
                    '-avoid_negative_ts', 'disabled', *source_dispositions, *progress, final],
              'mux candidate', 70, 10)
        guard.phase = 'validating'
        guard.status(80)
        result = mm.probe(final, args.ffprobe)
        require_candidate(result)
        for field in ('width', 'height', 'bit_depth', 'color_primaries', 'color_transfer', 'color_space', 'color_range'):
            if getattr(info, field) != getattr(result, field):
                raise ValueError(f'{field} changed')
        final_frames = frame_info(args.ffprobe, final)
        if experimental:
            require_nvidia_frames(final_frames,allow_hdr10plus=combined)
            clip_streams = {'streams': stream_info(args.ffprobe, clip)}
            final_streams = {'streams': stream_info(args.ffprobe, final)}
            if nv.stream_inventory({'streams': original_streams}) != nv.stream_inventory(clip_streams) or nv.stream_inventory(clip_streams) != nv.stream_inventory(final_streams):
                raise ValueError('Non-video stream inventory/dispositions changed')
            if nv.first_video(clip_streams).get('sample_aspect_ratio') != nv.first_video(final_streams).get('sample_aspect_ratio'):
                raise ValueError('Sample aspect ratio changed')
            passed, detail = verify_startup_interleaving(final, args.ffprobe)
            report['startup_interleaving'] = {'passed': passed, 'detail': detail}
            if not passed:
                raise ValueError(detail)
        validate_timeline(frames, final_frames)
        report['static_hdr_rounding'] = compare_static_hdr(frames, final_frames)
        for source_frame, final_frame in zip(frames, final_frames):
            compare_static_hdr([source_frame],[final_frame])
            if combined and hdr10plus_metadata(source_frame)!=hdr10plus_metadata(final_frame):
                raise ValueError('Per-frame HDR10+ metadata changed or missing')
            def dv_metadata(frame):
                return [s for s in frame.get('side_data_list', []) if s.get('side_data_type') == 'Dolby Vision Metadata']
            if not dv_metadata(source_frame) or dv_metadata(source_frame) != dv_metadata(final_frame):
                raise ValueError('Per-frame Dolby Vision metadata changed or missing')
        for selector in ('a', 's', 't'):
            expected = [p for p in np.packet_signatures(args.ffprobe, clip, selector)
                        if selector == 't' or float(p.get('pts_time', 'inf')) < end_time]
            if expected != np.packet_signatures(args.ffprobe, final, selector):
                raise ValueError(f'{selector} stream packets/timestamps changed')
        check_raw = directory / 'final-check.hevc'
        check_rpu = directory / 'final-rpu.bin'
        stage(ff + ['-i', final, '-map', '0:v:0', '-c', 'copy', '-bsf:v', 'hevc_mp4toannexb',
                    '-f', 'hevc', *progress, check_raw], 'extract final verification bitstream', 80, 5)
        stage([args.dovi_tool, 'extract-rpu', '-i', check_raw, '-o', check_rpu], 'verify final RPU', 85, 5)
        if not rpu.stat().st_size:
            raise ValueError('Empty original RPU')
        original_json, final_json = directory / 'original-rpu.json', directory / 'final-rpu.json'
        for binary, output_json in ((rpu, original_json), (check_rpu, final_json)):
            stage([args.dovi_tool, 'export', '-i', binary, '-d', f'all={output_json}'],
                  'compare complete Dolby Vision metadata', 90, 0)
        original_data = json.loads(original_json.read_text(encoding='utf-8'))
        final_data = json.loads(final_json.read_text(encoding='utf-8'))
        if len(original_data) != len(frames) or canonical_rpu(original_data) != canonical_rpu(final_data):
            raise ValueError('RPU count, frame order, or metadata values changed')
        report['rpu_byte_identical'] = sha256(rpu) == sha256(check_rpu)
        report['rpu_content_and_frame_order_unchanged'] = True
        if combined:report['hdr10plus_content_and_frame_order_unchanged']=True
        report['rpu_comparison_note'] = 'Compare every parsed field; only extension-block ordering and recalculated CRC are ignored. Frame order is never ignored.'
        stage(ff + ['-v', 'error', '-xerror', '-threads', '2', '-i', final, '-map', '0:v:0',
                    *(['-map', '0:a?'] if experimental else []), '-f', 'null', '-', *progress], 'decode validation', 90, 10)
        report.update(status='verified-structure-awaiting-visual-review', frames=len(frames),
                      reference_sha256=sha256(raw),
                      original_rpu_sha256=sha256(rpu), final_rpu_sha256=sha256(check_rpu),
                      output=str(final), original_video_bytes=sample_video_bytes,
                      output_video_bytes=injected.stat().st_size, static_hdr_within_one_quantization_unit=True,
                      audio_subtitle_packets_unchanged=True)
        report['video_savings_percent'] = 100 * (1 - injected.stat().st_size / sample_video_bytes)
        report['minimum_video_savings_percent']=minimum_savings
        report['savings_scope']='Selected video payload only; full-file savings still require full encoding and measurement'
        report['space_saving_candidate'] = report['video_savings_percent'] > 0 and report['video_savings_percent'] >= minimum_savings
        if getattr(args,'measure_quality',False):
            from hdr_auto import measure_prefix_quality
            guard.phase='Measuring shared HDR quality'
            guard.status(95)
            report['quality']=measure_prefix_quality(args.ffmpeg,clip,final,directory,len(frames),rate,guard)
            report['sample_qualified']=bool(report['space_saving_candidate'] and report['quality']['candidate']['passed'])
        print(f'STRUCTURAL CHECKS PASSED: {final}\nDolby Vision player review still required.', flush=True)
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='failed', error=str(exc) or 'Interrupted')
        print(f'STOPPED: {report["error"]}. All files retained.', flush=True)
    finally:
        after = source.stat()
        report['original_stat_unchanged'] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        if not report['original_stat_unchanged']:
            report.update(status='failed', error='Original stat changed externally during test')
        with (directory / 'validation.json').open('x', encoding='utf-8') as out:
            json.dump(report, out, indent=2)
        guard.phase = report['status']
        guard.status(100 if report['status'].startswith('verified') else 0)
        print(f'REPORT: {directory / "validation.json"}', flush=True)
    return 0 if report['status'].startswith('verified') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--execute', action='store_true')
    hardware = parser.add_mutually_exclusive_group()
    hardware.add_argument('--experimental-intel', action='store_true', help='Explicit bounded Intel Profile 8.1 research sample; normal/full-file gate unchanged')
    hardware.add_argument('--experimental-nvidia', action='store_true', help='Explicit bounded NVIDIA Profile 8.1 research sample; does not enable general/full-file preservation')
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--nvenc-cq',type=int,choices=range(18,33),help='Bounded NVIDIA quality/size trial; all preservation and quality checks still required')
    parser.add_argument('--measure-quality',action='store_true',help='Measure shared HDR base-layer quality after preservation checks')
    parser.add_argument('--minimum-savings-percent',type=float,default=10,help='Minimum sampled video-payload reduction; not proof of full-file savings')
    parser.add_argument('--experimental-hdr10plus',action='store_true',help='Opt-in combined DV Profile 8.1/HDR10+ sample research only; production guard remains unchanged')
    parser.add_argument('--start', type=float, default=0, help='Seek near this time; starts at preceding keyframe')
    parser.add_argument('--qp-i', type=int, default=18, help='Experimental I-frame QP (0..51); higher compresses more')
    parser.add_argument('--qp-p', type=int, default=20, help='Experimental P-frame QP (0..51); higher compresses more')
    parser.add_argument('--work-dir', type=Path, default=Path('reports'))
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    parser.add_argument('--dovi-tool', default=str(Path(__file__).parent.parent / 'tools/dovi_tool-2.3.3/dovi_tool.exe'))
    return run(parser.parse_args())


if __name__ == '__main__':
    from job_tracking import tracked_call
    raise SystemExit(tracked_call(main, 'Dolby Vision sample'))
