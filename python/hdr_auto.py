"""Automatic HDR trials: preserve native output, measure a common rendered view.

The rendering is only for the metric. It never changes the delivered video.
"""
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import shutil

RENDER_FILTER=('zscale=t=linear:npl=100,format=gbrpf32le,'
               'tonemap=tonemap=hable:desat=0:peak=100,'
               'zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p10le')

def admit(video, inspection):
    from hdr_inspection import enforce_automatic_policy
    enforce_automatic_policy(video,inspection)
    transfer=video.get('color_transfer')
    if transfer not in ('smpte2084','arib-std-b67'):
        raise ValueError('HDR transfer cannot be determined from source evidence')
    from source_format import valid_pixel_format
    if not valid_pixel_format(video.get('pix_fmt')):
        raise ValueError('Missing or invalid HDR source pixel format')
    for key in ('color_primaries','color_space','color_range'):
        if video.get(key) in (None,'unknown','unspecified','N/A','0:1'):
            raise ValueError('HDR source evidence is missing '+key)
    if int(video.get('width',0))<=0 or int(video.get('height',0))<=0:
        raise ValueError('Invalid source dimensions')
    return 'hlg' if transfer=='arib-std-b67' else 'pq'


def check_dependencies(ffmpeg, filters):
    for name in ('zscale','tonemap','libvmaf'):
        if name not in filters:raise ValueError('HDR quality evaluation requires FFmpeg filter '+name)
    for name in ('mkvmerge','mkvextract','mkvpropedit','hdr10plus_tool'):
        if not shutil.which(name):raise ValueError('HDR preservation dependency missing: '+name)


def quality_graph(name, frame_rate, frame_count=None, *, threads=2, reference_rendered=False):
    from auto_optimize import quality_graph as ordinary_graph
    ordinary_graph(name,frame_rate,threads=threads)  # Validate before filter interpolation.
    rate=Fraction(frame_rate)
    clock=f'settb=AVTB,setpts=N*{rate.denominator}/({rate.numerator}*TB)'
    # Explicit peak prevents each encoder's metadata choosing a different curve.
    render=RENDER_FILTER
    if type(reference_rendered) is not bool:raise ValueError('Invalid rendered-reference state')
    if frame_count is not None and (type(frame_count) is not int or frame_count<=0):
        raise ValueError('Quality prefix requires a positive frame count')
    prefix=f'trim=end_frame={frame_count},' if frame_count is not None else ''
    reference_filter='' if reference_rendered else render+','
    return (f'[0:V:0]{prefix}{render},{clock}[d];[1:V:0]{prefix}{reference_filter}{clock}[r];'
            f'[d][r]libvmaf=n_threads={threads}:log_fmt=json:log_path={name}')


def measure_prefix_quality(ffmpeg, reference, output, directory, count, rate, guard, *,
                           source_probe=None, candidate_probe=None, frame_checks=None, mean_floor=90, p5_floor=90):
    """Measure the same complete HDR view on CPU or on a calibrated GPU."""
    import json
    from native_pipeline import stage
    from auto_optimize import quality_summary, quality_command
    from job_tracking import progress

    def cpu_pair(folder, frames, timeout):
        results, paths, timings = {}, {}, {}
        for label, candidate in (('self', reference), ('candidate', output)):
            progress('HDR quality self-check' if label == 'self' else 'Checking HDR candidate quality',
                     detail=f'Comparing {frames} decoded frames', unit='frames', stage_percent=0)
            name = 'dv-'+label+'-vmaf.json'
            command = quality_command(ffmpeg, candidate, reference, quality_graph(name, rate, frames))
            timings[label] = {}
            stage(command, float(Fraction(frames)/Fraction(rate)), timeout=timeout, stall=min(timeout, 180),
                  guard=guard, cwd=folder, expected_frames=frames, measurement=timings[label])
            paths[label] = Path(folder)/name
            results[label] = quality_summary(json.loads(paths[label].read_text()), frames, 90, 90)
            if label == 'self' and not results[label]['passed']:
                raise ValueError('HDR quality measurement self-check failed')
        return results, paths, timings

    results = None
    if source_probe is not None and candidate_probe is not None and frame_checks is not None:
        from hdr_cuda_pair import measure
        results = measure(ffmpeg, reference, output, directory, count, rate, guard,
                          source_probe, candidate_probe, frame_checks, cpu_pair, mean_floor=mean_floor, p5_floor=p5_floor)
    if results is None:
        results, _, _ = cpu_pair(directory, count, 1800)
    return dict(**results, domain='hdr-common-render-v1',
                note='Common HDR10 base-layer render; not a native Dolby Vision perceptual model')

