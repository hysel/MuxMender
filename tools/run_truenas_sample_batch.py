"""Bounded three-episode experiment; not automatic library replacement."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from app_service import is_read_only

EPISODES = (
    'Example.Series.S01E06.EpisodeB.1080p.BluRay.EAC3.AVC-PiR8.mkv',
    'Example.Series.S01E08.EpisodeC.1080p.BluRay.EAC3.AVC-PiR8.mkv',
    'Example.Series.S01E10.EpisodeD.1080p.BluRay.EAC3.AVC-PiR8.mkv',
)
BATCH = 'SampleSeries-three-episode-batch-20260916'
ROUND2 = (
    'Example.Series.S01E07.EpisodeE.BluRay.EAC3.AVC-PiR8.mkv',
    'Example.Series.S01E09.EpisodeF.1080p.BluRay.EAC3.AVC-PiR8.mkv',
    'Example.Series.S01E04.EpisodeG.1080p.BluRay.EAC3.AVC-PiR8.mkv',
)


def plans(media, output, execute=False, round2=False):
    media, output = media.resolve(strict=True), output.resolve(strict=True)
    if not media.is_dir() or not output.is_dir() or media == output or media in output.parents or output in media.parents:
        raise ValueError('Separate media and output mounts required')
    if execute and not is_read_only(media):
        raise ValueError('Media mount must be read-only')
    commands = []
    batch_name = 'SampleSeries-round2-20260917' if round2 else BATCH
    for name in (ROUND2 if round2 else EPISODES):
        source = (media/'TV/Series/Season 1'/name).resolve(strict=True)
        if not source.is_file() or not source.is_relative_to(media):
            raise ValueError('Source must be a file inside media')
        command = [sys.executable, '-B', '-m', 'auto_optimize', str(source),
                   '--output-dir', str(output/batch_name), '--hardware', 'auto',
                   '--playback-verified-codecs', 'hevc', 'av1', '--encode-best']
        if execute:
            command.append('--execute')
        commands.append(command)
    return output/batch_name, commands


def run(media, output, execute=False, round2=False):
    folder, commands = plans(media, output, execute, round2)
    if not execute:
        print(json.dumps(dict(dry_run=True, commands=commands, originals_retained=True), indent=2))
        return 0
    if shutil.disk_usage(output).free < 12*1024**3:
        raise RuntimeError('At least 12 GiB free required for this bounded batch')
    # Exclusive directory creation prevents accidentally submitting the batch twice.
    folder.mkdir(exist_ok=False)
    state = dict(state='running', originals_retained=True, entries=[])
    def save():
        temporary = folder/'batch-summary.json.tmp'
        temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
        temporary.replace(folder/'batch-summary.json')
    save()
    try:
        for command in commands:
            row = dict(source=command[4], state='running', started=time.time())
            state['entries'].append(row)
            save()
            result = subprocess.run(command, check=False)
            row.update(exit_code=result.returncode, finished=time.time(),
                       state='finished-see-validation' if result.returncode == 0 else 'failed')
            save()
            if result.returncode:
                raise RuntimeError('Episode failed; remaining episodes not started')
        state['state'] = 'finished-see-per-file-results'
        save()
        return 0
    except BaseException as exc:
        state.update(state='stopped-originals-retained', error=str(exc))
        save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media-root', type=Path, default=Path('/media'))
    parser.add_argument('--output-root', type=Path, default=Path('/output'))
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--round2', action='store_true', help='Second set of example episodes; separate output batch')
    args = parser.parse_args()
    raise SystemExit(run(args.media_root, args.output_root, args.execute, args.round2))
