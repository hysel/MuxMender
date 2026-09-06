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
import mux_integrity as nvidia_mux
import job_tracking as jobs
import dv_preservation_test as dv
from streaming_pipeline import RunGuard, chapter_summary
from run_logged import Tee
import validate_nvidia as nv
from mux_integrity import verify_startup_interleaving, verify_seek_interleaving
from mux_integrity import savings_decision, NoSavingsError, savings_summary, savings_summary_text


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


def timestamped_video_command(ffmpeg, injected, output, rate):
    """Materialize raw HEVC timestamps before it shares a mux queue with audio."""
    return [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n',
            '-r', rate, '-i', str(injected), '-map', '0:v:0', '-c', 'copy',
            '-bsf:v', 'dovi_rpu=compression=none', '-avoid_negative_ts', 'disabled',
            '-progress', 'pipe:1', '-nostats', str(output)]


def ordered_dv_mux_command(ffmpeg, video, source, output, streams):
    command = nvidia_mux.finalize_command(video, source, output, streams, ffmpeg)
    # Sparse subtitle gaps must not force premature video/audio queue flushing.
    # Explicit DV experiment only; ordinary optimizer defaults remain unchanged.
    command[command.index('-max_interleave_delta')+1] = '0'
    command[-1:-1] = ['-progress', 'pipe:1', '-nostats']
    return command