def encode_preserved(workflow, source, output, settings, info, before, label, duration):
    from auto_optimize import encode_command,main_video
    from hdr10_trial import chroma_options
    video=main_video(before)
    hevc=settings['codec']=='hevc'
    metadata=None
    if hevc and workflow.hdr_mode in ('pq','hdr10plus'):
        frames=workflow.frame_cache.get(str(source.resolve()))
        if frames is None:frames=workflow.frame_file(source,label+'-hdr-source',before['format'])
        from hdr10plus_extraction import prepare
        metadata=prepare(workflow,source,frames,duration)
    av1_light=None
    av1_frames=None
    if settings['codec']=='av1':
        from av1_content_light import source_light,available
        if available():
            if video.get('codec_name')=='hevc':
                av1_frames=workflow.frame_cache.get(str(source.resolve()))
                if av1_frames is None:av1_frames=workflow.frame_file(source,label+'-hdr-source',before['format'])
            else:av1_light=source_light(workflow,source,before,label)
    encoded=output.with_name(output.stem+'-before-hdr-finalization.mkv') if hevc or av1_light is not None or av1_frames is not None else output
    command=encode_command(workflow.args.ffmpeg,source,encoded,settings,info,before['streams'])
    if hevc:command=command[:-1]+chroma_options(video)+command[-1:]
    elif settings['codec']=='av1':
        command=command[:-1]+av1_chroma_options(video)+command[-1:]
    workflow.execute(workflow.preserve_covers(command,source,before,label),label,duration)
    if av1_frames is not None:
        from av1_hdr_metadata import finalize as finalize_av1_hdr
        finalize_av1_hdr(workflow,source,encoded,output,av1_frames,label,duration)
    elif av1_light is not None:
        from av1_content_light import finalize as finalize_av1
        finalize_av1(workflow,encoded,output,av1_light,label,duration)
    if not hevc:
        # AV1 is tried on merit. Any lost static/dynamic metadata is detected by
        # the same full-frame validator; another candidate can still succeed.
        return
    from hdr10plus_preserve import finalize
    args=SimpleNamespace(source=source,encoded=encoded,output_dir=workflow.directory,
        final_output=output,mode=workflow.hdr_mode,repair_only=True,
        reference_frames=workflow.frame_cache.get(str(source.resolve())),
        reader_cache_root=getattr(workflow,'reader_cache_root',None),
        reference_hdr10plus_json=metadata,
        timeout=workflow.args.timeout,guard=workflow.guard,
        recover_empty_dv=bool(getattr(workflow.args,'dv_declaration_recovery',None)),
        ffmpeg=workflow.args.ffmpeg,ffprobe=workflow.args.ffprobe,
        hdr10plus_tool='hdr10plus_tool',mkvmerge='mkvmerge',mkvextract='mkvextract',mkvpropedit='mkvpropedit')
    result=finalize(args)
    workflow.frame_cache[str(source.resolve())]=Path(result['reference_frames'])
    for value in result.get('intermediates',[]):
        path=Path(value)
        if path.is_symlink() or not path.resolve().is_relative_to(workflow.directory.resolve()) or path in (source,output):
            raise ValueError('Unsafe HDR intermediate registry entry')
        stat=path.stat()
        workflow.hdr_intermediates.setdefault(output.resolve(),[]).append(
            (path,(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)))
    stat=encoded.stat()
    workflow.color_intermediates[output.resolve()]=(encoded,(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns))


def av1_chroma_options(video):
    """Preserve source siting on this no-resize, same-chroma encoding path.

    NVENC can omit AV1 chroma_sample_position although the input planes retain
    their original siting. Set only representable declared positions. Never
    apply this helper to an arbitrary external encode or a resampled picture.
    Decoded HDR metadata and geometry remain independently validated.
    """
    positions={'left':'vertical','topleft':'colocated'}
    position=positions.get(video.get('chroma_location'))
    if position and video.get('pix_fmt') in ('yuv420p','yuv420p10le','yuv420p12le'):
        return ['-chroma_sample_location:v:0',video['chroma_location'],
                '-bsf:v:0','av1_metadata=chroma_sample_position='+position]
    return []
