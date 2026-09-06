"""Read-only full-file preservation checks after an explicitly launched CLI run.

This diagnostic does not encode, publish, delete, or alter source media.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import job_tracking as jobs
import validate_nvidia as v


def main(args):
    run = args.run.resolve()
    evidence = run / ('full-verification-' + time.strftime('%H%M%S') + '-' + uuid.uuid4().hex[:8])
    evidence.mkdir(exist_ok=False)
    source = args.source.resolve()
    baseline = (source.stat().st_size, source.stat().st_mtime_ns)
    report = dict(status='running', source=str(source), checks={},
                  source_stat_capture='During encoding, before verification',
                  limitations=['Playback and visual-quality review required.',
                               'This SDR HEVC result does not certify HDR, AV1, or Dolby Vision.'])
    def save():
        (evidence / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    def guard(start, limit=1800):
        if (run / 'STOP').exists():
            raise RuntimeError('STOP requested; all files retained.')
        if time.monotonic() - start > limit:
            raise RuntimeError('Diagnostic time limit reached; all files retained.')
        if shutil.disk_usage(run).free < 2 * 1024**3:
            raise RuntimeError('Less than 2 GiB free; diagnostic stopped.')
    def command(argv, label, completed):
        jobs.progress(label, completed, 6, directory=evidence)
        print(label, flush=True)
        started = time.monotonic()
        output = evidence / (label + '.json')
        with output.open('xb') as out, (evidence / (label + '.log')).open('xb') as err:
            process = subprocess.Popen(argv, stdout=out, stderr=err)
            try:
                last = started
                while process.poll() is None:
                    guard(started)
                    if time.monotonic() - last >= 15:
                        print(f'{label}: {time.monotonic()-started:.0f}s elapsed', flush=True)
                        last = time.monotonic()
                    time.sleep(.5)
                if process.returncode:
                    raise RuntimeError(f'{label} failed: see retained log')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        return output
    save()
    try:
        jobs.progress('Waiting for full-file NVIDIA encode and mux', 0, 6, directory=evidence)
        started = time.monotonic()
        while not (run / 'cli-report.json').exists():
            guard(started, 7200)
            state = json.loads(args.job.read_text(encoding='utf-8'))
            if state.get('state') in ('failed', 'cancelled'):
                raise RuntimeError('Encoding job did not complete successfully.')
            time.sleep(2)
        cli = json.loads((run / 'cli-report.json').read_text(encoding='utf-8'))
        if cli.get('errors') or len(cli.get('files', [])) != 1 or cli['files'][0].get('status') != 'complete':
            raise RuntimeError('Normal CLI did not accept exactly one output.')
        entry = cli['files'][0]
        output = Path(entry['output'])
        if Path(entry['path']).resolve() != source:
            raise RuntimeError('CLI source does not match verification source.')
        report['output'] = str(output)
        ffprobe, ffmpeg = v.find_tool('ffprobe'), v.find_tool('ffmpeg')
        packets = []
        frames = []
        for index, (label, path) in enumerate((('source', source), ('output', output))):
            result = command([ffprobe, '-v', 'error', '-show_streams', '-show_format',
                              '-show_chapters', '-show_packets', '-show_data_hash', 'sha256',
                              '-of', 'json', str(path)], label + '-packets', index*2)
            packets.append(json.loads(result.read_text(encoding='utf-8')))
            v.validate_source(packets[-1], 'SDR')
            result = command([ffprobe, '-v', 'error', '-threads', '0', '-select_streams', 'v:0', '-show_frames',
                              '-show_entries', 'frame=best_effort_timestamp_time,interlaced_frame,repeat_pict:frame_side_data',
                              '-of', 'json', str(path)], label + '-frames', index*2+1)
            frames.append(json.loads(result.read_text(encoding='utf-8'))['frames'])
        checks = v.compare_sample(*packets, *frames, 'hevc')
        command([ffmpeg, '-v', 'error', '-xerror', '-i', str(output),
                 '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'], 'full-output-decode', 4)
        checks['full_video_audio_decode'] = True
        checks['source_size_mtime_unchanged_since_capture'] = baseline == (source.stat().st_size, source.stat().st_mtime_ns)
        report.update(checks=checks, source_bytes=source.stat().st_size, output_bytes=output.stat().st_size,
                      saved_percent=100*(1-output.stat().st_size/source.stat().st_size),
                      duration_seconds=float(packets[0]['format']['duration']),
                      source_frames=len(frames[0]), output_frames=len(frames[1]))
        state = json.loads(args.job.read_text(encoding='utf-8'))
        if state.get('finished'):
            report['cli_elapsed_seconds'] = state['finished'] - state['started']
            report['cli_speed_x_including_mux'] = report['duration_seconds'] / report['cli_elapsed_seconds']
        if not all(checks.values()):
            raise RuntimeError('Failed checks: ' + ', '.join(k for k, value in checks.items() if not value))
        report['status'] = 'verified-full-file-awaiting-playback'
        jobs.progress('Full SDR HEVC checks passed; playback review pending', 6, 6, directory=evidence)
        print(json.dumps(report, indent=2), flush=True)
        return 0
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        print(f'FAILED: {exc}', flush=True)
        return 1
    finally:
        save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('run', type=Path)
    parser.add_argument('--job', required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(jobs.tracked_call(lambda: main(args), 'NVIDIA full-file preservation and decode verification'))
