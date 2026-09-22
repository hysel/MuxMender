"""Automatic HDR trials: preserve native output, measure a common rendered view.

The rendering is only for the metric. It never changes the delivered video.
"""
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import shutil


def admit(video, inspection):
    from hdr_inspection import enforce_automatic_policy
    enforce_automatic_policy(video,inspection)
    transfer=video.get('color_transfer')
    if transfer not in ('smpte2084','arib-std-b67'):
        raise ValueError('HDR transfer cannot be determined from source evidence')
    from auto_optimize import PLANAR_FORMATS
    if video.get('pix_fmt') not in PLANAR_FORMATS:
        raise ValueError('No native encoder mapping for source pixel format '+str(video.get('pix_fmt')))
    for key in ('color_primaries','color_space','color_range','sample_aspect_ratio'):
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


def quality_graph(name, frame_rate, frame_count=None):
    from auto_optimize import quality_graph as ordinary_graph
    ordinary_graph(name,frame_rate)  # Validate filename and rate before filter interpolation.
    rate=Fraction(frame_rate)
    clock=f'settb=AVTB,setpts=N*{rate.denominator}/({rate.numerator}*TB)'
    # Explicit peak prevents each encoder's metadata choosing a different curve.
    render=('zscale=t=linear:npl=100,format=gbrpf32le,'
            'tonemap=tonemap=hable:desat=0:peak=100,'
            'zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p10le')
    if frame_count is not None and (type(frame_count) is not int or frame_count<=0):
        raise ValueError('Quality prefix requires a positive frame count')
    prefix=f'trim=end_frame={frame_count},' if frame_count is not None else ''
    return (f'[0:v:0]{prefix}{render},{clock}[d];[1:v:0]{prefix}{render},{clock}[r];'
            f'[d][r]libvmaf=n_threads=2:log_fmt=json:log_path={name}')


def measure_prefix_quality(ffmpeg, reference, output, directory, count, rate, guard):
    """Matched, preservation-verified prefix; shared HDR metric and score policy."""
    import json
    from native_pipeline import stage
    from auto_optimize import quality_summary, quality_command
    from job_tracking import progress
    results={}
    for label,candidate in (('self',reference),('candidate',output)):
        progress('HDR quality self-check' if label=='self' else 'Checking HDR candidate quality',
                 detail=f'Comparing {count} decoded frames',unit='frames',stage_percent=0)
        name='dv-'+label+'-vmaf.json'
        command=quality_command(ffmpeg,candidate,reference,quality_graph(name,rate,count))
        stage(command,float(Fraction(count)/Fraction(rate)),timeout=1800,stall=180,
              guard=guard,cwd=directory,expected_frames=count)
        results[label]=quality_summary(json.loads((Path(directory)/name).read_text()),count,
                                       90,90)
        if label=='self' and not results[label]['passed']:
            raise ValueError('HDR quality measurement self-check failed')
    return dict(**results,domain='hdr-common-render-v1',
                note='Common HDR10 base-layer render; not a native Dolby Vision perceptual model')


def encode_preserved(workflow, source, output, settings, info, before, label, duration):
    from auto_optimize import encode_command,main_video
    from hdr10_trial import chroma_options
    video=main_video(before)
    hevc=settings['codec']=='hevc'
    encoded=output.with_name(output.stem+'-before-hdr-finalization.mkv') if hevc else output
    command=encode_command(workflow.args.ffmpeg,source,encoded,settings,info,before['streams'])
    if hevc:command=command[:-1]+chroma_options(video)+command[-1:]
    elif settings['codec']=='av1':
        command=command[:-1]+av1_chroma_options(video)+command[-1:]
    workflow.execute(workflow.preserve_covers(command,source,before,label),label,duration)
    if not hevc:
        # AV1 is tried on merit. Any lost static/dynamic metadata is detected by
        # the same full-frame validator; another candidate can still succeed.
        return
    from hdr10plus_preserve import finalize
    args=SimpleNamespace(source=source,encoded=encoded,output_dir=workflow.directory,
        final_output=output,mode=workflow.hdr_mode,repair_only=True,
        reference_frames=workflow.frame_cache.get(str(source.resolve())),
        timeout=workflow.args.timeout,guard=workflow.guard,
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
