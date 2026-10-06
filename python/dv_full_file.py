"""Explicit experimental Profile 8.1 full-file safe-copy test; dry run by default."""
import argparse
import itertools
import subprocess
from fractions import Fraction
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
import dv_tracks
from streaming_pipeline import RunGuard, chapter_summary, verify_chapters_preserved
from run_logged import Tee
import validate_nvidia as nv
from mux_integrity import verify_startup_interleaving, verify_seek_interleaving
from mux_integrity import savings_decision, NoSavingsError, savings_summary, savings_summary_text


def grouped_packets(packets):
    """Allow mux interleaving changes, but preserve order within every track."""
    groups = {}
    for packet in packets:
        groups.setdefault(packet['stream_index'], []).append(packet)
    return groups

def compare_track_packets(before, after, streams):
    """Exact bytes/order/PTS; report AAC duration representation separately.

    Caller must prove decoded PCM, sample count and presentation timing for
    every returned track using decoded_track_proof. Missing durations are not
    invented and do not by themselves approve a track.
    """
    left, right = grouped_packets(before), grouped_packets(after)
    if left.keys() != right.keys():
        raise ValueError('Track packet inventory changed')
    info = {s['index']: s for s in streams}
    rounded = {}
    for index, packets in left.items():
        if len(packets) != len(right[index]):
            raise ValueError('Track packet count changed')
        for ordinal, (a, b) in enumerate(zip(packets, right[index]),1):
            if a == b:
                continue
            if {k:v for k,v in a.items() if k != 'duration_time'} != {k:v for k,v in b.items() if k != 'duration_time'}:
                fields=sorted(k for k in a.keys() | b.keys()
                              if k!='duration_time' and a.get(k)!=b.get(k))
                key=fields[0]
                raise ValueError('Track packet bytes, sequence or timestamps changed: '
                    f'track {index}, packet {ordinal}, {key}: {a.get(key)!r} -> {b.get(key)!r}')
            stream = info[index]
            if stream.get('codec_type') != 'audio' or stream.get('codec_name') != 'aac' or stream.get('time_base') != '1/1000':
                raise ValueError('Unexpected packet duration change')
            try:
                x=Fraction(a['duration_time'])
                if b.get('duration_time') in (None,'N/A'):
                    if x<=0:raise ValueError('Invalid source AAC duration')
                    rounded[index]=rounded.get(index,0)+1
                    continue
                y=Fraction(b['duration_time'])
            except (KeyError,TypeError,ZeroDivisionError) as exc:
                raise ValueError('Unresolved AAC duration evidence') from exc
            if min(x,y) <= 0 or abs(x-y) > Fraction(1,1000):
                raise ValueError('AAC duration change exceeds one Matroska millisecond')
            rounded[index] = rounded.get(index, 0)+1
    return rounded


def decoded_track_proof(ff,source,output,index,directory,execute):
    """Shared audio proof includes timing, not merely concatenated PCM bytes."""
    from packet_validation import compare_decoded_audio
    evidence=[]
    for label,path in [('source',source),('output',output)]:
        target=Path(directory)/f'aac-{index}-{label}-presentation.framehash'
        execute(ff+['-v','error','-xerror','-copyts','-threads','2','-i',str(path),'-map',f'0:{index}',
                    '-c:a','pcm_f64le','-progress','pipe:1','-nostats','-f','framehash','-hash','sha256',str(target)],
                f'Validate decoded {label} AAC track {index} and presentation timing')
        evidence.append(target)
    return compare_decoded_audio(*evidence)

def frame_evidence_timeout(duration):
    """Bound full-frame work without assuming a short file or an idle CPU."""
    if duration is None:return 3600
    duration=float(duration)
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid frame-audit duration')
    return max(3600,min(24*3600,duration*4+300))


def frame_evidence(ffprobe, source, output, guard, timeout=None):
    from validation_resources import validation_slot
    from job_tracking import measured_operation,progress
    with measured_operation('validation_wait'):
        with validation_slot([ffprobe,'-show_frames'],guard):
            progress(guard.phase,detail='CPU inspection: collecting complete frame metadata')
            with measured_operation('frame_validation'):
                return _frame_evidence(ffprobe,source,output,guard,timeout)


def _frame_evidence(ffprobe, source, output, guard, timeout=None):
    from runtime_support import frame_evidence_percent, TerminalProgress
    timeout=frame_evidence_timeout(getattr(guard,'duration',None)) if timeout is None else timeout
    if not math.isfinite(timeout) or timeout<=0:raise ValueError('Invalid frame-audit timeout')
    display = TerminalProgress(label=guard.phase, machine=False)
    fields = ('side_data_type,red_x,red_y,green_x,green_y,blue_x,blue_y,'
              'white_point_x,white_point_y,min_luminance,max_luminance,max_content,max_average')
    from decoder_context import metadata_reader_options
    from resource_governor import hdr_validation_threads
    duration=getattr(guard,'duration',None)
    threads=hdr_validation_threads() if duration is not None and float(duration)>=300 else 2
    command = [ffprobe, '-v', 'error', *metadata_reader_options(threads), '-select_streams', 'V:0',
               '-show_frames', '-show_entries',
               'frame=best_effort_timestamp_time,interlaced_frame,repeat_pict,width,height,pix_fmt,sample_aspect_ratio,color_range,color_space,color_transfer,color_primaries,chroma_location:frame_side_data=' + fields,
               '-of', 'compact', str(source)]
    if getattr(guard,'allow_hdr10plus',False):
        command=[ffprobe,'-v','error',*metadata_reader_options(threads),'-select_streams','V:0',
                 '-show_frames','-of','json=compact=1',str(source)]
    started = last = time.monotonic()
    with Path(output).open('xb') as out, Path(str(output)+'.log').open('xb') as err:
        process = subprocess.Popen(command, stdout=out, stderr=err)
        try:
            while process.poll() is None:
                guard()
                now = time.monotonic()
                if now-started > timeout:
                    raise RuntimeError('Frame evidence timeout; all files retained')
                if now-last > 15:
                    percent = frame_evidence_percent(output, getattr(guard, 'duration', None))
                    if percent is None:
                        print(f'{guard.phase}: {now-started:.0f}s elapsed', flush=True)
                    else:
                        display.update(percent)
                        dv.jobs.stage_progress(percent, display.eta_seconds)
                    last = now
                time.sleep(.5)
            if process.returncode:
                raise RuntimeError(f'Frame decode failed; see {output}.log')
            if Path(str(output)+'.log').stat().st_size:
                raise ValueError(f'Frame decoder reported errors; see {output}.log')
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
    return command

