"""Measured HEVC/AV1 selection and optional full safe-copy encoding (SDR only)."""
import argparse
import hashlib
import itertools
import json
import math
import shutil
import subprocess
import time
import uuid
from fractions import Fraction
from dataclasses import replace
from pathlib import Path

import muxmender as mm
from amd_av1_batch import disjoint, fingerprint
from task_progress import digest, run_probe
from codec_selection import select_candidate, impossible_size_bound
from dvd_av1_batch import save
from encoder_capabilities import probe_encoder
from job_tracking import tracked_call, progress
from native_pipeline import stage
import legacy_color
from media_metadata import canonical_tags, canonical_chapters
from packet_validation import collect_packets


def sample_positions(duration, seconds):
    if not math.isfinite(duration) or not 1 <= seconds <= 60 or duration < seconds * 6:
        raise ValueError('Need finite duration of at least six sample lengths; samples must be 1-60 seconds')
    return [round((duration-seconds)*fraction, 3) for fraction in (.15, .5, .85)]


def eligibility(data):
    videos = [s for s in data['streams'] if s['codec_type'] == 'video']
    if len(videos) != 1:
        raise ValueError('Requires exactly one video track')
    v = videos[0]
    if v.get('pix_fmt') != 'yuv420p' or v.get('field_order') != 'progressive':
        raise ValueError('Only progressive 8-bit 4:2:0 SDR is supported by measured auto mode')
    if not legacy_color.is_supported(v):
        raise ValueError('Missing or unsupported color metadata; inspect legacy SDR before selecting a test assumption')
    if v.get('color_range') not in ('tv', 'pc') or v.get('sample_aspect_ratio') in (None, 'N/A', '0:1'):
        raise ValueError('Color range and aspect ratio must be known')
    if any(s.get('side_data_type') != 'CPB properties' for s in v.get('side_data_list', [])):
        raise ValueError('Video side data (including Dolby Vision/rotation) requires specialized review')
    if any(s['codec_type'] not in ('video', 'audio', 'subtitle', 'attachment') for s in data['streams']):
        raise ValueError('Unsupported track type')
    if int(v['width']) <= 0 or int(v['height']) <= 0:
        raise ValueError('Invalid dimensions')
    return v


def quality_summary(data, expected_frames, mean_floor, p5_floor):
    values = [float(f['metrics']['vmaf']) for f in data.get('frames', [])]
    if len(values) != expected_frames or not values or any(not math.isfinite(x) for x in values):
        raise ValueError('Incomplete/invalid VMAF frame evidence')
    mean = sum(values)/len(values)
    p5 = sorted(values)[max(0, math.ceil(.05*len(values))-1)]
    return dict(mean=mean, p5=p5, frames=len(values),
                passed=mean >= mean_floor and p5 >= p5_floor,
                caveat='Objective SDR screening only, not proof of perceptual transparency')


def quality_graph(name, frame_rate):
    """Pair frame ordinals only AFTER count/geometry/timing validation.

    Millisecond container rounding can otherwise make framesync pick the previous
    reference frame. This clock exists only in the metric filter, never in output.
    """
    rate = Fraction(frame_rate)
    if rate <= 0 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.' for c in name):
        raise ValueError('Invalid quality graph parameters')
    clock = f'settb=AVTB,setpts=N*{rate.denominator}/({rate.numerator}*TB)'
    return f'[0:v:0]{clock}[d];[1:v:0]{clock}[r];[d][r]libvmaf=n_threads=2:log_fmt=json:log_path={name}'