def nvidia_savings_preflight(args):
    """Bounded sample must shrink before any full-file NVIDIA encode starts."""
    root = args.work_dir.resolve()/('nvidia-size-preflight-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    root.mkdir(parents=True,exist_ok=False)
    sample_args = argparse.Namespace(source=args.source, execute=True,
        experimental_nvidia=True, seconds=30, start=0, work_dir=root,
        ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, dovi_tool=args.dovi_tool)
    result = dv.run(sample_args)
    reports = list(root.glob('dv81-*/validation.json'))
    if result or len(reports) != 1:
        raise ValueError('Bounded NVIDIA sample did not pass; full-file encode not started')
    sample = json.loads(reports[0].read_text(encoding='utf-8'))
    if not sample.get('status','').startswith('verified') or not sample.get('original_stat_unchanged'):
        raise ValueError('Sample preservation failed; full-file encode not started')
    decision = savings_decision(sample['original_video_bytes'],sample['output_video_bytes'],
                                getattr(args,'min_savings',5.0))
    sample['optimization_decision'] = dict(decision, basis='selected sample video payload; whole-file container savings checked separately')
    if not decision['eligible']:
        sample.update(structural_status=sample['status'],status='skipped',
                      error=decision['reason'],full_file_encode_started=False)
    reports[0].write_text(json.dumps(sample,indent=2),encoding='utf-8')
    return decision


def run(args):
    minimum = getattr(args, 'min_savings', 5.0)
    savings_decision(1, 1, minimum)  # Validate before reading or encoding media.
    info = mm.probe(args.source, args.ffprobe)
    dv.require_candidate(info)
    if not math.isfinite(info.duration_seconds) or not 0 < info.duration_seconds <= 86400:
        raise ValueError('Requires a known duration of at most 24 hours')
    nvidia = getattr(args, 'experimental_nvidia', False)
    options = dv.sample_encoder_options(info, True) if nvidia else dv.experimental_encoder_options(info, args.qp_i, args.qp_p)
    encoder = 'hevc_nvenc' if nvidia else 'hevc_amf'
    for tool in (args.ffmpeg, args.ffprobe, args.dovi_tool):
        if not shutil.which(tool):
            raise ValueError(f'Missing tool: {tool}; no automatic installation')
    print(f'FULL-FILE PLAN: {info.duration_seconds:.3f}s; {info.width}x{info.height}; {encoder}; Profile 8.1', flush=True)
    if not args.execute:
        print('DRY RUN: no encoding or output files created')
        return 0
    if encoder not in mm.ffmpeg_encoder_names(args.ffmpeg):
        raise ValueError(f'{encoder} missing; no CPU fallback')
    if nvidia and 'nvidia' not in mm.gpu_vendors():
        raise ValueError('NVIDIA GPU not detected; no CPU fallback')
    if nvidia:
        decision = nvidia_savings_preflight(args)
        if not decision['eligible']:
            print(f"SKIPPED: {decision['reason']}. No full-file encode; original retained.",flush=True)
            return 0
    args.work_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.work_dir).free < 4 * info.size_bytes + 2 * 1024**3:
        raise ValueError('Insufficient reserve for retained compressed intermediates')
    directory = args.work_dir / ('dv-full-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(exist_ok=False)
    guard = (dv.NvidiaSampleGuard if nvidia else RunGuard)(directory, reserve=2 * 1024**3)
    before = args.source.stat()
    report = {'status': 'running', 'source': str(args.source), 'commands': [],
              'qp_i': args.qp_i, 'qp_p': args.qp_p, 'scope': 'full-file Profile 8.1 experimental',
              'quality_note': 'Metadata validation does not prove identical visual quality.'}
    if nvidia:
        report.update(encoder_settings={'encoder': encoder, 'options': options},
                      scope='explicit NVIDIA full-file Profile 8.1 experiment; normal AMD gate unchanged')
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
                started = time.monotonic()
                result = np.stage([str(c) for c in command], info.duration_seconds, offset, span,
                                  timeout=timeout, stall=0, guard=guard)
                report.setdefault('stage_seconds', {})[phase] = time.monotonic()-started
                return result
            ff = [args.ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n']
            progress = ['-progress', 'pipe:1', '-nostats']
            guard.phase = 'source inspection'
            guard.status(0)
            source_pts, source_bytes = video_packets(args.ffprobe, args.source)
            streams = {'streams': dv.stream_info(args.ffprobe, args.source)}
            stream = next(s for s in streams['streams'] if s['codec_type'] == 'video')
            rate = stream['r_frame_rate']
            step = 1 / float(dv.Fraction(rate))
            if not source_pts or abs(source_pts[0]) > .002 or any(abs(b-a-step) > .002 for a,b in zip(source_pts, source_pts[1:])):
                raise ValueError('Only continuous constant-rate video starting at zero is supported')
            if nvidia:
                import dv_nvidia_validation as audit
                nv.first_video(streams)
                if any(s['codec_type'] not in ('video','audio','subtitle','attachment') for s in streams['streams']):
                    raise ValueError('Unsupported original track type')
                guard.phase = 'Inspect every source frame for HDR and DV metadata'
                guard.status(0)
                source_frames = directory/'source-frames.compact'
                report['commands'].append(audit.frame_evidence(args.ffprobe, args.source, source_frames, guard))
                audit.validate_source_frames(source_frames, source_pts, guard)
            raw, rpu, encoded, injected, final = [directory / n for n in
                ('original.hevc', 'original-rpu.bin', 'encoded.hevc', 'injected.hevc', mm.clean_media_name(args.source))]
            if getattr(args, 'video_only_folder', False):
                final = directory / 'media' / final.name
                final.parent.mkdir(exist_ok=False)
            stage(ff + ['-i', args.source, '-map', '0:v:0', '-c', 'copy', '-bsf:v', 'hevc_mp4toannexb', '-f', 'hevc', *progress, raw], 'extract source bitstream', 0, 8)
            stage([args.dovi_tool, 'extract-rpu', '-i', raw, '-o', rpu], 'extract full RPU', 8, 2)
            stage(ff + ['-threads', '0' if nvidia else '2', '-i', args.source, '-map', '0:v:0', *options,
                  '-profile:v', 'main10', '-fps_mode', 'passthrough', '-f', 'hevc', *progress, encoded], f'{encoder} full encode', 10, 55)
            if nvidia and shutil.disk_usage(directory).free < 4*encoded.stat().st_size + 3*1024**3:
                raise ValueError('Insufficient room for injection, final mux and retained verification copy')
            stage([args.dovi_tool, 'inject-rpu', '-i', encoded, '--rpu-in', rpu, '-o', injected], 'inject full RPU', 65, 5)
            mux = mux_command(args.ffmpeg, args.source, injected, final, rate)
            if nvidia:
                timestamped = directory/'timestamped-dv-video.mkv'
                stage(timestamped_video_command(args.ffmpeg, injected, timestamped, rate),
                      'materialize DV video timestamps', 70, 0)
                mux = ordered_dv_mux_command(args.ffmpeg, timestamped, args.source, final, streams)
            stage(mux, 'copy all audio subtitles chapters', 70, 5)
            decision = savings_decision(info.size_bytes, final.stat().st_size, minimum)
            report['optimization_decision'] = decision
            if not decision['eligible']:
                report.update(status='skipped', error=decision['reason'],
                              output=str(final.resolve()), publication_allowed=False)
                print(f"SKIPPED: {decision['reason']}; output not accepted for publication.",flush=True)
                raise NoSavingsError(decision['reason'])
            guard.phase = 'validate streams and timestamps'
            guard.status(75)
            if nvidia:
                seek_ok, seek_checks = verify_seek_interleaving(final, args.ffprobe,
                    [info.duration_seconds * fraction for fraction in (0, .1, .25, .5, .75, .9)])
                report['seek_interleaving'] = seek_checks
                if not seek_ok:
                    raise ValueError('Audio/video packet ordering failed seek-point validation')
            output_info = mm.probe(final, args.ffprobe)
            dv.require_candidate(output_info)
            if nvidia:
                final_streams = {'streams': dv.stream_info(args.ffprobe, final)}
                if nv.stream_inventory(streams) != nv.stream_inventory(final_streams):
                    raise ValueError('Original stream inventory/dispositions changed')
                if stream.get('sample_aspect_ratio') != nv.first_video(final_streams).get('sample_aspect_ratio'):
                    raise ValueError('Sample aspect ratio changed')
                passed, detail = verify_startup_interleaving(final, args.ffprobe)
                report['startup_interleaving'] = {'passed': passed, 'detail': detail}
                if not passed:
                    raise ValueError(detail)
            for field in ('width', 'height', 'bit_depth', 'color_primaries', 'color_transfer', 'color_space', 'color_range', 'audio_codecs', 'subtitle_codecs'):
                if getattr(info, field) != getattr(output_info, field):
                    raise ValueError(f'Changed {field}')
            output_pts, output_bytes = video_packets(args.ffprobe, final)
            if len(source_pts) != len(output_pts) or any(abs(a-b) > .002 for a,b in zip(source_pts,output_pts)):
                raise ValueError('Full frame-packet timeline mismatch')
            for selector in ('a', 's', 't'):
                guard()
                source_packets = np.packet_signatures(args.ffprobe, args.source, selector, timeout=600)
                final_packets = np.packet_signatures(args.ffprobe, final, selector, timeout=600)
                if nvidia:
                    rounded = audit.compare_track_packets(source_packets, final_packets, streams['streams'])
                    for index, count in rounded.items():
                        hashes = []
                        for label, path in (('source', args.source), ('output', final)):
                            text = stage(ff + ['-v','error','-xerror','-i',path,'-map',f'0:{index}',
                                               '-c:a','pcm_s32le','-f','hash','-hash','sha256','-'],
                                         f'Validate decoded {label} AAC track {index}',75,0)
                            hashes.append(next(line.strip() for line in text.splitlines() if line.startswith('SHA256=')))
                        if hashes[0] != hashes[1]:
                            raise ValueError('Decoded AAC audio changed')
                        report.setdefault('aac_duration_rounding', {})[index] = dict(packets=count, decoded_pcm_identical=True, sha256=hashes[0])
                elif source_packets != final_packets:
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
            if nvidia:
                guard.phase = 'Compare every decoded output frame and static HDR value'
                guard.status(80)
                output_frames = directory/'output-frames.compact'
                report['commands'].append(audit.frame_evidence(args.ffprobe, final, output_frames, guard))
                report['decoded_frame_checks'] = audit.compare_frames(source_frames, output_frames, guard)
            stage(ff + ['-v', 'error', '-xerror', '-threads', '0' if nvidia else '2', '-i', final, '-map', '0:v:0',
                        *(['-map', '0:a?'] if nvidia else []), '-f', 'null', '-', *progress], 'complete output decode', 80, 20)
            report.update(status='verified-full-file-awaiting-playback', output=str(final.resolve()), frames=len(source_pts),
                rpu_content_digest=digests[0][1], rpu_byte_identical=dv.sha256(rpu)==dv.sha256(check_rpu),
                audio_subtitle_packets_unchanged=True, chapters_unchanged=True,
                source_bytes=info.size_bytes, output_bytes=final.stat().st_size,
                video_savings_percent=100*(1-output_bytes/source_bytes), total_savings_percent=100*(1-final.stat().st_size/info.size_bytes))
            if report.get('aac_duration_rounding'):
                report['audio_subtitle_packets_unchanged'] = False
                report['packet_payloads_order_and_pts_unchanged'] = True
                report['audio_note'] = 'AAC duration fields rounded by at most 1ms; decoded PCM hashes are identical. Packet bytes and presentation timestamps are exact.'
            if minimum is not None and report['total_savings_percent'] < minimum:
                raise ValueError(f"Output passed structural checks but saved only {report['total_savings_percent']:.2f}%; requires {minimum}%. Output retained, not accepted.")
            report['artwork'] = mm.copy_matching_artwork(args.source, final, getattr(args, 'video_only_folder', False))
            report['video_only_folder'] = getattr(args, 'video_only_folder', False)
        except NoSavingsError as exc:
            report.update(status='skipped',error=str(exc),publication_allowed=False)
        except (Exception, KeyboardInterrupt) as exc:
            report.update(status='failed', error=str(exc) or 'Interrupted')
            print(f'STOPPED: {report["error"]}; all files retained', flush=True)
        finally:
            after = args.source.stat()
            report['original_stat_unchanged'] = (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
            if not report['original_stat_unchanged']:
                report.update(status='failed', error='Source stat changed during execution')
            report['savings_summary'] = savings_summary(
                [(report['source_bytes'], report['output_bytes'])]
                if report['status'].startswith('verified') else [])
            print(savings_summary_text(report['savings_summary']), flush=True)
            with (directory/'validation.json').open('x',encoding='utf-8') as out:
                json.dump(report,out,indent=2)
            guard.phase = report['status']
            guard.status(100 if report['status'].startswith('verified') or report['status']=='skipped' else 0)
            print(f'RESULT: {report["status"]}\nREPORT: {directory / "validation.json"}',flush=True)
            sys.stdout = terminal
    return 0 if report['status'].startswith('verified') or report['status']=='skipped' else 1


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
            min_savings=args.min_savings, video_only_folder=getattr(args, 'video_only_folder', False)))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'BLOCKED: {exc}; original and any partial output retained')
        return 4