def frames(path, allow_hdr10plus=False):
    if allow_hdr10plus:
        from hdr10plus_preserve import frame_records
        for frame in frame_records(path):
            dv.require_nvidia_frames([frame],allow_hdr10plus=True)
            if not any(s.get('side_data_type')=='Dolby Vision RPU Data' for s in frame.get('side_data_list',[])):
                raise ValueError('A decoded frame lacks Dolby Vision RPU data')
            yield frame
        return
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                continue
            if not line.startswith('frame|'):
                raise ValueError('Unexpected frame evidence record')
            fields, side = {}, {}
            for item in line.strip().split('|')[1:]:
                key, separator, value = item.partition('=')
                if not separator:
                    raise ValueError('Malformed frame evidence field')
                if key.startswith('side_datum/'):
                    group, key = key.split(':', 1)
                    side.setdefault(group, {})[key] = value
                elif ':' not in key:
                    fields[key] = value
            fields['interlaced_frame'] = int(fields['interlaced_frame'])
            fields['repeat_pict'] = int(fields['repeat_pict'])
            fields['side_data_list'] = list(side.values())
            dv.require_nvidia_frames([fields])
            if not any('Dolby Vision RPU Data' == s.get('side_data_type') for s in side.values()):
                raise ValueError('A decoded frame lacks Dolby Vision RPU data')
            yield fields

def validate_source_frames(path, expected_pts, guard=lambda: None):
    count = 0
    previous = None
    for frame, timestamp in itertools.zip_longest(frames(path,getattr(guard,'allow_hdr10plus',False)), expected_pts):
        guard()
        if frame is None or timestamp is None:
            raise ValueError('Source decoded-frame and packet timelines differ')
        pair = frame_timestamp(frame), frame_timestamp({'best_effort_timestamp_time': timestamp})
        if abs(pair[0]-pair[1]) > Fraction(1,500):
            raise ValueError('Source decoded-frame and packet timelines differ')
        if previous is not None and any(b <= a for a,b in zip(previous,pair)):
            raise ValueError('Source presentation timeline is not increasing')
        previous = pair
        count += 1
    return count


def frame_timestamp(frame):
    """Exact finite presentation time; NaN must never pass an error comparison."""
    try:
        return Fraction(str(frame['best_effort_timestamp_time']))
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        raise ValueError('Missing or invalid decoded-frame timestamp') from None

def frame_picture_signature(frame):
    """Compare source-derived geometry/color, not an allowlist of resolutions."""
    try:
        width, height = int(frame['width']), int(frame['height'])
        pixel_format = frame['pix_fmt']
        if width <= 0 or height <= 0 or not pixel_format:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ValueError('Incomplete decoded-frame geometry; refresh frame evidence') from None
    sar = frame.get('sample_aspect_ratio')
    if sar not in (None, '', 'N/A', '0:1'):
        try:
            sar = Fraction(str(sar).replace(':', '/'))
            if sar <= 0:raise ValueError()
        except (ValueError, ZeroDivisionError):
            raise ValueError('Invalid decoded-frame aspect ratio') from None
    else:
        sar = None
    color = tuple(frame.get(key) or 'unknown' for key in (
        'color_range', 'color_space', 'color_transfer', 'color_primaries', 'chroma_location'))
    return width, height, pixel_format, sar, color


def picture_evidence_complete(path, guard=lambda: None):
    count = 0
    for frame in frames(path, getattr(guard, 'allow_hdr10plus', False)):
        guard()
        if any(key not in frame for key in ('width', 'height', 'pix_fmt')):
            return False
        frame_picture_signature(frame)
        count += 1
    return count > 0


def compare_frames(source, output, guard=lambda: None):
    count, rounded = 0, 0
    previous = None
    combined=getattr(guard,'allow_hdr10plus',False)
    for before, after in itertools.zip_longest(frames(source,combined), frames(output,combined)):
        guard()
        if before is None or after is None:
            raise ValueError('Decoded frame count changed')
        pair = frame_timestamp(before), frame_timestamp(after)
        if abs(pair[0]-pair[1]) > Fraction(1,500):
            raise ValueError('Decoded frame timing changed')
        if previous is not None and any(b <= a for a,b in zip(previous,pair)):
            raise ValueError('Decoded presentation timeline is not increasing')
        previous = pair
        if frame_picture_signature(before) != frame_picture_signature(after):
            keys=('width','height','pix_fmt','sample_aspect_ratio','color_range','color_space',
                  'color_transfer','color_primaries','chroma_location')
            changed={k:dict(source=before.get(k),output=after.get(k)) for k in keys if before.get(k)!=after.get(k)}
            raise ValueError('Decoded frame geometry, aspect ratio or color signaling changed: '
                             +json.dumps(dict(frame=count,pts=str(pair[0]),fields=changed),sort_keys=True))
        if dv.compare_static_hdr([before], [after]):
            rounded += 1
        if combined and dv.hdr10plus_metadata(before)!=dv.hdr10plus_metadata(after):
            raise ValueError('Full HDR10+ content or decoded-frame alignment changed')
        count += 1
    if not count:
        raise ValueError('No decoded frames')
    return dict(frames=count, static_hdr_rounding_frames=rounded,
                timing_preserved=True, static_hdr_preserved=True, frame_picture_preserved=True,
                progressive=True, rpu_present_every_frame=True,
                hdr10plus_preserved=combined)


