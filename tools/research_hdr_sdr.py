"""Bounded Linux-only HDR10-base-layer rendering research; never publish media."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

TONES = ('hable', 'mobius', 'reinhard')


def require_idle_production():
    state = json.loads(Path('/output/ui-requests/requests.json').read_text())
    if not state.get('paused') or any(j.get('state') == 'running' for j in state['jobs']):
        raise RuntimeError('Pause production new starts and let active work finish before this research run')


def render_filter(video, target, tone):
    if tone not in TONES:
        raise ValueError('Unknown research renderer')
    from output_presets import scale_filter
    scale = scale_filter(video, target)
    # peak=0 uses frame metadata/default estimation, not a fixed mastering peak.
    return ('setpts=PTS-STARTPTS,zscale=t=linear:npl=100,format=gbrpf32le,'
            f'tonemap=tonemap={tone}:desat=0:peak=0,'
            'zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p10le,'
            'sidedata=mode=delete' + (',' + scale if scale else ''))


def run(root):
    from job_tracking import progress
    from output_presets import preset, geometry
    from auto_optimize import quality_graph, quality_command, quality_summary
    require_idle_production()
    source_status = Path('/work/audio-fix-full-a234ffd131ea/cases/case-0')
    source = Path(json.loads(next(source_status.glob('auto-*/status.json')).read_text())['source']).resolve(strict=True)
    if not source.is_relative_to('/media'):
        raise ValueError('Source must remain inside read-only media mount')
    identity = source.stat()
    os.nice(10)

    def execute(args, name, timeout=600):
        with (root/(name+'.log')).open('x') as log:
            subprocess.run(args, stdin=subprocess.DEVNULL, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=timeout, cwd=root)

    def probe(path, frames=False):
        args = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_streams', '-show_format']
        if frames:
            args += ['-show_frames']
        return json.loads(subprocess.check_output(args+['-of', 'json', str(path)], timeout=60))

    metadata = probe(source)
    video = metadata['streams'][0]
    if video.get('color_transfer') != 'smpte2084' or video.get('color_primaries') != 'bt2020':
        raise ValueError('Research source is not a qualified PQ/BT.2020 base layer')
    for side in video.get('side_data_list', []):
        if side.get('side_data_type') == 'DOVI configuration record' and side.get('dv_bl_signal_compatibility_id') != 1:
            raise ValueError('Dolby Vision source lacks HDR10-compatible base layer')
    duration = float(metadata['format']['duration'])
    rows = []
    total = 3*len(TONES)*2
    for scene, fraction in enumerate((.1, .5, .9)):
        for target in ('tv1080', 'mobile720'):
            for tone in TONES:
                require_idle_production()
                progress('Rendering SDR comparison', completed=len(rows), total=total, unit='clips',
                         detail=f'Scene {scene+1}; {target}; {tone}; research only, no publication')
                name = f'scene-{scene+1}-{target}-{tone}'
                reference, output = root/(name+'-reference.mkv'), root/(name+'.mkv')
                started = time.monotonic()
                execute(['ffmpeg', '-hide_banner', '-nostdin', '-n', '-threads', '2', '-filter_threads', '2',
                         '-ss', str(duration*fraction), '-i', str(source), '-t', '10', '-map', '0:V:0',
                         '-an', '-sn', '-dn', '-map_metadata', '-1', '-map_chapters', '-1',
                         '-vf', render_filter(video, target, tone), '-c:v', 'ffv1', '-level', '3',
                         '-pix_fmt', 'yuv420p10le', '-fps_mode', 'passthrough',
                         '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
                         '-color_range', 'tv', str(reference)], name+'-render')
                render_seconds = time.monotonic()-started
                policy = preset(target)
                started = time.monotonic()
                execute(['ffmpeg', '-hide_banner', '-nostdin', '-n', '-threads', '2', '-i', str(reference),
                         '-map', '0:V:0', '-an', '-sn', '-map_metadata', '-1', '-map_chapters', '-1',
                         '-c:v', 'hevc_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '22', '-b:v', '0',
                         '-maxrate', str(policy['video_bps']), '-bufsize', str(2*policy['video_bps']),
                         '-bf', '0', '-pix_fmt', 'p010le', '-fps_mode', 'passthrough',
                         '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
                         '-color_range', 'tv', str(output)], name+'-encode')
                encode_seconds = time.monotonic()-started
                before, after = probe(reference, True), probe(output, True)
                fields = ('width', 'height', 'best_effort_timestamp_time')
                expected = [tuple(f.get(k) for k in fields) for f in before['frames']]
                actual = [tuple(f.get(k) for k in fields) for f in after['frames']]
                if not expected or actual != expected:
                    raise ValueError('Rendered-reference frame count, geometry or timestamps changed')
                target_geometry = geometry(video, target)
                out_video = after['streams'][0]
                for k in ('width', 'height', 'sample_aspect_ratio'):
                    wanted = target_geometry['sar'] if k == 'sample_aspect_ratio' else target_geometry[k]
                    if out_video.get(k) != wanted:
                        raise ValueError('Output display geometry changed: '+k)
                if any(out_video.get(k) != 'bt709' for k in ('color_transfer', 'color_primaries', 'color_space')):
                    raise ValueError('SDR color metadata incorrect')
                if out_video.get('color_range') != 'tv':
                    raise ValueError('SDR color range incorrect')
                if any(any(x in str(f.get('side_data_list', [])) for x in
                           ('Mastering display', 'Content light', 'HDR Dynamic', 'DOVI')) for f in after['frames']):
                    raise ValueError('SDR frames retain HDR signaling')
                execute(['ffmpeg', '-hide_banner', '-nostdin', '-v', 'error', '-xerror', '-threads', '2',
                         '-i', str(output), '-map', '0:V:0', '-f', 'null', '-'], name+'-decode')
                metric = name+'-quality.json'
                execute(quality_command('ffmpeg', output, reference,
                        quality_graph(metric, video['avg_frame_rate'], threads=2)), name+'-quality')
                score = quality_summary(json.loads((root/metric).read_text()), len(expected), policy['mean'], policy['p5'])
                packets = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                    '-show_packets', '-show_entries', 'packet=size,duration_time', '-of', 'json', str(output)], timeout=60))['packets']
                packet_seconds = sum(float(p['duration_time']) for p in packets)
                video_bps = 8*sum(int(p['size']) for p in packets)/packet_seconds
                passed = score['passed'] and video_bps <= policy['video_bps']
                rows.append(dict(scene=scene+1, target=target, tone=tone, output=output.name,
                    seconds=packet_seconds, bytes=output.stat().st_size, video_bps=video_bps,
                    render_seconds=render_seconds, encode_seconds=encode_seconds, quality=score,
                    passed=passed, frame_timing_geometry_passed=True, sdr_metadata_passed=True,
                    tone_mapping_visually_approved=False))
                result = dict(rows=rows, publication_authorized=False, source_stat_unchanged=None,
                    scope='Video-only 10-second HDR10-base-layer comparisons. VMAF measures encoding against the same lossless SDR render, not tone-mapping accuracy or Dolby Vision presentation. Audio/subtitle preservation and full conversion are not qualified by this experiment.')
                (root/'result.json').write_text(json.dumps(result, indent=2))
                reference.unlink()  # Large, reproducible lossless scratch; keep review clips/evidence.
    latest = source.stat()
    if (identity.st_dev, identity.st_ino, identity.st_size, identity.st_mtime_ns) != (latest.st_dev, latest.st_ino, latest.st_size, latest.st_mtime_ns):
        raise ValueError('Source identity changed')
    result['source_stat_unchanged'] = True
    (root/'result.json').write_text(json.dumps(result, indent=2))
    progress('SDR comparison clips ready', completed=total, total=total, unit='clips',
             detail='Review tone mapping visually before enabling any production transformation')
    return 0 if all(row['passed'] for row in rows) else 1


def run_with_cleanup(root):
    try:
        return run(root)
    finally:
        # Only this runner's reproducible lossless scratch, never retained clips.
        for scene in range(1, 4):
            for target in ('tv1080', 'mobile720'):
                for tone in TONES:
                    (root/f'scene-{scene}-{target}-{tone}-reference.mkv').unlink(missing_ok=True)


if __name__ == '__main__':
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Run only in isolated Linux research container, never on Windows')
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root/'python'))
    from job_tracking import tracked_call
    raise SystemExit(tracked_call(lambda: run_with_cleanup(root), 'HDR-to-SDR short comparison', root/'reports'))
