"""Durable view preferences and deliberately conservative recovery controls.

Archiving changes presentation only. Cleanup deletes only explicitly previewed,
single-link generated media inside a failed request's private output directory.
Replacement journals and source-side recovery files are never removed here.
"""
import math
import time
import uuid
from pathlib import Path
from autonomous_queue import read, signature

ACTIVE = ('pending', 'running')
RETRYABLE = ('failed', 'interrupted', 'skipped')
GENERATED_MEDIA = {'.mkv', '.mp4', '.avi', '.hevc', '.h264', '.ivf', '.yuv', '.wav'}


class WorkspaceHistory:
    def view_action(self, data):
        with self.mutex:
            if not self.ready:raise ValueError('Control worker is not ready; history is read-only')
            prefs = self.state.setdefault('view', {})
            action = data['action']
            if action == 'archive-results':
                previous = set(prefs.get('archived_ids', []))
                current = {j['id'] for j in self.state['jobs'] if j['state'] not in ACTIVE}
                if current - previous:prefs['undo_archive'] = sorted(current - previous)
                prefs['archived_ids'] = sorted(previous | current)
            elif action == 'undo-archive':
                prefs['archived_ids'] = sorted(set(prefs.get('archived_ids', [])) - set(prefs.pop('undo_archive', [])))
            else:
                values = data.get('preferences', {})
                choices = {'sort': ('newest', 'oldest', 'name', 'saved'),
                           'filter': ('all', 'active', 'ready', 'kept', 'attention', 'replaced', 'complete', 'history'),
                           'theme': ('system', 'light', 'dark'), 'show_archived': (True, False)}
                if not isinstance(values, dict) or set(values) - (set(choices) | {'batch'}):
                    raise ValueError('Unknown view preference')
                for key, value in values.items():
                    if key == 'batch':
                        if not isinstance(value, str) or len(value)>4096:raise ValueError('Invalid batch filter')
                        continue
                    if value not in choices[key] or (key == 'show_archived' and type(value) is not bool):
                        raise ValueError('Invalid view preference')
                prefs.update(values)
            self.save()
            return dict(message='Display preferences saved. Processing history and media are unchanged.', view=prefs)

    def request_folder(self, job):
        if not isinstance(job.get('id'), str) or len(job['id']) != 32 or any(c not in '0123456789abcdef' for c in job['id']):
            raise ValueError('Invalid request identifier')
        folder = self.root / ('request-' + job['id'])
        if folder.is_symlink() or folder.resolve().parent != self.root.resolve():
            raise ValueError('Request folder escapes output storage')
        return folder

    def recovery_info(self, job):
        folder = self.request_folder(job)
        journals = []
        for path in folder.glob('auto-*/replacement.json'):
            if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
                raise ValueError('Unsafe replacement journal path')
            record = read(path)
            journals.append(dict(path=str(path), state=record.get('state', 'unknown'),
                                 source=record.get('source'), target=record.get('target'),
                                 backup=record.get('backup'), stage=record.get('stage')))
        # A confirmed manual receipt also forbids blindly re-encoding the source.
        receipts = list(folder.glob('auto-*/approved-replacement.json'))
        source = Path(job['source'])
        target = source if source.suffix.lower()=='.mkv' else source.with_suffix('.mkv')
        # Include exact source-side markers even if a journal was lost. Read only.
        markers = [source.with_name(source.name+'.muxmender-'+job['id']+'.original'),
                   target.with_name(target.name+'.muxmender-'+job['id']+'.staging')]
        present = [str(p) for p in markers if p.exists() or p.is_symlink()]
        blocked = bool(journals or receipts or present or 'Replacement needs attention:' in job.get('reason', ''))
        return dict(job_id=job['id'], journals=journals, recovery_files=present, publication_record_found=blocked,
                    retry_allowed=job['state'] in RETRYABLE and not blocked,
                    cleanup_allowed=job['state'] in ('failed', 'interrupted') and not blocked,
                    message=('Publication records exist. Inspect the journal and verify source, target and backup hashes before manual recovery. '
                             'No retry or cleanup is allowed here; source-side backups are never deleted.' if blocked else
                             'No publication journal found. A retry starts a fresh request, rechecks the source and keeps this history.'))

    def history_action(self, data):
        with self.mutex:
            job = next((j for j in self.state['jobs'] if j['id'] == data.get('job_id')), None)
            if not job:
                raise ValueError('Unknown request')
            info = self.recovery_info(job)
            action = data['action']
            if action == 'inspect-recovery':
                return info
            if not self.ready:raise ValueError('Control worker is not ready; recovery is read-only')
            if action == 'retry-preview':
                if not info['retry_allowed']:
                    raise ValueError('Retry is blocked: active, successful or publication-recovery work must not be repeated')
                source = self.resolve(job['source'])
                if signature(source) != job['signature']:
                    raise ValueError('Source changed. Select it again and review a new request.')
                settings = {k: v for k, v in job['settings'].items() if k != 'codecs'}
                settings.update(path=job['source'], recheck=False, history_mode='retry')
                draft = self.preview(settings)
                self.drafts[draft['preview_id']]['retry_of'] = job['id']
                return draft
            if not info['cleanup_allowed']:
                raise ValueError('Cleanup is limited to failed/interrupted requests without publication records')
            folder = self.request_folder(job)
            if action == 'cleanup-preview':
                files = []
                for path in folder.rglob('*'):
                    if path.suffix.lower() not in GENERATED_MEDIA or not path.is_file():
                        continue
                    self.check_cleanup_path(path, folder)
                    files.append(dict(path=str(path), signature=signature(path)))
                token = uuid.uuid4().hex
                self.cleanup_drafts = {k: v for k, v in getattr(self, 'cleanup_drafts', {}).items() if v['expires'] > time.time()}
                if len(self.cleanup_drafts) >= 20:
                    raise ValueError('Too many cleanup previews')
                self.cleanup_drafts[token] = dict(job_id=job['id'], files=files, expires=time.time()+600)
                return dict(cleanup_id=token, files=files, bytes=sum(f['signature'][0] for f in files),
                            message='Only these generated files will be permanently removed. Logs, history and originals stay.')
            if action != 'cleanup-confirm' or data.get('confirm') is not True:
                raise ValueError('Explicit cleanup confirmation required')
            draft = getattr(self, 'cleanup_drafts', {}).pop(data.get('cleanup_id'), None)
            if not draft or draft['job_id'] != job['id'] or draft['expires'] < time.time():
                raise ValueError('Cleanup preview expired; preview again')
            # Precheck the entire set before deleting anything. No globs or recursive delete.
            for row in draft['files']:
                path = Path(row['path'])
                self.check_cleanup_path(path, folder)
                if signature(path) != row['signature']:
                    raise ValueError('Generated output changed; preview again')
            removed = []
            try:
                for row in draft['files']:
                    path = Path(row['path'])
                    self.check_cleanup_path(path, folder)
                    if signature(path) != row['signature']:
                        raise ValueError('Generated output changed during cleanup')
                    path.unlink()
                    removed.append(row['path'])
            finally:
                job.setdefault('cleanup_history', []).append(dict(at=time.time(), removed=removed))
                self.save()
            return dict(message=f'Removed {len(removed)} generated files permanently. Original media and reports retained.', removed=removed)

    def check_cleanup_path(self, path, folder):
        if not path.resolve(strict=True).is_relative_to(folder.resolve(strict=True)) or path.suffix.lower() not in GENERATED_MEDIA:
            raise ValueError('Cleanup path outside generated media')
        for part in [path, *path.parents]:
            if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
                raise ValueError('Linked paths cannot be cleaned')
            if part == self.output:
                break
        stat = path.stat()
        if not path.is_file() or stat.st_nlink != 1:
            raise ValueError('Only single-link generated files can be removed')


def decision_evidence(folder, selection):
    """Small recorded summary, never invent scores or convert VMAF into a quality percentage."""
    result = {k: selection[k] for k in ('estimated_savings_percent','reason_code','candidates') if k in selection}
    trials = read(Path(folder)/'trials.json').get('trials', [])
    quality = []
    for trial in trials:
        samples = []
        for sample in trial.get('samples', []):
            scores = sample.get('quality', {})
            if all(type(scores.get(k)) in (float,int) and math.isfinite(scores[k]) for k in ('mean','p5')):
                samples.append(dict(mean=scores['mean'],p5=scores['p5'],passed=scores.get('passed') is True,
                                    domain=scores.get('domain','sdr')))
        if samples:quality.append(dict(id=trial.get('id','Unknown trial'),samples=samples))
    if quality:result['quality']=quality
    return result