def metadata_check(before, after, codec):
    old, new = before['streams'], after['streams']
    if len(old) != len(new):
        raise ValueError('Track count changed')
    for a, b in zip(old, new):
        keys = ['codec_type', 'disposition']
        if a['codec_type'] == 'video':
            keys += ['width', 'height', 'pix_fmt', 'sample_aspect_ratio', 'avg_frame_rate',
                     'color_range', 'color_space', 'color_transfer', 'color_primaries']
            if b['codec_name'] != codec:
                raise ValueError('Unexpected video codec')
        else:
            keys += ['codec_name', 'sample_rate', 'channels', 'channel_layout', 'extradata_hash']
        if any(a.get(k) != b.get(k) for k in keys):
            raise ValueError('Stream properties changed: '+str(a['index']))
        old_tags=canonical_tags(a.get('tags', {}), f"source stream {a['index']}")
        new_tags=canonical_tags(b.get('tags', {}), f"output stream {b['index']}")
        for tag in ('language', 'title', 'filename', 'mimetype'):
            if old_tags.get(tag) != new_tags.get(tag):
                raise ValueError(f"Stream {a['index']} ({a['codec_type']}) tag changed: {tag}: {old_tags.get(tag)!r} -> {new_tags.get(tag)!r}")
    if canonical_chapters(before.get('chapters', [])) != canonical_chapters(after.get('chapters', [])):
        raise ValueError('Chapters changed')
    durations=[float(item['format']['duration']) for item in (before,after)]
    if any(not math.isfinite(value) or value<=0 for value in durations):
        raise ValueError('Invalid duration; finite positive evidence required')
    if abs(durations[0]-durations[1]) > .1:
        raise ValueError('Duration changed')


def encode_command(ffmpeg, source, output, settings, info, streams):
    options = mm.encoder_options(settings['codec'], settings['quality'], info, settings['encoder'])
    if 'nvenc_cq' in settings:
        if settings['encoder'] not in ('hevc_nvenc', 'av1_nvenc') or settings['nvenc_cq'] not in (21, 22, 23, 24, 25):
            raise ValueError('Measured NVENC CQ must be 21-25')
        options = list(options)
        options[options.index('-cq') + 1] = str(settings['nvenc_cq'])
    if 'nvenc_preset' in settings:
        if not settings['encoder'].endswith('_nvenc') or settings['nvenc_preset'] != 'p7':
            raise ValueError('Adaptive preset must be NVENC p7')
        options = list(options)
        options[options.index('-preset') + 1] = settings['nvenc_preset']
    command = [ffmpeg, '-hide_banner', '-nostdin', '-n', '-copyts', '-i', str(source),
               '-map', '0', '-map_metadata', '0', '-map_chapters', '0', '-c', 'copy',
               *options, '-pix_fmt', 'yuv420p', '-fps_mode:v', 'passthrough',
               '-avoid_negative_ts', 'disabled']
    # Explicit flags avoid muxer auto-selection of default tracks.
    for i, stream in enumerate(streams):
        flags = '+'.join(k for k, value in stream.get('disposition', {}).items() if value) or '0'
        command += [f'-disposition:{i}', flags]
    return command + ['-progress', 'pipe:1', '-nostats', str(output)]


