"""Validate an existing AMD AV1 full-file copy without encoding or changing media."""
import argparse
import json
from pathlib import Path
import time
import uuid

import amd_av1_preview as av
from job_tracking import tracked_call, phase


def run(args):
    previous = json.loads((args.run_dir/'validation.json').read_text(encoding='utf-8-sig'))
    source = Path(previous['source']).resolve(strict=True)
    output = Path(previous['output']).resolve(strict=True)
    output.relative_to(args.run_dir.resolve(strict=True))
    if source == output or not previous.get('source_sha256_before'):
        raise ValueError('Separate output and original checksum evidence required')
    directory = args.report_dir / ('AMD-revalidation-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    av.worker.save(directory/'job.json', dict(title='Existing AMD AV1 output revalidation',
                                             state='running', updated=time.time()))
    ctx = av.worker.Context(directory)
    before = source.stat(), output.stat()
    result = dict(status='running', source=str(source), output=str(output), prior_run=str(args.run_dir))
    phase(directory, 'Verify existing media checksums', 0)
    try:
        result['source_sha256_before'] = av.checksum(source, ctx)
        if result['source_sha256_before'] != previous['source_sha256_before']:
            raise ValueError('Source no longer matches original conversion checksum')
        result['output_sha256_before'] = av.checksum(output, ctx)
        av.validate_output(args, source, source, output, directory, ctx, result, True)
        result['output_sha256_after'] = av.checksum(output, ctx, 95, 5)
        if result['output_sha256_before'] != result['output_sha256_after']:
            raise ValueError('Output changed during validation')
        result['status'] = 'verified-full-file-awaiting-playback'
        ctx.update('Revalidation passed', 100, state='completed')
        phase(directory, 'Full revalidation passed — ready for playback review', 100)
        return 0
    except BaseException as exc:
        result.update(status='failed-all-files-retained', error=str(exc))
        ctx.update('Revalidation failed; files retained', state='failed', error=str(exc))
        raise
    finally:
        after = source.stat(), output.stat()
        unchanged = all((a.st_size, a.st_mtime_ns) == (b.st_size, b.st_mtime_ns) for a,b in zip(before,after))
        result.update(media_stat_unchanged=unchanged, finished=time.time())
        if not unchanged:
            result.update(status='failed-all-files-retained', error='Media changed during validation')
        av.worker.save(directory/'validation.json', result)
        print(json.dumps(result, indent=2), flush=True)
        if not unchanged:
            raise ValueError(result['error'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args()
    return tracked_call(lambda: run(args), 'AMD AV1 existing-output full revalidation')


if __name__ == '__main__':
    raise SystemExit(main())
