"""Sequential experimental AMD 1080p SDR batches. Dry-run by default; never deletes media."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import amd_av1_preview as av
import library_planner as planner
import workflow_worker as worker
from job_tracking import tracked_call, phase

SUCCESS = 'validated-experimental-full-file-awaiting-playback'


def fingerprint(path):
    stat = path.stat()
    return dict(size=stat.st_size, mtime_ns=stat.st_mtime_ns)


def disjoint(source, output):
    source, output = source.resolve(strict=True), output.resolve()
    source_root = source if source.is_dir() else source.parent
    if output == Path(output.anchor) or output == source_root or source_root in output.parents or output in source_root.parents:
        raise ValueError('Use a separate output directory outside the input tree, not a drive root')
    return source, output


def make_plan(source, output, ffprobe):
    source, output = disjoint(source, output)
    entries = []
    for path in sorted(planner.enumerate_media(source), key=lambda p: str(p).casefold()):
        row = dict(source=str(path), action='needs-review')
        try:
            before = fingerprint(path)
            info = planner.probe_with_frame_color(path, ffprobe)
            action, reason = planner.amd_av1_eligibility(info, worker.shape(path, ffprobe))
            if before != fingerprint(path):
                raise ValueError('Source changed during scan')
            row.update(fingerprint=before, action=action, reason=reason)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            row.update(action='probe-error', reason=str(exc))
        entries.append(row)
    return dict(schema='muxmender-amd-batch-v1', source=str(source), output_root=str(output), entries=entries,
                note='Metadata candidates only; not proof of healthy media, savings or visual quality. Originals always retained.')


def digest(path, guard=lambda: None):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(8*1024**2):
            guard()
            value.update(block)
    return value.hexdigest()


def completed_matches(row, previous, output_root, guard):
    if not previous or previous.get('fingerprint') != row.get('fingerprint'):
        return False
    output = Path(previous['output']).resolve()
    if output_root not in output.parents or not output.is_file():
        return False
    source = Path(row['source'])
    return (digest(output, guard) == previous.get('output_sha256')
            and digest(source, guard) == previous.get('source_sha256')
            and fingerprint(source) == row['fingerprint'])


def execute(plan, args, runner=av.run):
    root = Path(plan['output_root'])
    root.mkdir(parents=True, exist_ok=True)
    lock = root/'.amd-batch.lock'
    # No stale-lock auto-removal: another active process must never be displaced.
    with lock.open('x', encoding='utf-8') as stream:
        json.dump(dict(pid=os.getpid(), started=time.time()), stream)
    try:
        return execute_locked(plan, args, runner)
    finally:
        lock.unlink()  # Owned synchronization metadata only, never media.


def execute_locked(plan, args, runner):
    root = Path(plan['output_root'])
    index_path = root/'amd-batch-completed.json'
    index = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else dict(schema='muxmender-amd-completed-v1', files={})
    if index.get('schema') != 'muxmender-amd-completed-v1' or not isinstance(index.get('files'), dict):
        raise ValueError('Unrecognized completed index; not overwriting it')
    directory = root/('AMD-BATCH-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(exist_ok=False)
    worker.save(directory/'plan.json', plan)
    state = dict(schema=plan['schema'], status='running', entries=[], originals_retained=True)
    def save(): worker.save(directory/'batch.json', state)
    def guard():
        if (directory/'STOP').exists():
            raise InterruptedError('Batch stopped; all media retained')
        if shutil.disk_usage(root).free < 5*1024**3:
            raise InterruptedError('Disk reserve reached; batch stopped, all media retained')
    def scan(path):
        # Reading all packets catches container warnings outside sampled preflight windows.
        phase(directory, 'Read-only full container scan: '+path.name, 0)
        av.np.stage([args.ffprobe, '-v', 'warning', '-count_packets', '-show_entries',
                     'stream=index,nb_read_packets', '-of', 'json', str(path)],
                    1, timeout=1200, stall=0, guard=guard, observe=av.reject_integrity_warning)
    print('BATCH DIRECTORY: '+str(directory), flush=True)
    attempted = 0
    save()
    try:
        for planned in plan['entries']:
            row = dict(planned)
            row['status'] = 'pending'
            state['entries'].append(row)
            if row['action'] != 'preview-candidate':
                row['status'] = 'failed-retained' if row['action'] == 'probe-error' else 'skipped'
                save(); continue
            guard()
            source = Path(row['source'])
            try:
                if fingerprint(source) != row['fingerprint']:
                    raise ValueError('Source changed since plan; rescan required')
                key = os.path.normcase(str(source.resolve()))
                phase(directory, 'Check completed output: '+source.name, 0)
                if completed_matches(row, index['files'].get(key), root, guard):
                    row.update(status='already-validated', output=index['files'][key]['output'])
                    save(); continue
                if attempted >= args.max_files:
                    row['status'] = 'deferred-file-limit'
                    save(); continue
                attempted += 1
                if 'amd' not in av.mm.gpu_vendors() or 'av1_amf' not in av.mm.ffmpeg_encoder_names(args.ffmpeg):
                    raise InterruptedError('AMD AV1 unavailable; batch stopped, no installation or CPU fallback')
                if shutil.disk_usage(root).free < row['fingerprint']['size']*2+5*1024**3:
                    raise InterruptedError('Insufficient disk space for next file; batch stopped')
                row['status'] = 'container-scan'
                save()
                scan(source)
                if fingerprint(source) != row['fingerprint']:
                    raise ValueError('Source changed during container scan')
                row['status'] = 'converting'
                save()
                results = []
                code = runner(SimpleNamespace(source=source, output_dir=directory, ffmpeg=args.ffmpeg,
                                              ffprobe=args.ffprobe, full=True, start=0, seconds=30,
                                              execute=True, dry_run=False), on_result=results.append, guard=guard)
                if code or not results or results[-1].get('status') != SUCCESS:
                    raise ValueError('Full-file runner did not return validated success')
                result = results[-1]
                output = Path(result['output']).resolve(strict=True)
                if directory.resolve() not in output.parents:
                    raise ValueError('Unexpected output location')
                if fingerprint(source) != row['fingerprint'] or not result.get('original_size_mtime_unchanged'):
                    raise ValueError('Source changed during batch')
                if not result.get('source_sha256_before') or result['source_sha256_before'] != result.get('source_sha256_after'):
                    raise ValueError('Missing matching original checksums')
                phase(directory, 'Checksum validated output: '+source.name, 95)
                output_hash = digest(output, guard)
                row.update(status='validated-copy', output=str(output), savings_percent=result['total_savings_percent'])
                index['files'][key] = dict(fingerprint=row['fingerprint'], output=str(output),
                                           source_sha256=result['source_sha256_after'], output_sha256=output_hash)
                worker.save(index_path, index)
            except InterruptedError:
                row['status'] = 'stopped'
                raise
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                row.update(status='failed-retained', error=str(exc))
                print('File rejected; original retained: '+str(exc), flush=True)
            save()
        state['status'] = 'completed-with-errors' if any(r['status']=='failed-retained' for r in state['entries']) else 'completed'
        phase(directory, state['status'], 100)
        return int(state['status']=='completed-with-errors')
    except BaseException as exc:
        state.update(status='stopped', error=str(exc))
        raise
    finally:
        save()
        print('BATCH REPORT: '+str(directory/'batch.json'), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    parser.add_argument('--max-files', type=int, default=1, help='Maximum attempted files per invocation (default: 1)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.max_files < 1: parser.error('--max-files must be positive')
    plan = make_plan(args.source, args.output_dir, args.ffprobe)
    if not args.execute:
        print(json.dumps(plan, indent=2), flush=True)
        return int(any(r['action']=='probe-error' for r in plan['entries']))
    return tracked_call(lambda: execute(plan,args), 'Safe sequential AMD AV1 batch')


if __name__ == '__main__':
    raise SystemExit(main())