class Workflow:
    def __init__(self, args, directory, guard):
        self.args, self.directory, self.guard = args, directory, guard
        self.serial = 0
        self.packet_reference_cache = {}

    def execute(self, command, label, duration):
        self.guard()
        progress(label, directory=self.directory)
        self.serial += 1
        with (self.directory/f'{self.serial:03d}-{label}.log').open('x', encoding='utf-8') as log:
            log.write(json.dumps(command)+'\n')
            def observe(line):
                log.write(line)
                return False
            return stage(command, duration, 0, 100, timeout=self.args.timeout, stall=120,
                         guard=self.guard, observe=observe, cwd=self.directory)

    def probe(self, source):
        progress('Reading media metadata: '+source.name, directory=self.directory)
        raw = subprocess.check_output([self.args.ffprobe, '-v', 'error', '-show_streams',
               '-show_chapters', '-show_format', '-show_data_hash', 'sha256', '-of', 'json', str(source)],
               text=True, timeout=60)
        data=json.loads(raw)
        resolved=getattr(self.args,'resolved_color',None)
        if resolved and (source==self.args.source or source.name.startswith('reference-')):
            video=next(s for s in data['streams'] if s['codec_type']=='video')
            for key,value in resolved.items():
                if video.get(key) in legacy_color.UNKNOWN:video[key]=value
                elif video[key]!=value:raise ValueError('Reference color metadata changed: '+key)
        return data

    def frame_file(self, source, label, metadata=None):
        metadata=metadata if metadata is not None else self.probe(source)['format']
        path = self.directory/(label+'-frames.jsonl')
        # Bound CPU contention between queue workers. Do not drop side-data or
        # frames: identical validation fields and full EOF draining are retained.
        run_probe([self.args.ffprobe, '-v', 'error', '-threads', '2', '-select_streams', 'v:0', '-show_frames',
                '-show_entries', 'frame=best_effort_timestamp_time,width,height,pix_fmt,sample_aspect_ratio,interlaced_frame,repeat_pict,color_primaries,color_transfer,color_space,color_range',
                '-of', 'compact=p=0', str(source)],path,'Checking frame timing: '+label,
                self.args.timeout,self.guard,float(metadata['duration']),float(metadata.get('start_time',0)))
        return path

    def packet_file(self, source, label, index):
        path = self.directory/(label+f'-stream-{index}.txt')
        run_probe([self.args.ffprobe, '-v', 'error', '-select_streams', str(index),
                '-show_packets', '-show_data_hash', 'sha256', '-show_entries',
                'packet=pts_time,dts_time,duration_time,data_hash', '-of', 'compact=p=0', str(source)],
                path,'Checking copied track: '+label+f' · track {index}',self.args.timeout,self.guard)
        return path

    def copied_packets(self, source, label, indices, metadata, reuse_sample=False):
        # Only generated clips in this workflow can be reused. Verify content,
        # including cached evidence, on every reuse; no persistent/stat-only cache.
        cacheable=(reuse_sample and source.resolve().parent==self.directory.resolve()
                   and source.name.startswith('reference-') and source.suffix=='.mkv')
        key=(str(source.resolve()),tuple(indices),digest(source,self.guard)) if cacheable and indices else None
        cached=self.packet_reference_cache.get(key) if key else None
        if cached and all(path.is_file() and not path.is_symlink() and digest(path,self.guard)==hash_value
                          for path,hash_value in cached.values()):
            progress('Reusing verified sample track evidence',detail='Generated reference and cached evidence hashes match')
            return {index:item[0] for index,item in cached.items()}
        result=collect_packets(self.args.ffprobe,source,self.directory,label,indices,self.args.timeout,self.guard,
                               float(metadata['duration']),float(metadata.get('start_time',0)))
        if key:self.packet_reference_cache[key]={index:(path,digest(path,self.guard)) for index,path in result.items()}
        return result

    def validate(self, reference, output, before, codec, label, reference_frames):
        actual = self.probe(output)
        metadata_check(before, actual, codec)
        frames = self.frame_file(output, label, actual['format'])
        count = compare_frames(reference_frames, frames)
        indices=[s['index'] for s in before['streams'] if s['codec_type'] in ('audio','subtitle')]
        original=self.copied_packets(reference,label+'-reference',indices,before['format'],reuse_sample=True)
        encoded=self.copied_packets(output,label,indices,actual['format'])
        for index in indices:compare_packets(original[index],encoded[index])
        self.execute([self.args.ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-xerror',
                      '-i', str(output), '-map', '0:v:0', '-map', '0:a?', '-progress', 'pipe:1',
                      '-nostats', '-f', 'null', '-'], label+'-decode', float(before['format']['duration']))
        return count

    def quality(self, reference, output, label, count, duration):
        # Safe generated basename and cwd avoid platform/path escaping in filter syntax.
        name = label+'-vmaf.json'
        video = next(s for s in self.probe(reference)['streams'] if s['codec_type'] == 'video')
        graph = quality_graph(name, video['avg_frame_rate'])
        self.execute([self.args.ffmpeg, '-hide_banner', '-nostdin', '-v', 'warning',
                      '-i', str(output), '-i', str(reference), '-filter_complex', graph,
                      '-an', '-sn', '-progress', 'pipe:1', '-nostats', '-f', 'null', '-'],
                     label+'-quality', duration)
        result = quality_summary(json.loads((self.directory/name).read_text()), count,
                                 self.args.vmaf_mean, self.args.vmaf_p5)
        result['alignment'] = 'verified-frame-ordinal-v1'
        return result


