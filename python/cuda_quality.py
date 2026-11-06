"""Job-local CUDA scorer selection, with canonical CPU qualification and fallback.

Only scoring moves to the GPU. Decoding, rendering, frame alignment and all
publication checks stay with the shared workflow. No media or host receipts
can opt a job into this path.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import time

ROOT = Path('/opt/muxmender-score')
POLICY = 2
FRAME_TOLERANCE = 0.0001
BOUNDARY_MARGIN = 0.01


def discover(cpu_binary):
    if not sys.platform.startswith('linux'):
        return None
    try:
        from gpu_frame_reader import trusted_file
        from encoder_capabilities import nvidia_adapters
        binary = ROOT / 'bin/ffmpeg'
        library = ROOT / 'lib/libvmaf.so.3.0.0'
        cpu = Path(shutil.which(str(cpu_binary)) or cpu_binary)
        files = {}
        for name, path in (('cpu', cpu), ('cuda', binary), ('vmaf', library)):
            data = trusted_file(path, 128*1024*1024)
            if not data.startswith(b'\x7fELF'):
                return None
            files[name] = hashlib.sha256(data).hexdigest()
        if not os.access(binary, os.X_OK):
            return None
        adapters = nvidia_adapters()
        if len(adapters) != 1:
            return None  # Do not guess a device when CUDA routing is ambiguous.
        adapter = {k: adapters[0][k] for k in ('uuid', 'driver')}
        if any(not isinstance(v, str) or not v for v in adapter.values()):
            return None
        binding = dict(policy=POLICY, files=files, adapter=adapter,
                       visibility={k: os.environ.get(k) for k in
                           ('CUDA_VISIBLE_DEVICES', 'NVIDIA_VISIBLE_DEVICES', 'CUDA_DEVICE_ORDER')})
        return dict(binary=str(binary), binding=binding)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def cuda_graph(graph, name):
    """Replace only the metric, keeping its input pixels and comparison clock."""
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
        raise ValueError('Invalid CUDA metric report name')
    match = re.fullmatch(r'(.*)\[d\]\[r\]libvmaf=n_threads=[124]:log_fmt=json:log_path=[A-Za-z0-9_.-]+', graph)
    if match is None:
        raise ValueError('Unknown comparison graph; keep canonical CPU scoring')
    return (match[1] + '[d]hwupload_cuda[gd];[r]hwupload_cuda[gr];'
            '[gd][gr]libvmaf_cuda=n_threads=0:log_fmt=json:log_path=' + name)


def scores(path, count):
    # A complete score file is required; a GPU error cannot approve partial work.
    values = [float(frame['metrics']['vmaf']) for frame in json.loads(Path(path).read_text())['frames']]
    if type(count) is not int or count <= 0 or len(values) != count or any(not math.isfinite(x) for x in values):
        raise ValueError('Incomplete or invalid CUDA score evidence')
    return values


def equivalent(cpu, gpu, count, mean_floor, p5_floor):
    from auto_optimize import quality_summary
    a, b = scores(cpu, count), scores(gpu, count)
    left = quality_summary(json.loads(Path(cpu).read_text()), count, mean_floor, p5_floor)
    right = quality_summary(json.loads(Path(gpu).read_text()), count, mean_floor, p5_floor)
    delta = max(abs(x-y) for x, y in zip(a, b))
    return dict(passed=delta <= FRAME_TOLERANCE and left['passed'] == right['passed'],
                maximum_frame_score_difference=delta, frames=count)


def covered(video, output, hdr_mode, preset, decoder_options):
    # Outside the tested scoring scope means CPU, never an unsupported input.
    if preset != 'original' or decoder_options or video.get('field_order') != 'progressive':
        return False
    if any(type(video.get(k)) is not int or not 0 < video[k] <= limit
           for k, limit in (('width', 3840), ('height', 2160))):
        return False
    if video.get('codec_name') not in ('h264', 'hevc', 'av1', 'ffv1') or output.get('codec_name') not in ('h264', 'hevc', 'av1', 'ffv1'):
        return False
    if video.get('pix_fmt') != output.get('pix_fmt'):
        return False
    return ((not hdr_mode and video.get('pix_fmt') == 'yuv420p') or
            (hdr_mode in ('pq', 'hdr10', 'hdr10plus') and video.get('pix_fmt') == 'yuv420p10le'))


def comparison_video(video, frames, expected, guard):
    """Recover missing scan tags from every already-decoded comparison frame.

    This is scoring eligibility only, never a source metadata rewrite. Explicit
    interlacing stays authoritative. Incomplete or conflicting audits keep CPU.
    """
    if video.get('field_order') not in (None, '', 'unknown'):
        return video
    if type(expected) is not int or expected <= 0:
        return video
    count = 0
    for frame in frames:
        guard()
        count += 1
        if (count > expected or str(frame.get('interlaced_frame')) != '0'
                or str(frame.get('repeat_pict')) != '0'
                or any(str(frame.get(k)) != str(video.get(k)) for k in ('width', 'height', 'pix_fmt'))):
            return video
    if count != expected:
        return video
    return dict(video, field_order='progressive')


def execution_seconds(workflow, label, wall_seconds):
    """Compare active native work, excluding admission and cooperative pauses.

    Older callers and generated test workflows can retain wall timing, but a
    record from a different stage must never select a backend for this one.
    """
    measured = getattr(workflow, 'last_execution_timing', None)
    if isinstance(measured, dict) and measured.get('label') == label and measured.get('completed') is True:
        value = measured.get('execution_seconds')
        if (type(value) in (int, float) and math.isfinite(value) and value > 0
                and value <= wall_seconds + .05
                and measured.get('scope') == 'native-stage-active-v1'):
            return value, 'native-stage-active-v1'
    return wall_seconds, 'stage-wall-v1'


class Scorer:
    """A short complete CPU/GPU comparison qualifies only this job's profile.

    No persisted success bypasses the check after an app, driver or GPU change.
    Near-boundary results always get canonical CPU confirmation. Slow or failed
    GPU work keeps CPU scoring, and cancellation always propagates.
    """
    def __init__(self, workflow):
        self.workflow = workflow
        self.context = discover(workflow.args.ffmpeg)
        self.profiles = {}

    def run(self, reference, output, graph, label, count, duration, video,
            *, preset='original', rendered_reference=False):
        from auto_optimize import quality_command, quality_summary, main_video
        w = self.workflow
        name = label + '-vmaf.json'
        destination = w.directory / name

        def cpu():
            start = time.monotonic()
            w.execute(quality_command(w.args.ffmpeg, output, reference, graph), label+'-quality', duration)
            return execution_seconds(w, label+'-quality', time.monotonic()-start)

        info = dict(backend='cpu', decoding='cpu', policy=POLICY)
        if self.context is None:
            cpu()
            return info
        candidate = main_video(w.probe(output))
        if (Path(reference).resolve()==Path(output).resolve()
                and candidate.get('field_order') in (None,'','unknown')
                and video.get('field_order')=='progressive'):
            # Self-calibration reads the exact same file. Carry its established
            # scan evidence into both profile sides instead of needlessly
            # qualifying the same decoder layout again for a tagged candidate.
            candidate=dict(candidate,field_order='progressive')
        options = [w.decoder_options(p) for p in (reference, output)]
        if not covered(video, candidate, w.hdr_mode, preset, any(options)):
            cpu()
            return dict(info, reason='CPU scoring retained for this comparison profile')
        # Include exact rate/render policy and both decoder profiles, not paths.
        key_graph = re.sub(r'log_path=[A-Za-z0-9_.-]+$', 'log_path=<report>', graph)
        keys = ('codec_name', 'width', 'height', 'pix_fmt', 'field_order', 'color_range',
                'color_space', 'color_transfer', 'color_primaries', 'chroma_location')
        # Rendered references have a different decoder/pixel domain.
        actual_reference = main_video(w.probe(reference)) if rendered_reference else video
        profile = json.dumps(dict(binding=self.context['binding'], graph=key_graph,
            source={k: actual_reference.get(k) for k in keys},
            output={k: candidate.get(k) for k in keys}), sort_keys=True)
        state = self.profiles.get(profile)
        qualifying = state is None and 0 < duration <= 60 and 0 < count <= 6000
        if (state is None and not qualifying) or state is False:
            cpu()
            return dict(info, reason='CPU scoring retained until a matching short trial qualifies')
        cpu_seconds, cpu_scope = cpu() if qualifying else (None, None)
        gpu_name = label + '-cuda-vmaf.json'
        try:
            command = quality_command(self.context['binary'], output, reference, cuda_graph(graph, gpu_name))
            command[1:1] = ['-init_hw_device', 'cuda=metric:0', '-filter_hw_device', 'metric']
            start = time.monotonic()
            w.execute(command, label+'-gpu-quality', duration)
            gpu_seconds, gpu_scope = execution_seconds(w, label+'-gpu-quality', time.monotonic()-start)
            gpu_path = w.directory / gpu_name
            # Validation is mandatory even after the profile has qualified.
            scores(gpu_path, count)
            summary = quality_summary(json.loads(gpu_path.read_text()), count, w.args.vmaf_mean, w.args.vmaf_p5)
            if qualifying:
                proof = equivalent(destination, gpu_path, count, w.args.vmaf_mean, w.args.vmaf_p5)
                faster = cpu_scope == gpu_scope and gpu_seconds < cpu_seconds * .95
                self.profiles[profile] = proof['passed'] and faster
                info.update(qualification=proof, cpu_seconds=cpu_seconds, gpu_seconds=gpu_seconds,
                            cpu_timing_scope=cpu_scope, gpu_timing_scope=gpu_scope,
                            qualified_for_later_checks=self.profiles[profile])
                if not self.profiles[profile]:
                    info['qualification_rejection'] = ('score_equivalence_failed' if not proof['passed'] else
                        'timing_scopes_differ' if cpu_scope != gpu_scope else 'no_measured_speed_gain')
                # Retain canonical CPU scores for the trial used to qualify GPU.
                return dict(info, reason='CPU/GPU trial compared; later matching checks use GPU' if self.profiles[profile]
                            else 'CPU scoring retained: GPU was slower or did not match')
            near = any(abs(summary[k]-floor) <= BOUNDARY_MARGIN for k, floor in
                       (('mean', w.args.vmaf_mean), ('p5', w.args.vmaf_p5)))
            if near:
                cpu()
                proof = equivalent(destination, gpu_path, count, w.args.vmaf_mean, w.args.vmaf_p5)
                if not proof['passed']:
                    self.profiles[profile] = False
                return dict(info, reason='Quality threshold confirmed with CPU', qualification=proof)
            # The complete parsed GPU file becomes this stage's metric evidence.
            from job_tracking import replace_record
            replace_record(gpu_path, destination)
            return dict(info, backend='cuda', gpu_seconds=gpu_seconds,
                        gpu_timing_scope=gpu_scope,
                        runtime=self.context['binding'], qualification='matching-job-local-trial')
        except Exception as exc:
            w.guard()  # Cancellation/deadlines must not be converted into fallback.
            self.profiles[profile] = False
            if not qualifying:
                cpu()
            return dict(info, reason='GPU scoring unavailable; complete CPU check used',
                        diagnostic=type(exc).__name__+': '+str(exc)[:400])