def final_decode_maps(streams, frame_checks, expected_frames):
    """Reuse only a complete, strict, source-matched video frame audit.

    Called with the in-memory result immediately after frame_evidence and
    compare_frames, never with a historical status file as authorization.
    Audio still needs a complete strict decode even when its packets match.
    """
    required=('timing_preserved','static_hdr_preserved','frame_picture_preserved',
              'progressive','rpu_present_every_frame')
    reuse=bool(expected_frames and frame_checks.get('frames')==expected_frames
               and all(frame_checks.get(key) is True for key in required))
    return np.decode_maps_after_frame_audit(streams,expected_frames if reuse else None)

def rpu_digest(path, guard=lambda: None, *, inspect=None):
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
                if buffer.strip():
                    raise ValueError('Trailing data in RPU export')
                while True:
                    guard()
                    tail = stream.read(65536)
                    if not tail:
                        break
                    if tail.strip():
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
            if end > 8 * 1024**2:
                raise ValueError('Oversized RPU entry')
            if inspect is not None:
                inspect(value)
            digest.update(json.dumps(dv.canonical_rpu(value), sort_keys=True, separators=(',', ':')).encode())
            digest.update(b'\n')
            count += 1
            buffer = buffer[end:]
            expect_value = False


def video_packets(ffprobe, path):
    data = np.checked_json([ffprobe, '-v', 'error', '-select_streams', 'V:0', '-show_packets',
        '-show_entries', 'packet=pts_time,size', '-of', 'json', str(path)], timeout=600)
    packets = data['packets']
    return sorted(float(p['pts_time']) for p in packets), sum(int(p['size']) for p in packets)


def mux_command(ffmpeg, source, injected, output, rate):
    return [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n', '-r', rate,
        '-i', str(injected), '-i', str(source), '-map', '0:v:0', '-map', '1:a?', '-map', '1:s?',
        '-map', '1:t?', '-map_metadata', '1', '-map_chapters', '1', '-c', 'copy',
        '-bsf:v', 'dovi_rpu=compression=none', '-avoid_negative_ts', 'disabled',
        '-progress', 'pipe:1', '-nostats', str(output)]


def timestamped_video_command(ffmpeg, injected, output, rate, intel=False, *, timestamps=None, mkvmerge='mkvmerge', preserve_enhancement=False):
    """Materialize raw HEVC timestamps before it shares a mux queue with audio."""
    if timestamps is not None or preserve_enhancement:
        # Research route for irregular decoded presentation times. Callers must
        # verify every reconstructed frame; supplying a clock is not approval.
        if Path(output).exists():raise ValueError('Timestamp output already exists')
        if Fraction(rate)<=0:raise ValueError('Positive fallback frame rate required')
        # FFmpeg's dovi_rpu filter can synthesize a single-layer Profile 8
        # configuration for raw layered input. Do not use it for retained EL.
        # This only chooses a mux mechanism: callers must independently verify
        # the configuration, every RPU, EL payload and all decoded timestamps.
        command=[mkvmerge,'-o',str(output),'--disable-lacing','--default-duration','0:'+rate+'fps']
        if timestamps is not None:command += ['--timestamps','0:'+str(timestamps)]
        return command+[str(injected)]
    bsf = "dovi_rpu=compression=none"
    if intel:
        cadence = Fraction(rate)
        bsf += (f",setts=pts=N*{cadence.denominator}/({cadence.numerator}*TB)"
                f":dts=N*{cadence.denominator}/({cadence.numerator}*TB)")
    return [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n',
            '-r', rate, '-i', str(injected), '-map', '0:v:0', '-c', 'copy',
            '-bsf:v', bsf, '-avoid_negative_ts', 'disabled',
            '-progress', 'pipe:1', '-nostats', str(output)]


def ordered_dv_mux_command(ffmpeg, video, source, output, streams, start_offset=0):
    command = nvidia_mux.finalize_command(video, source, output, streams, ffmpeg)
    if not math.isfinite(float(start_offset)):
        raise ValueError('DV video start offset must be finite')
    if start_offset:
        # Raw HEVC lost its timestamps; only the reconstructed video needs the
        # source offset. Original audio/subtitle timestamps must not move.
        first_input=command.index('-i')
        command[first_input:first_input]=['-itsoffset',str(start_offset)]
    # Keep ordered interleaving until an alternative passes memory and seeking
    # qualification. A finite-buffer trial preserved packets but failed seeking.
    command[command.index('-max_interleave_delta')+1] = '0'
    command[-1:-1] = ['-progress', 'pipe:1', '-nostats']
    return command


def copied_matroska_packetizer_options(streams,identified):
    """Preserve already packetized TrueHD Matroska audio, not codec-derived clocks.

    This changes transport only. All complete packet/PCM/frame/metadata and
    quality checks remain mandatory. Other source layouts retain their route.
    """
    container=identified.get('container',{})
    scale=container.get('properties',{}).get('timestamp_scale')
    if (container.get('type')=='Matroska' and type(scale) is int and 0<scale<=1000000000
            and any(s.get('codec_type')=='audio' and s.get('codec_name')=='truehd'
                    for s in streams['streams'])):
        return ['--engage','force_passthrough_packetizer','--timestamp-scale',str(scale)]
    return []


