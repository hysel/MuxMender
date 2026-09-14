"""Write a separately remuxed copy with original track flags, then fully validate it."""
import argparse
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import time
import uuid

import amd_av1_preview as av
import amd_av1_revalidate as rv
from job_tracking import tracked_call, phase


def run(args):
    previous = json.loads((args.run_dir/'validation.json').read_text(encoding='utf-8-sig'))
    source = Path(previous['source']).resolve(strict=True)
    encoded = Path(previous['output']).resolve(strict=True)
    encoded.relative_to(args.run_dir.resolve(strict=True))
    if source == encoded or not previous.get('source_sha256_before'):
        raise ValueError('Separate encoded file and original checksum required')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.output_dir).free < encoded.stat().st_size + 5*1024**3:
        raise ValueError('Insufficient disk space')
    directory = args.output_dir/('AMD-flags-corrected-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(exist_ok=False)
    av.worker.save(directory/'job.json', dict(state='running', title='Restore original track flags', updated=time.time()))
    ctx = av.worker.Context(directory)
    phase(directory, 'Verify original before flag correction', 0)
    if av.checksum(source, ctx) != previous['source_sha256_before']:
        raise ValueError('Original checksum no longer matches')
    streams = av.np.checked_json([args.ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(source)], timeout=120)['streams']
    output = directory/(source.stem+'.AV1-QP80.FlagsPreserved.mkv')
    duration = av.probe_with_frame_color(encoded, args.ffprobe).duration_seconds
    phase(directory, 'Copy existing streams with original track flags — no encoding', 10)
    av.np.stage([args.ffmpeg, '-hide_banner', '-v', 'warning', '-xerror', '-nostdin', '-n',
                 '-copyts', '-i', str(encoded), '-map', '0', '-map_metadata', '0', '-map_chapters', '0',
                 '-c', 'copy', *av.disposition_options(streams), '-avoid_negative_ts', 'disabled',
                 '-progress', 'pipe:1', '-nostats', str(output)], duration,
                timeout=1200, stall=120, guard=ctx.guard, observe=av.reject_integrity_warning)
    av.worker.save(directory/'validation.json', dict(status='pending-full-revalidation',
        source=str(source), output=str(output), source_sha256_before=previous['source_sha256_before'],
        prior_output=str(encoded), note='Remux only; not approved until full validation passes'))
    ctx.update('Remux complete; full validation required', 100, state='completed')
    return rv.run(SimpleNamespace(run_dir=directory, report_dir=args.output_dir,
                                 ffmpeg=args.ffmpeg, ffprobe=args.ffprobe))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args()
    return tracked_call(lambda: run(args), 'Episode 4 track-flag correction and full validation')


if __name__ == '__main__':
    raise SystemExit(main())
