"""Paired CUDA scoring for the compatible HDR view of verified DV 8.1 video."""
from fractions import Fraction
import json
import math
import os
from pathlib import Path

from cuda_quality import BOUNDARY_MARGIN, equivalent
from dv_cuda_quality import commands
from hdr_auto import RENDER_FILTER


FLOOR = 90
CALIBRATION_FRAMES = 120
STAGE_LIMIT = 1800


def eligible(before, after, frame_checks, count):
    from auto_optimize import main_video
    from dv_render import single_layer_configuration

    try:
        source = main_video(before)
        output = main_video(after)
        a = single_layer_configuration(before)
        b = single_layer_configuration(after)
    except (ValueError, TypeError, KeyError):
        return False
    return (frame_checks.get('frames') == count and frame_checks.get('progressive') is True
            and frame_checks.get('timing_preserved') is True
            and frame_checks.get('frame_picture_preserved') is True
            and a == b and a['dv_profile'] == 8 and a.get('dv_bl_signal_compatibility_id') == 1
            and all(type(source.get(k)) is int and 0 < source[k] <= limit
                    for k, limit in (('width', 3840), ('height', 2160)))
            and all(source.get(k) == output.get(k) for k in
                    ('width', 'height', 'pix_fmt', 'color_transfer', 'color_primaries',
                     'color_space', 'color_range', 'chroma_location', 'sample_aspect_ratio'))
            and source.get('codec_name') == output.get('codec_name') == 'hevc'
            and source.get('pix_fmt') == 'yuv420p10le'
            and source.get('color_transfer') == 'smpte2084'
            and source.get('field_order') in ('progressive', None, 'unknown')
            and output.get('field_order') in ('progressive', None, 'unknown'))


def compatible_commands(ffmpeg, gpu, candidate, reference, video, rate, directory, count):
    from dv_render import RENDER_FILTER as native_render

    consumer, producers = commands(ffmpeg, gpu, candidate, reference, video, rate, 'hdr.json',
                                    directory, 0, paired=True, frame_count=count)
    for producer in producers:
        start = producer.index('-init_hw_device')
        del producer[start:start+4]
        i = producer.index('-vf')+1
        graph = producer[i]
        if native_render+','+RENDER_FILTER+',' not in graph:
            raise ValueError('Unexpected rendering graph for compatible HDR scoring')
        producer[i] = graph.replace(native_render+',', '', 1)
    return consumer, producers


def read_views(paths, count):
    from auto_optimize import quality_summary

    return {key:quality_summary(json.loads(path.read_text()), count, FLOOR, FLOOR)
            for key, path in paths.items()}


def cuda_views(ffmpeg, context, reference, output, video, directory, count, rate, guard, timeout):
    from job_tracking import progress
    from native_stream import stage

    directory.mkdir()
    command, producers = compatible_commands(ffmpeg, context['binary'], output, reference, video,
                                              rate, directory, count)
    common = dict(os.environ)
    env = dict(common)
    env['LD_LIBRARY_PATH'] = str(Path(context['binary']).parent.parent/'lib')+':'+env.get('LD_LIBRARY_PATH','')
    duration = float(Fraction(count)/Fraction(rate))
    timing = {}
    progress('Checking compatible HDR quality on GPU', detail=f'Comparing {count} frames in both views',
             unit='frames', stage_percent=0)
    with (directory/'score.log').open('x',encoding='utf-8') as log:
        stage(command,duration,producer_commands=producers,producer_env=common,env=env,
              directory=directory,expected_frames=count,guard=guard,timeout=timeout,stall=min(180,timeout),
              observe=lambda line:log.write(line) and False,measurement=timing)
    paths = {key:directory/(key+'-vmaf.json') for key in ('self','candidate')}
    return read_views(paths,count),paths,timing


def measure(ffmpeg, reference, output, directory, count, rate, guard, before, after, frame_checks, cpu_pair, *, mean_floor=90, p5_floor=90):
    """Calibrate per candidate; no successful proof is reused across encodes."""
    from auto_optimize import main_video
    from cuda_quality import discover
    from job_tracking import progress, replace_record
    from native_pipeline import StageTimeout

    if (type(count) is not int or count < CALIBRATION_FRAMES * 2 or
            any(type(f) not in (int,float) or not math.isfinite(f) or not 0 <= f <= 100
                for f in (mean_floor,p5_floor)) or not eligible(before,after,frame_checks,count)):
        return None
    context = discover(ffmpeg)
    if context is None:
        return None
    video = main_video(before)
    scratch = Path(directory)/'hdr-cuda'
    calibration = scratch/'calibration-cpu'
    # Failures in the probe are recoverable via the established complete CPU check.
    try:
        calibration.mkdir(parents=True)
        n = CALIBRATION_FRAMES
        duration = float(Fraction(n)/Fraction(rate))
        if duration > 60:
            return None
        _, cpu_paths, cpu_time = cpu_pair(calibration,n,min(STAGE_LIMIT,240))
        _, gpu_paths, gpu_time = cuda_views(ffmpeg,context,reference,output,video,
                                          scratch/'calibration-gpu',n,rate,guard,180)
        proof = {key:equivalent(cpu_paths[key],gpu_paths[key],n,max(FLOOR,mean_floor),max(FLOOR,p5_floor))
                 for key in cpu_paths}
        if (not all(p['passed'] for p in proof.values()) or
                any(t.get('scope') != 'native-stage-active-v1' for t in [*cpu_time.values(),gpu_time]) or
                gpu_time['execution_seconds'] >= sum(t['execution_seconds'] for t in cpu_time.values())*.95):
            progress('GPU HDR calibration did not qualify; checking on CPU')
            return None
    except (OSError,RuntimeError,ValueError) as exc:
        guard()
        progress('GPU HDR calibration unavailable; checking on CPU',detail=type(exc).__name__)
        return None
    try:
        views, gpu_paths, timing = cuda_views(ffmpeg,context,reference,output,video,scratch/'complete',
                                      count,rate,guard,STAGE_LIMIT)
    except (OSError,RuntimeError,ValueError) as exc:
        guard()
        if isinstance(exc,StageTimeout) and exc.runtime_limit:
            raise RuntimeError('Compatible HDR quality reached the stage time limit; original retained') from exc
        progress('GPU HDR comparison unavailable; checking on CPU',detail=type(exc).__name__)
        return None
    if not views['self']['passed'] or near_boundary(views,mean_floor,p5_floor):
        progress('Confirming compatible HDR scores on CPU')
        return None
    for key,path in gpu_paths.items():
        replace_record(path,Path(directory)/('dv-'+key+'-vmaf.json'))
    return dict(**views,scoring=dict(backend='cuda',calibration=proof,seconds=timing['execution_seconds'],
                                     runtime=context.get('binding')))

def near_boundary(views, mean_floor=None, p5_floor=None):
    floors = [('mean',FLOOR),('p5',FLOOR)]
    floors.extend((k,v) for k,v in (('mean',mean_floor),('p5',p5_floor)) if v is not None)
    return any(abs(view[k]-floor)<=BOUNDARY_MARGIN for view in views.values() for k,floor in floors)