def compact_rows(path, required):
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            row = dict(item.split('=', 1) for item in line.strip().split('|') if '=' in item)
            if required == 'width' and any(word in line.lower() for word in ('dolby', 'dovi', 'mastering display', 'content light', 'hdr dynamic', 'display matrix')):
                raise ValueError('Unexpected HDR/geometry frame side data')
            if required == 'data_hash' and row and 'data_hash' not in row:
                raise ValueError('Missing packet hash evidence')
            if required in row:
                yield row


def compare_frames(reference, output):
    progress('Comparing frame geometry and timestamps',detail='Comparing collected frame evidence; percentage unavailable')
    count = 0
    fields = ('width', 'height', 'pix_fmt', 'sample_aspect_ratio')
    for a, b in itertools.zip_longest(compact_rows(reference, 'width'), compact_rows(output, 'width')):
        if a is None or b is None:
            raise ValueError('Decoded frame count changed')
        if any(a.get(k) != b.get(k) for k in fields):
            raise ValueError('Decoded frame geometry/pixel format changed')
        for key in legacy_color.FIELDS:
            if a.get(key) not in legacy_color.UNKNOWN and b.get(key) not in legacy_color.UNKNOWN and a[key]!=b[key]:
                raise ValueError('Decoded frame color metadata changed: '+key)
        for frame in (a, b):
            if frame.get('color_transfer') in ('smpte2084','arib-std-b67'):
                raise ValueError('HDR transfer found during SDR frame validation')
            if frame.get('interlaced_frame') != '0' or frame.get('repeat_pict') != '0':
                raise ValueError('Non-progressive/repeated frames require separate review')
            if 'side_data_type' in frame and any(x in frame['side_data_type'].lower() for x in ('dovi', 'dolby', 'mastering', 'content light', 'hdr', 'display matrix')):
                raise ValueError('Unexpected HDR/geometry frame side data')
        timestamps = [float(f['best_effort_timestamp_time']) for f in (a, b)]
        if not all(math.isfinite(t) for t in timestamps) or abs(timestamps[0]-timestamps[1]) > .002:
            raise ValueError('Decoded frame timing changed')
        count += 1
    if not count:
        raise ValueError('No decoded frames')
    return count


def compare_packets(reference, output):
    progress('Comparing copied track evidence',detail='Checking packet hashes and timestamps; percentage unavailable')
    for a, b in itertools.zip_longest(compact_rows(reference, 'data_hash'), compact_rows(output, 'data_hash')):
        if a is None or b is None or a['data_hash'] != b['data_hash']:
            raise ValueError('Copied packet payload/count changed')
        for key in ('pts_time', 'dts_time', 'duration_time'):
            left, right = a.get(key), b.get(key)
            if any(value not in (None,'N/A') and not math.isfinite(float(value)) for value in (left,right)):
                raise ValueError('Invalid copied packet timestamp: '+key)
            if left != right and (left in (None, 'N/A') or right in (None, 'N/A') or abs(float(left)-float(right)) > .002):
                raise ValueError('Copied packet timing changed')


def adaptive_candidates(report, limit=8):
    """Only refine runtime-tested NVIDIA encoders; never infer support or relax gates."""
    encoders = {}
    for trial in report['trials']:
        if trial.get('runtime_supported') is True and trial.get('playback_compatible') is True and trial.get('encoder') in ('hevc_nvenc','av1_nvenc'):
            encoders[trial['encoder']] = trial['codec']
    # Prefer the codec whose weakest scene scored best in the baseline trials.
    def score(encoder):
        values = [min((s.get('quality',{}).get('p5',0) for s in t['samples']),default=0)
                  for t in report['trials'] if t['encoder']==encoder]
        return max(values,default=0)
    candidates=[]
    for encoder in sorted(encoders,key=lambda e:(-score(e),e)):
        for cq in (23,22,24,25):
            candidates.append(dict(codec=encoders[encoder],encoder=encoder,quality='balanced',
                                   nvenc_cq=cq,nvenc_preset='p7'))
    return candidates[:limit]