def matroska_dv_mux_command(video,source,output,streams,identified,start_offset=0,mkvmerge='mkvmerge'):
    """Two-input Matroska mux with original non-video tracks and bounded memory.

    Track IDs come from mkvmerge identification, never assumed from ffprobe.
    Callers still verify all packets, metadata, frame clocks and seek points.
    """
    if Path(output).exists():raise ValueError('DV mux output already exists')
    if not math.isfinite(float(start_offset)):raise ValueError('DV video start offset must be finite')
    original=[s for s in streams['streams'] if s.get('codec_type')!='attachment']
    tracks=identified.get('tracks',[])
    types={'video':'video','audio':'audio','subtitle':'subtitles'}
    if len(original)!=len(tracks) or any(types.get(s.get('codec_type'))!=t.get('type')
                                        for s,t in zip(original,tracks)):
        raise ValueError('Matroska track identification does not match source inventory')
    if any(type(t.get('id')) is not int or t['id']<0 for t in tracks) or len({t['id'] for t in tracks})!=len(tracks):
        raise ValueError('Matroska track IDs must be unique nonnegative integers')
    primary=dv_tracks.primary(streams['streams'])
    primary_position=next(i for i,s in enumerate(original) if s is primary)
    video_ids=[t['id'] for i,t in enumerate(tracks) if t['type']=='video' and i!=primary_position]
    order=','.join('0:0' if i==primary_position else '1:'+str(t['id']) for i,t in enumerate(tracks))
    flags=primary.get('disposition',{});tags=primary.get('tags',{})
    command=[mkvmerge,'-o',str(output),*copied_matroska_packetizer_options(streams,identified),
             '--disable-lacing','--track-order',order,
             '--no-audio','--no-subtitles','--no-attachments','--no-chapters','--no-global-tags',
             '--language','0:'+tags.get('language','und'),'--track-name','0:'+tags.get('title',''),
             '--default-track-flag','0:'+str(int(bool(flags.get('default')))),
             '--forced-display-flag','0:'+str(int(bool(flags.get('forced'))))]
    if start_offset:command+=['--sync','0:'+format(float(start_offset)*1000,'.9f')]
    command+=[str(video)]
    command+=['--video-tracks',','.join(map(str,video_ids))] if video_ids else ['--no-video']
    return command+[str(source)]


