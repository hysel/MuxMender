"""Paired full-source runtime qualification; sources mounted read-only, no publication."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def outcome(status, code):
    state = status.get('state')
    if code == 0 and state == 'validated-copy-awaiting-playback':
        return 'validated_copy'
    if code == 0 and state == 'full-output-rejected-insufficient-savings':
        return 'original_kept'
    decision = status.get('decision', {})
    if (code == 0 and state == 'trials-completed' and decision.get('action') == 'keep_original'
            and decision.get('reason_code') != 'evaluation_inconclusive'):
        return 'original_kept'
    return 'needs_attention'


def main():
    if sys.platform != 'linux':
        raise RuntimeError('Linux-only qualification')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request-id', action='append', required=True)
    parser.add_argument('--runtime', choices=('both','baseline','candidate'), default='both')
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    from job_tracking import tracked_call, progress
    from media_workflow import automatic_arguments
    rows = []

    def idle():
        requests = json.loads(Path('/output/ui-requests/requests.json').read_text())
        if any(j.get('state') in ('pending', 'running') for j in requests['jobs']):
            raise RuntimeError('Production must remain idle during serial GPU qualification')
        return requests['jobs']

    def run():
        os.nice(10)
        jobs = idle()
        runtimes = ('baseline','candidate') if args.runtime == 'both' else (args.runtime,)
        total = len(args.request_id) * len(runtimes)
        for index, identifier in enumerate(args.request_id):
            request = next(j for j in jobs if j['id'] == identifier)
            source = Path(request['source']).resolve(strict=True)
            if not source.is_relative_to('/media'):
                raise ValueError('Source outside read-only media mount')
            before = source.stat()
            identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            settings = dict(request['settings'], mode='encode', hardware='nvidia')
            for runtime in runtimes:
                idle()
                progress(f'Case {index+1} · {runtime}', len(rows), total,
                         unit='full-source evaluations', detail='Original settings and gates; no replacement')
                env = dict(os.environ)
                if runtime == 'candidate':
                    env['PATH'] = '/opt/ffmpeg9/bin:' + env['PATH']
                else:
                    env.pop('LD_LIBRARY_PATH', None)
                    env['PATH'] = '/usr/local/bin:/usr/bin:/bin'
                output = args.output / f'case-{index+1}-{runtime}'
                import auto_optimize
                command = [sys.executable, '-B', str(Path(auto_optimize.__file__).resolve()),
                           *automatic_arguments(source, output, settings, min_free_gib=8)]
                started = time.monotonic()
                with (args.output / f'case-{index+1}-{runtime}.log').open('x') as log:
                    code = subprocess.run(command, env=env, stdin=subprocess.DEVNULL,
                                          stdout=log, stderr=subprocess.STDOUT).returncode
                states = list(output.glob('auto-*/status.json'))
                status = json.loads(states[0].read_text()) if len(states) == 1 else {}
                cleanup_path = states[0].parent/'terminal-cleanup.json' if len(states) == 1 else None
                cleanup = json.loads(cleanup_path.read_text()) if cleanup_path and cleanup_path.is_file() else {}
                after = source.stat()
                unchanged = identity == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                rows.append(dict(case=index+1, runtime=runtime, request_id=identifier,
                    source_bytes=before.st_size, historical_state=request['state'],
                    elapsed_seconds=round(time.monotonic()-started, 3), exit_code=code,
                    outcome=outcome(status, code), state=status.get('state'),
                    decision=status.get('decision'), error=status.get('error'),
                    cleanup={k:cleanup.get(k) for k in ('state','files','bytes','error')},
                    source_stat_unchanged=unchanged, saved_percent=status.get('saved_percent')))
                (args.output / 'result.json').write_text(json.dumps(dict(results=rows,
                    complete=len(rows)==total, production_changed=False, publication_authorized=False,
                    quality_gates_changed=False), indent=2))
                if not unchanged:
                    raise ValueError('Source identity changed')
        progress('Paired full-source evaluations finished', total, total, unit='full-source evaluations',
                 detail='Read result.json for validation outcomes; execution is not deployment approval')
        return 0

    return tracked_call(run, 'FFmpeg 8 versus 9 — full-source comparison', folder=args.output/'reports')


if __name__ == '__main__':
    raise SystemExit(main())