def hardest_reference(report, encoder):
    scores={}
    for trial in report['trials']:
        if trial['encoder'] != encoder:continue
        for sample in trial['samples']:
            value=sample.get('quality',{}).get('p5')
            if value is not None:
                key=int(sample['reference_id'])
                scores[key]=min(scores.get(key,value),value)
    return min(scores,key=scores.get) if scores else 0


def run(args):
    source, root = disjoint(args.source, args.output_dir)
    if not source.is_file():
        raise ValueError('Measured auto mode processes one video at a time')
    args.ffmpeg = shutil.which(args.ffmpeg) or args.ffmpeg
    args.ffprobe = shutil.which(args.ffprobe) or args.ffprobe
    baseline = fingerprint(source)
    data = Workflow(args, root, lambda: None).probe(source)
    color_report=None
    try:
        videos=[s for s in data['streams'] if s['codec_type']=='video']
        if len(videos)==1 and any(videos[0].get(k) in legacy_color.UNKNOWN for k in legacy_color.FIELDS):
            progress('Inspecting legacy color metadata',detail='Reading declared color properties from decoded frames; no source changes')
            frames=legacy_color.inspect_frames(args.ffprobe,source,float(data['format']['duration']))
            data,color_report=legacy_color.resolve(data,frames,getattr(args,'legacy_color','inspect'))
            if color_report['missing']:
                raise ValueError('Missing color metadata after frame inspection: '+', '.join(color_report['missing'])+'. Original retained; an explicit sample-only color assumption is available.')
            if color_report['assumed'] and args.encode_best:
                raise ValueError('Assumed color is sample-only; full conversion/replacement requires confirmed color handling')
            args.resolved_color=color_report['effective']
        video = eligibility(data)
    except ValueError as exc:
        # Structured, expected rejection rather than a worker crash. Never encode.
        root.mkdir(parents=True, exist_ok=True)
        save(root/'eligibility.json', dict(state='unsupported', reason=str(exc), source=str(source),color_inspection=color_report))
        print('Original kept: unsupported input. '+str(exc))
        return 0
    duration = float(data['format']['duration'])
    positions = sample_positions(duration, args.seconds)
    plan = dict(source=str(source), positions=positions, seconds=args.seconds, hardware=args.hardware,
                qualities=args.qualities, hevc_nvenc_cq=getattr(args, 'hevc_nvenc_cq', None),
                playback_verified_codecs=args.playback_verified_codecs,
                minimum_savings_percent=args.minimum_savings_percent, full_copy=args.encode_best,
                source_deletion=False, metric='VMAF', mean_floor=args.vmaf_mean, p5_floor=args.vmaf_p5,
                adaptive=getattr(args,'adaptive',False), max_extra_trials=getattr(args,'max_extra_trials',8),color_inspection=color_report)
    if not args.execute:
        print(json.dumps(dict(dry_run=True, plan=plan), indent=2))
        return 0
    if not args.playback_verified_codecs:
        raise ValueError('Explicit --playback-verified-codecs required for your target players')
    root.mkdir(parents=True, exist_ok=True)
    directory = root/('auto-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir()
    required_space = max(args.min_free_gib*1024**3, baseline['size']*1.2 if args.encode_best else 0)
    if shutil.disk_usage(directory).free < required_space:
        raise RuntimeError('Insufficient free output space; source retained')
    def guard():
        if (directory/'STOP').exists():
            raise KeyboardInterrupt('STOP requested')
        if fingerprint(source) != baseline:
            raise RuntimeError('Source changed during work')
        if shutil.disk_usage(directory).free < args.min_free_gib*1024**3:
            raise RuntimeError('Output free space below safety reserve')
    workflow = Workflow(args, directory, guard)
    save(directory/'plan.json', plan)
    state = dict(state='running', source=str(source), original_retained=True)
    save(directory/'status.json', state)
    try:
        guard()
        source_hash = digest(source, guard)
        progress('Checking available encoders and quality tools',directory=directory)
        report = dict(schema='muxmender-codec-trials-v1', source_id=source_hash, color_mode='sdr', references=[], trials=[])
        filters = subprocess.check_output([args.ffmpeg, '-hide_banner', '-filters'], text=True, stderr=subprocess.STDOUT, timeout=30)
        if 'libvmaf' not in filters:
            raise RuntimeError('FFmpeg libvmaf is required; no unmeasured automatic selection')
        names = mm.ffmpeg_encoder_names(args.ffmpeg)
        vendors = mm.gpu_vendors() if args.hardware == 'auto' else [args.hardware]
        # Container lspci may be absent. Runtime probe remains the authority.
        if args.hardware == 'auto' and not vendors and shutil.which('nvidia-smi'):
            vendors = ['nvidia']
        candidates = []
        for vendor in vendors:
            for codec in ('hevc', 'av1'):
                intermediate = getattr(args, 'hevc_nvenc_cq', None)
                if intermediate and (vendor != 'nvidia' or codec != 'hevc'):
                    continue
                encoder = mm.HARDWARE_ENCODERS[vendor][codec]
                if encoder not in names or codec not in args.playback_verified_codecs:
                    continue
                runtime = probe_encoder(args.ffmpeg, encoder, video['width'], video['height'])
                save(directory/(encoder+'-runtime.json'), runtime)
                if runtime['status'] == 'working':
                    if intermediate:
                        candidates.extend(dict(codec=codec, encoder=encoder, quality='balanced', nvenc_cq=q)
                                          for q in intermediate)
                    else:
                        candidates.extend(dict(codec=codec, encoder=encoder, quality=q) for q in args.qualities)
        if not candidates:
            raise RuntimeError('No runtime-verified GPU encoder for the allowed codecs; no automatic CPU fallback')
        references = []
        for i, position in enumerate(positions):
            reference = directory/f'reference-{i}.mkv'
            workflow.execute([args.ffmpeg, '-hide_banner', '-nostdin', '-n', '-ss', str(position),
                '-i', str(source), '-t', str(args.seconds), '-map', '0', '-c', 'copy', '-map_chapters', '-1',
                '-avoid_negative_ts', 'make_zero', '-progress', 'pipe:1', '-nostats', str(reference)], 'reference-'+str(i), args.seconds)
            probe = workflow.probe(reference)
            frames = workflow.frame_file(reference, 'reference-'+str(i), probe['format'])
            count = compare_frames(frames, frames)
            # Do not accept pathological keyframe preroll spanning another sample.
            if float(probe['format']['duration']) > args.seconds*2:
                raise ValueError('Reference clip exceeds bounded sampling window')
            references.append((reference, probe, frames, count))
            report['references'].append(dict(id=str(i), bytes=reference.stat().st_size, position=position))
            # Defer expensive VMAF until a candidate can actually save space.
        info = mm.probe(source, args.ffprobe)
        if getattr(args,'resolved_color',None):info=replace(info,**args.resolved_color)
        def trial_candidate(settings, adaptive=False):
            trial_id = settings['encoder']+'-'+settings['quality']
            if 'nvenc_cq' in settings:
                trial_id += '-cq'+str(settings['nvenc_cq'])
            if 'nvenc_preset' in settings:
                trial_id += '-'+settings['nvenc_preset']
            first=hardest_reference(report,settings['encoder']) if adaptive else 0
            trial = dict(id=trial_id, source_id=source_hash, codec=settings['codec'], encoder=settings['encoder'],
                         settings=settings, runtime_supported=True, playback_compatible=True, samples=[])
            report['trials'].append(trial)
            order=[first]+[i for i in range(len(references)) if i!=first]
            for i in order:
                reference, probe, frames, count = references[i]
                label = trial_id+'-'+str(i)
                output = directory/(label+'.mkv')
                sample = dict(reference_id=str(i), bytes=0, quality_pass=False, preservation_pass=False,
                              decode_pass=False, quality_method='VMAF mean and fifth percentile')
                trial['samples'].append(sample)
                try:
                    started = time.monotonic()
                    workflow.execute(encode_command(args.ffmpeg, reference, output, settings, info, probe['streams']), label, float(probe['format']['duration']))
                    sample.update(bytes=output.stat().st_size, encode_completed=True,
                                  encode_seconds=time.monotonic()-started)
                except (ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                    guard()  # Changed source/low disk aborts the run, not just this candidate.
                    sample['error'] = str(exc)
                save(directory/'trials.json', report)
                if sample.get('error'):
                    trial['screened_out']='Encoding failed; evaluation incomplete'
                    save(directory/'trials.json',report)
                    return
                bound=impossible_size_bound(report['references'],trial['samples'],args.minimum_savings_percent)
                if bound and len(trial['samples'])<len(references):
                    trial['size_screen']=dict(rejected=True,early_bound=True,minimum=args.minimum_savings_percent,**bound)
                    trial['screened_out']='Encoded clips already exceed total sample size budget; remaining encodes skipped'
                    progress('Skipping candidate: sample size budget exceeded',directory=directory,
                             detail=f"{len(trial['samples'])} of {len(references)} clips already exceed the whole candidate budget. Quality not evaluated.")
                    save(directory/'trials.json',report)
                    return
            # Rejection only: size alone can never approve an output. All three
            # identical sample windows must be encoded before comparing totals.
            reference_bytes=sum(r['bytes'] for r in report['references'])
            savings=100*(1-sum(s['bytes'] for s in trial['samples'])/reference_bytes)
            trial['size_screen'] = dict(savings_percent=savings, minimum=args.minimum_savings_percent)
            if savings < args.minimum_savings_percent:
                trial['size_screen']['rejected']=True
                trial['screened_out']='Insufficient sample savings; quality not evaluated'
                progress('Keeping original size: candidate cannot save enough space',directory=directory,
                         detail=f'{savings:.1f}% sample reduction; {args.minimum_savings_percent:g}% required. Skipping costly quality checks.')
                save(directory/'trials.json',report)
                return
            for sample in trial['samples']:
                i=int(sample['reference_id'])
                reference, probe, frames, count=references[i]
                label=trial_id+'-'+str(i)
                output=directory/(label+'.mkv')
                ref_report=report['references'][i]
                if 'metric_self_check' not in ref_report:
                    calibration=workflow.quality(reference,reference,'self-'+str(i),count,float(probe['format']['duration']))
                    # Identical videos need not score 100 (or even 98). Do not
                    # normalize scores or loosen the user's conversion floors.
                    if calibration['mean'] < args.vmaf_mean or calibration['p5'] < args.vmaf_p5:
                        raise RuntimeError('Reference quality baseline is below configured thresholds; evaluation inconclusive, source retained')
                    ref_report['metric_self_check']=calibration
                try:
                    workflow.validate(reference,output,probe,settings['codec'],label,frames)
                    quality=workflow.quality(reference,output,label,count,float(probe['format']['duration']))
                    sample.update(preservation_pass=True,decode_pass=True,quality_pass=quality['passed'],quality=quality)
                except (ValueError,RuntimeError,subprocess.SubprocessError) as exc:
                    guard()
                    sample['error']=str(exc)
                save(directory/'trials.json',report)
                if not all(sample[k] for k in ('quality_pass','preservation_pass','decode_pass')):
                    trial['screened_out']='Scene '+str(i)+' failed; remaining quality checks skipped'
                    save(directory/'trials.json',report)
                    return
        for index, settings in enumerate(candidates):
            trial_candidate(settings)
            progress('Candidate completed', index+1, len(candidates), directory=directory, unit='candidates')
        decision = select_candidate(report, args.minimum_savings_percent)
        if getattr(args,'adaptive',False) and decision['action']=='keep_original':
            extra=adaptive_candidates(report,args.max_extra_trials)
            tested=0
            for settings in extra:
                guard()
                trial_candidate(settings,adaptive=True)
                tested+=1
                progress('Adaptive candidate checked',tested,len(extra),directory=directory,unit='candidates')
                decision=select_candidate(report,args.minimum_savings_percent)
                if decision['action']=='encode_copy':break
            save(directory/'adaptive-search.json',dict(extra_trials=tested,budget=len(extra),
                result=decision['action'],stop_reason='eligible_candidate' if decision['action']=='encode_copy' else 'bounded_search_exhausted',
                cpu_fallback='not_run_requires_explicit_opt_in',quality_thresholds_unchanged=True))
        save(directory/'selection.json', decision)
        if args.encode_best and decision['action'] == 'encode_copy':
            settings = decision['selected']['settings']
            output = directory/('full-'+settings['codec']+'.mkv')
            workflow.execute(encode_command(args.ffmpeg, source, output, settings, info, data['streams']), 'full-encode', duration)
            frames = workflow.frame_file(source, 'full-source', data['format'])
            workflow.validate(source, output, data, settings['codec'], 'full', frames)
            actual_savings = 100*(1-output.stat().st_size/baseline['size'])
            guard()
            if digest(source, guard) != source_hash:
                raise RuntimeError('Source hash changed; output not approved')
            if actual_savings < args.minimum_savings_percent:
                state.update(state='full-output-rejected-insufficient-savings', candidate=str(output), saved_percent=actual_savings)
            else:
                state.update(state='validated-copy-awaiting-playback', output=str(output), saved_percent=actual_savings,
                             source_sha256=source_hash, output_sha256=digest(output, guard))
        else:
            guard()
            if digest(source, guard) != source_hash:
                raise RuntimeError('Source hash changed')
            state.update(state='trials-completed', decision=decision)
        save(directory/'status.json', state)
        print(json.dumps(state, indent=2))
        return 0
    except BaseException as exc:
        state.update(state='stopped-original-retained', error=str(exc))
        save(directory/'status.json', state)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--hardware', choices=('auto', 'nvidia', 'amd', 'intel'), default='auto')
    parser.add_argument('--execute', action='store_true', help='Run trials; default only probes and prints plan')
    parser.add_argument('--encode-best', action='store_true', help='After trials, encode and validate a full copy')
    parser.add_argument('--legacy-color',choices=('inspect','bt709-limited'),default='inspect',
                        help='Inspect missing color tags; optional BT.709 limited-range assumption is sample-only')
    parser.add_argument('--playback-verified-codecs', nargs='+', choices=('hevc', 'av1'), default=[])
    parser.add_argument('--qualities', nargs='+', choices=('transparent', 'balanced', 'compact'), default=['balanced', 'compact'])
    parser.add_argument('--hevc-nvenc-cq', nargs='+', type=int, choices=(22, 23, 24),
                        help='HEVC-only intermediate trials using balanced preset and explicit CQ values')
    parser.add_argument('--adaptive', action='store_true', help='If baseline fails, refine runtime-tested NVENC settings using hardest-scene screening')
    parser.add_argument('--max-extra-trials', type=int, choices=range(1,13), default=8)
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--vmaf-mean', type=float, default=95)
    parser.add_argument('--vmaf-p5', type=float, default=90)
    parser.add_argument('--minimum-savings-percent', type=float, default=10)
    parser.add_argument('--min-free-gib', type=float, default=4)
    parser.add_argument('--timeout', type=float, default=7200)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args(argv)
    for name, low, high in [('vmaf_mean', 0, 100), ('vmaf_p5', 0, 100), ('minimum_savings_percent', 0, 99.9),
                            ('min_free_gib', 1, 100000), ('timeout', 1, 86400), ('seconds', 1, 60)]:
        value = getattr(args, name)
        if not math.isfinite(value) or not low <= value <= high:
            parser.error('Invalid '+name)
    args.qualities = list(dict.fromkeys(args.qualities))
    if args.hevc_nvenc_cq:
        args.hevc_nvenc_cq = list(dict.fromkeys(args.hevc_nvenc_cq))
        if args.hardware not in ('auto', 'nvidia') or 'hevc' not in args.playback_verified_codecs:
            parser.error('Intermediate CQ trials require NVIDIA and HEVC playback verification')
    # Validate separation BEFORE tracked_call creates dashboard artifacts.
    args.source, args.output_dir = disjoint(args.source, args.output_dir)
    return tracked_call(lambda: run(args), 'Measured codec selection', folder=args.output_dir) if args.execute else run(args)


if __name__ == '__main__':
    raise SystemExit(main())