def nvidia_savings_preflight(args, duration=None):
    """Bounded sample must shrink before any full-file NVIDIA encode starts."""
    root = args.work_dir.resolve()/('nvidia-size-preflight-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    root.mkdir(parents=True,exist_ok=False)
    seconds=min(30.,duration) if duration and duration>0 else 30.
    whole_source=bool(duration and 0<duration<30)
    start = 0. if whole_source else min(300., max(0., duration/2-15)) if duration else 0.
    sample_args = argparse.Namespace(source=args.source, execute=True,
        overall_offset=0, overall_span=10,
        experimental_nvidia=not getattr(args,'experimental_intel',False), experimental_intel=getattr(args,'experimental_intel',False), seconds=seconds, start=start, whole_source=whole_source, work_dir=root,
        nvenc_cq=getattr(args,'nvenc_cq',None), measure_quality=True,
        nvenc_maxrate_mbps=getattr(args,'nvenc_maxrate_mbps',None),
        minimum_savings_percent=getattr(args,'min_savings',5.0),
        experimental_hdr10plus=getattr(args,'experimental_hdr10plus',False),
        ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, dovi_tool=args.dovi_tool)
    sample_args.source_guard=getattr(args,'source_guard',lambda:None)
    result = dv.run(sample_args)
    reports = list(root.glob('dv81-*/validation.json'))
    if result or len(reports) != 1:
        raise ValueError('Bounded hardware DV sample did not pass; full-file encode not started')
    sample = json.loads(reports[0].read_text(encoding='utf-8'))
    if not sample.get('status','').startswith('verified') or not sample.get('original_stat_unchanged'):
        raise ValueError('Sample preservation failed; full-file encode not started')
    decision = savings_decision(sample['original_video_bytes'],sample['output_video_bytes'],
                                getattr(args,'min_savings',5.0))
    if sample.get('quality',{}).get('candidate',{}).get('passed') is not True:
        decision.update(eligible=False,reason='Bounded DV sample did not meet the shared quality floor')
    sample['optimization_decision'] = dict(decision, basis='selected sample video payload; whole-file container savings checked separately')
    if not decision['eligible']:
        sample.update(structural_status=sample['status'],status='skipped',
                      error=decision['reason'],full_file_encode_started=False)
    reports[0].write_text(json.dumps(sample,indent=2),encoding='utf-8')
    return decision


def run(args, *, qualified_preflight=None):
    minimum = getattr(args, 'min_savings', 5.0)
    savings_decision(1, 1, minimum)  # Validate before reading or encoding media.
    info = mm.probe(args.source, args.ffprobe)
    dv.require_candidate(info)
    if not math.isfinite(info.duration_seconds) or not 0 < info.duration_seconds <= 86400:
        raise ValueError('Requires a known duration of at most 24 hours')
    nvidia = getattr(args, 'experimental_nvidia', False)
    intel = getattr(args, 'experimental_intel', False)
    experimental = nvidia or intel
    combined=getattr(args,'experimental_hdr10plus',False)
    if combined and (not nvidia or not shutil.which('hdr10plus_tool')):
        raise ValueError('Combined DV/HDR10+ full research requires NVIDIA and hdr10plus_tool')
    options = dv.sample_encoder_options(info, nvidia, intel, getattr(args,'nvenc_cq',None),
        getattr(args,'nvenc_maxrate_mbps',None)) if experimental else dv.experimental_encoder_options(info, args.qp_i, args.qp_p)
    if getattr(args,'nvenc_cq',None) is not None and not nvidia:
        raise ValueError('NVENC CQ requires explicit NVIDIA research')
    encoder = 'hevc_qsv' if intel else 'hevc_nvenc' if nvidia else 'hevc_amf'
    for tool in (args.ffmpeg, args.ffprobe, args.dovi_tool):
        if not shutil.which(tool):
            raise ValueError(f'Missing tool: {tool}; no automatic installation')
    print(f'FULL-FILE PLAN: {info.duration_seconds:.3f}s; {info.width}x{info.height}; {encoder}; Profile 8.1', flush=True)
    if not args.execute:
        print('DRY RUN: no encoding or output files created')
        return 0
    if encoder not in mm.ffmpeg_encoder_names(args.ffmpeg):
        raise ValueError(f'{encoder} missing; no CPU fallback')
    if intel and 'intel' not in mm.gpu_vendors():
        raise ValueError('Intel GPU not detected; no CPU fallback')
    if nvidia and 'nvidia' not in mm.gpu_vendors():
        raise ValueError('NVIDIA GPU not detected; no CPU fallback')
    if experimental:
        # The automatic workflow already compared multiple preserved scenes.
        # Reuse its verified, source/settings-bound decision rather than letting
        # an unrelated single scene veto it. Standalone callers still preflight.
        decision = (qualified_preflight(args) if qualified_preflight is not None
                    else nvidia_savings_preflight(args, info.duration_seconds))
        if not decision['eligible']:
            print(f"SKIPPED: {decision['reason']}. No full-file encode; original retained.",flush=True)
            return 0
    args.work_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.work_dir).free < 4 * info.size_bytes + 2 * 1024**3:
        raise ValueError('Insufficient reserve for retained compressed intermediates')
    directory = args.work_dir / ('dv-full-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(exist_ok=False)
    guard = (dv.NvidiaSampleGuard if experimental else RunGuard)(directory, reserve=2 * 1024**3)
    if experimental:guard.source_guard=getattr(args,'source_guard',lambda:None)
    guard.allow_hdr10plus=combined
    if experimental:
        guard.detail = 'Full-file DV preservation; integrated opt-in supports AMD/Intel Profile 8.1. Playback review follows automated checks.'
        guard.duration = info.duration_seconds
        guard.overall_offset, guard.overall_span = 10, 90
    before = args.source.stat()
    report = {'status': 'running', 'source': str(args.source), 'commands': [],
              'qp_i': args.qp_i, 'qp_p': args.qp_p, 'scope': 'full-file Profile 8.1 experimental',
              'quality_note': 'Metadata validation does not prove identical visual quality.'}
    if experimental:
        report.update(encoder_settings={'encoder': encoder, 'options': options},
                      scope=f'explicit {encoder} full-file Profile 8.1 experiment; normal AMD gate unchanged')
    terminal = sys.stdout
    with (directory / 'terminal.log').open('x', encoding='utf-8') as log:
        sys.stdout = Tee(terminal, log)
        try:
            print(f'RUN DIRECTORY: {directory.resolve()}', flush=True)
            def stage(command, phase, offset, span, timeout=14400, strict_decode=False):
                guard.phase = phase
                guard.status(offset)
                guard()
                report['commands'].append([str(c) for c in command])
                print(f'PHASE: {phase}', flush=True)
                started = time.monotonic()
                result = np.stage([str(c) for c in command], info.duration_seconds, offset, span,
                                  timeout=timeout, stall=0, guard=guard, strict_decode=strict_decode)
                report.setdefault('stage_seconds', {})[phase] = time.monotonic()-started
                return result
            ff = [args.ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n']
            progress = ['-progress', 'pipe:1', '-nostats']
            guard.phase = 'source inspection'
            guard.status(0)
            source_pts, source_bytes = video_packets(args.ffprobe, args.source)
            streams = {'streams': dv.stream_info(args.ffprobe, args.source)}
            stream = dv_tracks.primary(streams['streams'])
            from hdr10_trial import chroma_options
            options += chroma_options(stream)
            rate = stream['r_frame_rate']
            step = 1 / float(dv.Fraction(rate))
            variable=bool(source_pts) and any(abs(b-a-step)>.002 for a,b in zip(source_pts,source_pts[1:]))
            if not source_pts or (variable and not experimental):
                raise ValueError('DV timestamp reconstruction requires continuous constant-rate video')
            if not experimental and abs(source_pts[0]) > .002:
                raise ValueError('Nonzero DV start requires the ordered timestamp-preserving workflow')
            if experimental:
                audit = sys.modules[__name__]
                dv_tracks.primary(streams['streams'])
                guard.phase = 'Inspect every source frame for HDR and DV metadata'
                guard.status(0)
                source_frames = directory/'source-frames.compact'
                report['commands'].append(audit.frame_evidence(args.ffprobe, args.source, source_frames, guard))
                audit.validate_source_frames(source_frames, source_pts, guard)
            raw, rpu, encoded, injected, final = [directory / n for n in
                ('original.hevc', 'original-rpu.bin', 'encoded.hevc', 'injected.hevc', args.source.with_suffix('.mkv').name)]
            if getattr(args, 'video_only_folder', False):
                final = directory / 'media' / final.name
                final.parent.mkdir(exist_ok=False)
            stage(ff + ['-i', args.source, '-map', '0:V:0', '-c', 'copy', '-bsf:v', 'hevc_mp4toannexb', '-f', 'hevc', *progress, raw], 'extract source bitstream', 0, 8)
            stage([args.dovi_tool, 'extract-rpu', '-i', raw, '-o', rpu], 'extract full RPU', 8, 2)
            stage(ff + ['-xerror','-threads', '2', '-i', args.source, '-map', '0:V:0', *options,
                  '-profile:v', 'main10', '-fps_mode', 'passthrough', '-f', 'hevc', *progress, encoded], f'{encoder} full encode', 10, 55)
            if experimental and shutil.disk_usage(directory).free < 4*encoded.stat().st_size + 3*1024**3:
                raise ValueError('Insufficient room for injection, final mux and retained verification copy')
            injection_source=encoded
            if combined:
                metadata=directory/'original-hdr10plus.json'
                stage(['hdr10plus_tool','extract',raw,'-o',metadata],'extract full HDR10+',65,0)
                injection_source=directory/'encoded-hdr10plus.hevc'
                stage(['hdr10plus_tool','inject','-i',encoded,'-j',metadata,'-o',injection_source],
                      'inject full HDR10+',65,0)
            stage([args.dovi_tool, 'inject-rpu', '-i', injection_source, '--rpu-in', rpu, '-o', injected], 'inject full RPU', 65, 5)
            mux = mux_command(args.ffmpeg, args.source, injected, final, rate)
            if experimental:
                timestamped = directory/'timestamped-dv-video.mkv'
                timestamps=None
                if variable:
                    from hdr10plus_preserve import write_decoded_timestamps
                    timestamps=directory/'decoded-timestamps.txt'
                    write_decoded_timestamps(({'pts_time':f['best_effort_timestamp_time']}
                        for f in audit.frames(source_frames,combined)),timestamps,guard)
                stage(timestamped_video_command(args.ffmpeg, injected, timestamped, rate, intel=intel,
                                                timestamps=timestamps),
                      'materialize DV video timestamps', 70, 0)
                report['variable_timing_detected']=variable
                if shutil.which('mkvmerge'):
                    identified=np.checked_json(['mkvmerge','-J',str(args.source)],timeout=60)
                    mux=matroska_dv_mux_command(timestamped,args.source,final,streams,identified,
                                                start_offset=0 if variable else source_pts[0])
                else:
                    mux = ordered_dv_mux_command(args.ffmpeg, timestamped, args.source, final, streams,
                                                 start_offset=0 if variable else source_pts[0])
            stage(mux, 'copy all audio subtitles chapters', 70, 5)
            decision = savings_decision(info.size_bytes, final.stat().st_size, minimum,
                                       policy=getattr(args,'savings_policy',None))
            report['optimization_decision'] = decision
            if not decision['eligible']:
                report.update(status='skipped', error=decision['reason'],
                              output=str(final.resolve()), publication_allowed=False)
                print(f"SKIPPED: {decision['reason']}; output not accepted for publication.",flush=True)
                raise NoSavingsError(decision['reason'])
            guard.phase = 'validate streams and timestamps'
            guard.status(75)
            if experimental:
                seek_ok, seek_checks = verify_seek_interleaving(final, args.ffprobe,
                    [info.duration_seconds * fraction for fraction in (0, .1, .25, .5, .75, .9)])
                report['seek_interleaving'] = seek_checks
                if not seek_ok:
                    raise ValueError('Audio/video packet ordering failed seek-point validation')
            output_info = mm.probe(final, args.ffprobe)
            dv.require_candidate(output_info)
            if experimental:
                final_streams = {'streams': dv.stream_info(args.ffprobe, final)}
                if nv.stream_inventory(streams) != nv.stream_inventory(final_streams):
                    raise ValueError('Original stream inventory/dispositions changed')
                if stream.get('sample_aspect_ratio') != dv_tracks.primary(final_streams['streams']).get('sample_aspect_ratio'):
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
                if experimental:
                    rounded = audit.compare_track_packets(source_packets, final_packets, streams['streams'])
                    for index, count in rounded.items():
                        proof=decoded_track_proof(ff,args.source,final,index,directory,
                                                 lambda command,label:stage(command,label,75,0))
                        report.setdefault('aac_duration_rounding', {})[index] = dict(packets=count, decoded_pcm_identical=True, presentation=proof)
                elif source_packets != final_packets:
                    raise ValueError(f'Original {selector} packets changed')
            report['chapter_preservation'] = verify_chapters_preserved(args.ffprobe, args.source, final, 60)
            def first_frame(path):
                from decoder_context import metadata_reader_options
                return np.checked_json([args.ffprobe, '-v', 'error', *metadata_reader_options(), '-select_streams', 'V:0',
                    '-read_intervals', '%+#1', '-show_frames', '-of', 'json', str(path)])['frames']
            report['static_hdr_rounding_first_frame'] = dv.compare_static_hdr(first_frame(args.source), first_frame(final))
            check_raw, check_rpu = directory / 'final-check.hevc', directory / 'final-rpu.bin'
            stage(ff + ['-i', final, '-map', '0:V:0', '-c', 'copy', '-bsf:v', 'hevc_mp4toannexb', '-f', 'hevc', *progress, check_raw], 'extract final verification video', 75, 3)
            stage([args.dovi_tool, 'extract-rpu', '-i', check_raw, '-o', check_rpu], 'extract final verification RPU', 78, 2)
            digests = []
            for binary, name in ((rpu, 'original-rpu.json'), (check_rpu, 'final-rpu.json')):
                exported = directory / name
                stage([args.dovi_tool, 'export', '-i', binary, '-d', f'all={exported.resolve()}'], 'export metadata for bounded-memory comparison', 80, 0)
                digests.append(rpu_digest(exported, guard))
            if digests[0] != digests[1] or digests[0][0] != len(source_pts):
                raise ValueError('Full RPU content/count/frame order mismatch')
            if experimental:
                guard.phase = 'Compare every decoded output frame and static HDR value'
                guard.status(80)
                output_frames = directory/'output-frames.compact'
                report['commands'].append(audit.frame_evidence(args.ffprobe, final, output_frames, guard))
                report['decoded_frame_checks'] = audit.compare_frames(source_frames, output_frames, guard)
                if variable:report['variable_timing_preserved']=True
                report['verified_secondary_video_tracks']=dv_tracks.verify(
                    args.ffmpeg,args.ffprobe,args.source,final,directory,guard,frames=len(output_pts),
                    verified_variable_timing=variable)
                report['secondary_video_packets_unchanged']=True
            maps,reused=final_decode_maps(final_streams if experimental else streams,
                report.get('decoded_frame_checks',{}),len(output_pts))
            report['final_decode_evidence']=dict(video_audit_reused=reused,audio_maps=maps if reused else 'all',
                video='strict full-frame audit' if reused else 'final full decode')
            if maps:
                stage(ff + ['-v', 'error', '-xerror', '-threads', '2', '-i', final,
                            *[item for mapping in maps for item in ('-map',mapping)], '-f', 'null', '-', *progress],
                      'complete output audio decode' if reused else 'complete output decode', 80, 20, strict_decode=True)
            report.update(status='verified-full-file-awaiting-playback', output=str(final.resolve()), frames=len(source_pts),
                rpu_content_digest=digests[0][1], rpu_byte_identical=dv.sha256(rpu)==dv.sha256(check_rpu),
                audio_subtitle_packets_unchanged=True, chapters_unchanged=True,
                source_bytes=info.size_bytes, output_bytes=final.stat().st_size,
                video_savings_percent=100*(1-output_bytes/source_bytes), total_savings_percent=100*(1-final.stat().st_size/info.size_bytes))
            if report.get('aac_duration_rounding'):
                report['audio_subtitle_packets_unchanged'] = False
                report['packet_payloads_order_and_pts_unchanged'] = True
                report['audio_note'] = 'AAC duration fields are omitted or rounded by at most 1ms. Packet bytes and timestamps are exact; decoded PCM, sample count and presentation timing passed independently.'
            if not savings_decision(info.size_bytes,final.stat().st_size,minimum,
                                    policy=getattr(args,'savings_policy',None))['eligible']:
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
        or args.hardware not in ('auto', 'amd', 'intel') or args.hardware_fallback == 'cpu'
        or args.dolby_vision_policy != 'skip' or args.dolby_preview_backend != 'vulkan'
        or args.native_delivery_test or args.streaming_delivery_test or args.full_file_streaming
        or args.preview_range_explicit or args.report is not None or args.quality != 'balanced'
    )
    if conflicts:
        print('BLOCKED: preservation requires one file, original resolution, AMD/Intel/auto HEVC, '
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
        vendor = args.hardware
        if args.execute:
            vendors = mm.gpu_vendors()
            if vendor == 'auto':
                vendor = next((v for v in ('amd', 'intel') if v in vendors), None)
            if vendor not in vendors or vendor not in ('amd', 'intel'):
                print('BLOCKED: supported AMD/Intel GPU not detected; no CPU fallback.')
                return 3
        elif vendor == 'auto':
            vendor = next((v for v in ('amd', 'intel') if v in mm.gpu_vendors()), 'amd')
        print('Preservation: Profile 8.1 only; no scaling or tone mapping. '
              'All originals and intermediate files retained. Playback review remains required.')
        return run(argparse.Namespace(source=source, execute=args.execute, qp_i=args.dv_qp_i,
            qp_p=args.dv_qp_p, work_dir=args.output_dir or Path(__file__).resolve().parent.parent/'reports',
            ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, dovi_tool=args.dovi_tool,
            min_savings=args.min_savings, video_only_folder=getattr(args, 'video_only_folder', False),
            experimental_intel=vendor == 'intel'))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'BLOCKED: {exc}; original and any partial output retained')
        return 4


def verify_existing(parent, *, output=None, ffmpeg='ffmpeg', ffprobe='ffprobe',
                    dovi_tool=None, min_savings=5.0):
    full = sys.modules[__name__]
    audit = sys.modules[__name__]
    parent = parent.resolve(strict=True)
    previous = json.loads((parent/'validation.json').read_text(encoding='utf-8'))
    if previous.get('encoder_settings',{}).get('encoder') != 'hevc_nvenc' or not previous.get('original_stat_unchanged'):
        raise ValueError('Requires a retained NVIDIA run with unchanged-source evidence')
    source = Path(previous['source'])
    output = Path(output) if output is not None else parent/'episode-dolby-vision.mkv'
    if output.is_symlink() or not output.resolve(strict=True).is_relative_to(parent) or output.resolve()==source.resolve():
        raise ValueError('Retained verification requires an output inside its research run, never the source')
    dovi_tool=dovi_tool or str(Path(__file__).parent.parent/'tools/dovi_tool-2.3.3/dovi_tool.exe')
    for tool in (ffmpeg,ffprobe,dovi_tool):
        if not tool or not shutil.which(tool):raise ValueError(f'Missing verification tool: {tool}')
    directory = parent/('verification-'+time.strftime('%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir()
    guard = dv.NvidiaSampleGuard(directory, reserve=2*1024**3)
    initial = (source.stat().st_size, source.stat().st_mtime_ns)
    report = dict(status='running',source=str(source),output=str(output),parent_run=str(parent),commands=[],
                  min_savings=min_savings,publication_authorized=False,
                  scope='Full NVIDIA Profile 8.1 preservation verification; playback review separate')
    dovi = dovi_tool
    duration = 0.0
    ff = [ffmpeg,'-hide_banner','-nostdin','-n']
    def stage(command,label,percent,strict_decode=False):
        guard.phase=label; guard.status(percent); guard()
        report['commands'].append([str(c) for c in command])
        print(label,flush=True)
        return np.stage([str(c) for c in command],duration,timeout=3600,stall=0,guard=guard,strict_decode=strict_decode)
    try:
        decision=savings_decision(source.stat().st_size,output.stat().st_size,min_savings)
        report['optimization_decision']=decision
        if not decision['eligible']:
            report.update(status='skipped',error=decision['reason'],publication_allowed=False)
            print(f"SKIPPED: {decision['reason']}; no acceptance or publication.",flush=True)
            return 0
        guard.phase='Verify original tracks and timestamps'; guard.status(0)
        before, after = mm.probe(source,ffprobe), mm.probe(output,ffprobe)
        duration = before.duration_seconds
        guard.duration = duration
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
            report['decoded_pcm_checks'][index]=decoded_track_proof(ff,source,output,index,directory,
                                                                  lambda command,label:stage(command,label,15))
        report['chapter_preservation'] = verify_chapters_preserved(ffprobe,source,output,60)
        passed,detail=verify_startup_interleaving(output,ffprobe)
        if not passed: raise ValueError(detail)
        report['startup_interleaving']=detail
        passed,checks=verify_seek_interleaving(output,ffprobe,[duration*f for f in (0,.1,.25,.5,.75,.9)])
        report['seek_interleaving']=checks
        if not passed:raise ValueError('Audio/video packet ordering failed seek-point validation')
        fresh=directory/'current-source.hevc'
        stage(ff+['-v','error','-i',source,'-map','0:v:0','-c','copy','-bsf:v','hevc_mp4toannexb','-f','hevc',fresh],'Confirm current source bitstream matches audited frames',25)
        if dv.sha256(fresh)!=dv.sha256(parent/'original.hevc'): raise ValueError('Source bitstream changed since frame audit')
        source_frames=parent/'source-frames.compact'
        if not full.picture_evidence_complete(source_frames,guard):
            guard.phase='Refresh source frame geometry and color evidence'; guard.status(30)
            source_frames=directory/'source-frames.compact'
            report['commands'].append(full.frame_evidence(ffprobe,source,source_frames,guard))
            report['legacy_source_evidence_refreshed']=True
        audit.validate_source_frames(source_frames,source_pts,guard)
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
        report['decoded_frame_checks']=audit.compare_frames(source_frames,frames,guard)
        maps,reused=final_decode_maps(final_streams,report['decoded_frame_checks'],len(final_pts))
        report['final_decode_evidence']=dict(video_audit_reused=reused,audio_maps=maps if reused else 'all',
            video='strict full-frame audit' if reused else 'final full decode')
        if maps:
            stage(ff+['-v','error','-xerror','-threads','2','-i',output,
                  *[item for mapping in maps for item in ('-map',mapping)],'-f','null','-','-progress','pipe:1','-nostats'],
                  'Full output audio decode' if reused else 'Full output video/audio decode',80,strict_decode=True)
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
    parser.add_argument('--verify-output', type=Path, help='Explicit retained output inside --verify-existing run')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--video-only-folder', action='store_true', help='Place accepted video alone in the run media folder; omit artwork and external subtitles, retain embedded tracks and sources')
    hardware = parser.add_mutually_exclusive_group()
    hardware.add_argument('--experimental-intel', action='store_true', help='Explicit Intel Profile 8.1 full-file research; bounded preflight and all preservation checks required')
    hardware.add_argument('--experimental-nvidia', action='store_true', help='Explicit NVIDIA research run; integrated opt-in supports AMD/Intel')
    parser.add_argument('--min-savings', type=float, default=5.0, help='Minimum percentage reduction; larger/equal outputs are always rejected')
    parser.add_argument('--nvenc-cq',type=int,choices=range(18,33),help='Explicit NVIDIA research CQ; the same setting is used for preflight and full encoding')
    parser.add_argument('--experimental-hdr10plus',action='store_true',help='Explicit combined DV Profile 8.1/HDR10+ full research; production guard unchanged')
    parser.add_argument('--qp-i',type=int,default=21)
    parser.add_argument('--qp-p',type=int,default=23)
    parser.add_argument('--work-dir',type=Path,default=Path('reports'))
    parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--dovi-tool',default=str(Path(__file__).parent.parent/'tools/dovi_tool-2.3.3/dovi_tool.exe'))
    args = parser.parse_args()
    if args.verify_existing:
        if args.source or args.execute:
            parser.error('--verify-existing cannot be combined with source/execute')
        return verify_existing(args.verify_existing,output=args.verify_output,ffmpeg=args.ffmpeg,
                               ffprobe=args.ffprobe,dovi_tool=args.dovi_tool,min_savings=args.min_savings)
    if args.verify_output:parser.error('--verify-output requires --verify-existing')
    if args.source is None:
        parser.error('source is required unless --verify-existing is used')
    return run(args)


if __name__ == '__main__':
    from job_tracking import tracked_call
    raise SystemExit(tracked_call(main, 'Full Dolby Vision preservation'))