def verify_existing(parent):
    full = sys.modules[__name__]
    import dv_nvidia_validation as audit
    parent = parent.resolve(strict=True)
    previous = json.loads((parent/'validation.json').read_text(encoding='utf-8'))
    if previous.get('encoder_settings',{}).get('encoder') != 'hevc_nvenc' or not previous.get('original_stat_unchanged'):
        raise ValueError('Requires a retained NVIDIA run with unchanged-source evidence')
    source, output = Path(previous['source']), parent/'episode-dolby-vision.mkv'
    directory = parent/('verification-'+time.strftime('%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir()
    guard = dv.NvidiaSampleGuard(directory, reserve=2*1024**3)
    initial = (source.stat().st_size, source.stat().st_mtime_ns)
    report = dict(status='running',source=str(source),output=str(output),parent_run=str(parent),commands=[],
                  scope='Full NVIDIA Profile 8.1 preservation verification; playback review separate')
    ffmpeg, ffprobe = nv.find_tool('ffmpeg'), nv.find_tool('ffprobe')
    dovi = str(Path('tools/dovi_tool-2.3.3/dovi_tool.exe').resolve())
    duration = 0.0
    ff = [ffmpeg,'-hide_banner','-nostdin','-n']
    def stage(command,label,percent):
        guard.phase=label; guard.status(percent); guard()
        report['commands'].append([str(c) for c in command])
        print(label,flush=True)
        return np.stage([str(c) for c in command],duration,timeout=3600,stall=0,guard=guard)
    try:
        decision=savings_decision(source.stat().st_size,output.stat().st_size)
        report['optimization_decision']=decision
        if not decision['eligible']:
            report.update(status='skipped',error=decision['reason'],publication_allowed=False)
            print('SKIPPED: output does not reduce size; no acceptance or publication.',flush=True)
            return 0
        guard.phase='Verify original tracks and timestamps'; guard.status(0)
        before, after = mm.probe(source,ffprobe), mm.probe(output,ffprobe)
        duration = before.duration_seconds
        dv.require_candidate(before); dv.require_candidate(after)
        for field in ('width','height','bit_depth','pixel_format','color_primaries','color_transfer','color_space','color_range'):
            if getattr(before,field) != getattr(after,field): raise ValueError(f'Changed {field}')
        streams, final_streams = {'streams':dv.stream_info(ffprobe,source)}, {'streams':dv.stream_info(ffprobe,output)}
        if nv.stream_inventory(streams) != nv.stream_inventory(final_streams): raise ValueError('Track inventory/dispositions changed')
        if nv.first_video(streams).get('sample_aspect_ratio') != nv.first_video(final_streams).get('sample_aspect_ratio'): raise ValueError('Aspect ratio changed')
        source_pts, source_video_bytes = full.video_packets(ffprobe,source)
        final_pts, final_video_bytes = full.video_packets(ffprobe,output)
        if len(source_pts)!=len(final_pts) or any(abs(a-b)>.002 for a,b in zip(source_pts,final_pts)): raise ValueError('Video packet timeline changed')
        rounding={}
        for selector in ('a','s','t'):
            guard()
            a=np.packet_signatures(ffprobe,source,selector,600)
            b=np.packet_signatures(ffprobe,output,selector,600)
            rounding.update(audit.compare_track_packets(a,b,streams['streams']))
        report['aac_duration_rounding_packets']=rounding
        report['decoded_pcm_checks']={}
        for index in rounding:
            hashes=[]
            for label,path in (('source',source),('output',output)):
                result=stage(ff+['-v','error','-xerror','-i',path,'-map',f'0:{index}','-c:a','pcm_s32le','-f','hash','-hash','sha256','-'],f'Decode {label} AAC track {index} to PCM hash',15)
                hashes.append(next(line.strip() for line in result.splitlines() if line.startswith('SHA256=')))
            if hashes[0]!=hashes[1]: raise ValueError('Decoded AAC audio changed')
            report['decoded_pcm_checks'][index]=dict(identical=True,sha256=hashes[0])
        if chapter_summary(ffprobe,source,60)!=chapter_summary(ffprobe,output,60): raise ValueError('Chapters changed')
        passed,detail=verify_startup_interleaving(output,ffprobe)
        if not passed: raise ValueError(detail)
        report['startup_interleaving']=detail
        fresh=directory/'current-source.hevc'
        stage(ff+['-v','error','-i',source,'-map','0:v:0','-c','copy','-bsf:v','hevc_mp4toannexb','-f','hevc',fresh],'Confirm current source bitstream matches audited frames',25)
        if dv.sha256(fresh)!=dv.sha256(parent/'original.hevc'): raise ValueError('Source bitstream changed since frame audit')
        audit.validate_source_frames(parent/'source-frames.compact',source_pts,guard)
        check_raw, check_rpu = directory/'final-check.hevc', directory/'final-rpu.bin'
        stage(ff+['-v','error','-i',output,'-map','0:v:0','-c','copy','-bsf:v','hevc_mp4toannexb','-f','hevc',check_raw],'Extract final DV bitstream',35)
        stage([dovi,'extract-rpu','-i',check_raw,'-o',check_rpu],'Extract final DV metadata',40)
        digests=[]
        for name,binary in (('source',parent/'original-rpu.bin'),('output',check_rpu)):
            target=directory/(name+'-rpu.json')
            stage([dovi,'export','-i',binary,'-d',f'all={target}'],f'Compare complete {name} RPU metadata',45)
            digests.append(full.rpu_digest(target,guard))
        if digests[0]!=digests[1] or digests[0][0]!=len(source_pts): raise ValueError('RPU content/count/frame order changed')
        report['rpu_content_digest']=digests[0][1]
        guard.phase='Compare every decoded frame and HDR value'; guard.status(60)
        frames=directory/'output-frames.compact'
        report['commands'].append(audit.frame_evidence(ffprobe,output,frames,guard))
        report['decoded_frame_checks']=audit.compare_frames(parent/'source-frames.compact',frames,guard)
        stage(ff+['-v','error','-xerror','-threads','0','-i',output,'-map','0:v:0','-map','0:a?','-f','null','-','-progress','pipe:1','-nostats'],'Full output video/audio decode',80)
        if initial!=(source.stat().st_size,source.stat().st_mtime_ns): raise ValueError('Source stat changed during verification')
        report.update(status='verified-full-file-awaiting-playback',frames=len(source_pts),
                      source_bytes=source.stat().st_size,output_bytes=output.stat().st_size,
                      total_savings_percent=100*(1-output.stat().st_size/source.stat().st_size),
                      video_savings_percent=100*(1-final_video_bytes/source_video_bytes),
                      original_stat_unchanged=True,full_audio_video_decode=True,chapters_unchanged=True,
                      packet_payloads_order_and_pts_unchanged=True,
                      encode_seconds=previous['stage_seconds']['hevc_nvenc full encode'],
                      encode_speed_x=duration/previous['stage_seconds']['hevc_nvenc full encode'],
                      duration_seconds=duration)
        print('Full NVIDIA Dolby Vision checks passed; playback review required.',flush=True)
        return 0
    except Exception as exc:
        report.update(status='failed',error=str(exc)); print(f'FAILED: {exc}',flush=True)
        return 1
    finally:
        (directory/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        guard.phase=report['status']; guard.status(100 if report['status'].startswith('verified') or report['status']=='skipped' else 0)
        print(f'Report: {directory / "validation.json"}',flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, nargs='?')
    parser.add_argument('--verify-existing', type=Path, help='Verify a retained run without encoding')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--video-only-folder', action='store_true', help='Place accepted video alone in the run media folder; omit artwork and external subtitles, retain embedded tracks and sources')
    parser.add_argument('--experimental-nvidia', action='store_true', help='Explicit research run only; normal optimizer remains AMD-only')
    parser.add_argument('--min-savings', type=float, default=5.0, help='Minimum percentage reduction; larger/equal outputs are always rejected')
    parser.add_argument('--qp-i',type=int,default=21)
    parser.add_argument('--qp-p',type=int,default=23)
    parser.add_argument('--work-dir',type=Path,default=Path('reports'))
    parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--dovi-tool',default=str(Path(__file__).parent/'tools/dovi_tool-2.3.3/dovi_tool.exe'))
    args = parser.parse_args()
    if args.verify_existing:
        if args.source or args.execute:
            parser.error('--verify-existing cannot be combined with source/execute')
        return verify_existing(args.verify_existing)
    if args.source is None:
        parser.error('source is required unless --verify-existing is used')
    return run(args)


if __name__ == '__main__':
    from job_tracking import tracked_call
    raise SystemExit(tracked_call(main, 'Full Dolby Vision preservation'))
