"""Validate two-stage hardware encoding and muxing against sparse-track fixtures."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid

import job_tracking as jobs
import muxmender as mm
import mux_integrity as nvidia_mux
import validate_nvidia as v
from mux_integrity import verify_startup_interleaving, verify_seek_interleaving
from dv_full_file import ordered_dv_mux_command
from runtime_support import process_memory_bytes


def generated_source(run, duration):
    """No external media dependency; one sparse and one empty subtitle track."""
    sparse, future = run/'sparse.srt', run/'future.srt'
    if not sparse.exists():
        sparse.write_text('1\n00:00:01,000 --> 00:00:02,000\nStart\n\n2\n00:04:50,000 --> 00:04:51,000\nAfter gap\n', encoding='utf-8')
        future.write_text('1\n00:10:00,000 --> 00:10:01,000\nOutside fixture\n', encoding='utf-8')
    source = run/f'stress-{duration}s.mkv'
    command = [v.find_tool('ffmpeg'), '-v', 'error', '-nostdin', '-n',
        '-f', 'lavfi', '-i', f'testsrc2=size=640x360:rate=24:duration={duration},setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709',
        '-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate=48000:duration={duration}',
        '-i', str(sparse), '-i', str(future), '-map', '0:v', '-map', '1:a', '-map', '2:s', '-map', '3:s',
        '-t', str(duration), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'ac3', '-c:s', 'srt',
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv', str(source)]
    subprocess.run(command, check=True, timeout=180)
    return source


def main(long_only=False, ordered_dv=False, hardware='nvidia', codec='hevc', playback_defaults=False):
    run = Path('reports') / ('staged-mux-stress-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    run.mkdir()
    selection = mm.select_encoder(codec, hardware, mm.ffmpeg_encoder_names(v.find_tool('ffmpeg')), mm.gpu_vendors())
    results = []
    for index, duration in enumerate((300,) if long_only else (60, 300)):
        jobs.progress('Generate sparse/empty subtitle fixture', index, 2, directory=run)
        source = generated_source(run, duration)
        video = run / f'{duration}s-video.mkv'
        output = run / f'{duration}s-final.mkv'
        info = mm.probe(source, v.find_tool('ffprobe'))
        info.recommendation = 'transcode'
        def probe(path):
            return json.loads(subprocess.check_output([v.find_tool('ffprobe'), '-v', 'error', '-show_streams', '-show_packets', '-show_data_hash', 'sha256', '-show_chapters', '-of', 'json', str(path)], timeout=60))
        before = probe(source)
        encode = nvidia_mux.video_stage_command(mm.build_ffmpeg_command(source, video, info, codec, 'balanced', v.find_tool('ffmpeg'), selection.encoder, 'keep'))
        finalize = (ordered_dv_mux_command(v.find_tool('ffmpeg'), video, source, output, before)
                    if ordered_dv else nvidia_mux.finalize_command(video, source, output, before, v.find_tool('ffmpeg')))
        commands = [('encode', encode), ('finalize', finalize)]
        peaks = {}
        def execute(stage, command):
            jobs.progress(f'{duration}s {stage}: sparse/empty subtitle validation', index, 2, directory=run)
            print(f'{duration}s {stage}', flush=True)
            peak = 0
            start = time.monotonic()
            with (run / f'{duration}s-{stage}.log').open('xb') as log:
                process = subprocess.Popen(command, stdout=log, stderr=log)
                try:
                    while True:
                        measured = process_memory_bytes(process)
                        if measured is None and process.poll() is None:
                            raise RuntimeError('Memory measurement unavailable')
                        peak = max(peak, measured or 0)
                        if peak > 1024**3 or time.monotonic() - start > 180:
                            raise RuntimeError('Stress safety limit exceeded')
                        if process.poll() is not None:
                            break
                        time.sleep(.02)
                    if process.returncode:
                        raise RuntimeError('Stage failed; see retained log')
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait()
            peaks[stage] = peak
        for stage, command in commands:
            execute(stage, command)
        after = probe(output)
        checks = dict(startup_interleaving=verify_startup_interleaving(output, v.find_tool('ffprobe'))[0], track_inventory=v.stream_inventory(before) == v.stream_inventory(after), audio_subtitle_packets=[[v.packet_signature(p) for p in g] for g in v.packet_groups(before)] == [[v.packet_signature(p) for p in g] for g in v.packet_groups(after)], chapters=before.get('chapters') == after.get('chapters'))
        checks['seek_interleaving'] = verify_seek_interleaving(output, v.find_tool('ffprobe'), [duration*f for f in (0,.1,.5,.9)])[0]
        subtitle_indices = [s['index'] for s in before['streams'] if s['codec_type'] == 'subtitle']
        checks['empty_subtitle_exercised'] = len(subtitle_indices) == 2 and any(not any(p['stream_index']==i for p in before['packets']) for i in subtitle_indices)
        a, b = v.first_video(before), v.first_video(after)
        checks.update({key: a.get(key) == b.get(key) for key in ('width', 'height', 'pix_fmt', 'sample_aspect_ratio', 'color_primaries', 'color_transfer', 'color_space', 'color_range')})
        timestamps = []
        for path in (source, output):
            data = json.loads(subprocess.check_output([v.find_tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)], timeout=120))
            timestamps.append([f['best_effort_timestamp_time'] for f in data['frames']])
        checks['frame_count_and_timing'] = bool(timestamps[0]) and len(timestamps[0]) == len(timestamps[1]) and all(abs(float(a)-float(b)) <= .002 for a,b in zip(*timestamps))
        decode = subprocess.run([v.find_tool('ffmpeg'), '-v', 'error', '-xerror', '-i', str(output), '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'], capture_output=True, timeout=120)
        (run / f'{duration}s-decode.log').write_bytes(decode.stderr)
        checks['full_decode'] = decode.returncode == 0
        if playback_defaults:
            prepared = run / f'{duration}s-playback.mkv'
            plan = nvidia_mux.playback_plan(after, audio_track=0, subtitle_track=0)
            execute('playback', nvidia_mux.playback_command(output, prepared, after, plan, v.find_tool('ffmpeg')))
            final = probe(prepared)
            checks['playback_preservation'] = all(nvidia_mux.verify_playback_copy(output, prepared, after, final, plan, v.find_tool('ffprobe')).values())
            checks['playback_seeks'] = verify_seek_interleaving(prepared, v.find_tool('ffprobe'), [duration*f for f in (0,.1,.5,.9)])[0]
            playback_decode = subprocess.run([v.find_tool('ffmpeg'), '-v', 'error', '-xerror', '-i', str(prepared), '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'], capture_output=True, timeout=120)
            (run/f'{duration}s-playback-decode.log').write_bytes(playback_decode.stderr)
            checks['playback_decode'] = playback_decode.returncode == 0
        results.append(dict(seconds=duration, peaks=peaks, checks=checks))
        (run / 'validation.json').write_text(json.dumps(dict(status='verified-stress' if all(all(r['checks'].values()) for r in results) else 'failed', ordered_dv=ordered_dv, hardware=hardware, codec=codec, playback_defaults=playback_defaults, results=results), indent=2), encoding='utf-8')
        print(json.dumps(results[-1]), flush=True)
        if not all(checks.values()):
            raise RuntimeError('Staged stress preservation failed')
    jobs.progress('Staged hardware memory and preservation checks passed', 2, 2, directory=run)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--long-only', action='store_true')
    parser.add_argument('--hardware', choices=('nvidia','intel'), default='nvidia')
    parser.add_argument('--codec', choices=('hevc','av1'), default='hevc')
    parser.add_argument('--playback-defaults', action='store_true')
    parser.add_argument('--ordered-dv', action='store_true', help='Exercise the experimental DV final mux ordering on generated SDR fixtures; this is not a DV metadata test')
    args = parser.parse_args()
    jobs.tracked_call(lambda: main(args.long_only, args.ordered_dv, args.hardware, args.codec, args.playback_defaults), args.hardware.upper() + ' two-stage mux: memory and preservation')
