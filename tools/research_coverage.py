"""Read-only recursive coverage audit; never treats path-only history as proof."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

from autonomous_queue import signature
from media_naming import MEDIA_EXTENSIONS


def classify(path, stamp, jobs):
    related = [j for j in jobs if str(path) in (j.get('source'), j.get('published_path'))]
    matching = []
    for job in related:
        published = job.get('state') == 'replaced' and job.get('published_path') == str(path)
        recorded = job.get('published_signature') if published else job.get('signature')
        if recorded == stamp:
            matching.append(job)
    if not matching:
        return dict(category='stale_history' if related else 'never_processed', attempts=len(related))
    latest = max(matching, key=lambda j: (j.get('created') or 0, j.get('finished') or 0))
    state = latest.get('state', 'unknown')
    category = {'replaced': 'converted', 'skipped': 'retained_decision',
                'kept-original': 'retained_decision',
                'failed': 'unresolved_failure', 'interrupted': 'interrupted',
                'pending': 'queued', 'running': 'running',
                'analyzed': 'analysis_only', 'tested': 'test_only',
                'awaiting-playback': 'retained_output'}.get(state, 'unresolved_state')
    reason=str(latest.get('reason') or '')
    if state=='skipped' and (reason.startswith('Unsupported input:') or 'temporarily disabled' in reason):
        category='retained_blocker'
    return dict(category=category, state=state, job_id=latest.get('id'),
                reason=latest.get('reason'), decision_code=latest.get('decision_code'),
                policy=latest.get('evaluation_policy'), attempts=len(related),
                prior_failures=sum(j.get('state') in ('failed', 'interrupted') for j in related))


def audit(root, jobs):
    root = root.resolve(strict=True)
    rows, errors, excluded_directories = [], [], []
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=lambda e: errors.append(str(e))):
        for name in list(dirs):
            path=Path(folder)/name
            if path.is_symlink():
                excluded_directories.append(str(path));dirs.remove(name)
        for name in files:
            path = Path(folder)/name
            if path.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            try:
                if path.is_symlink():
                    rows.append(dict(path=str(path), category='symlink_not_audited'))
                    continue
                stamp = signature(path)
                rows.append(dict(path=str(path), bytes=stamp[0], signature=stamp,
                                 **classify(path, stamp, jobs)))
            except OSError as exc:
                errors.append(str(exc))
    failures=[]
    current={r['path']:r for r in rows}
    for source in sorted({j['source'] for j in jobs if j.get('state') in ('failed','interrupted')}):
        if not Path(source).is_relative_to(root):continue
        attempts=[j for j in jobs if j.get('source')==source]
        aliases={source}|{j['published_path'] for j in attempts if j.get('published_path')}
        present=[current[p] for p in aliases if p in current]
        failed=[j for j in attempts if j.get('state') in ('failed','interrupted')]
        failures.append(dict(source=source,failed_attempts=sum(j.get('state') in ('failed','interrupted') for j in attempts),
                             current_categories=sorted({p['category'] for p in present}),
                             resolved_with_current_replacement=any(p['category']=='converted' for p in present),
                             latest_reason=max(attempts,key=lambda j:j.get('created') or 0).get('reason'),
                             latest_failure_reason=max(failed,key=lambda j:j.get('created') or 0).get('reason')))
    return dict(root=str(root), audited_at=time.time(), read_only=True,
                counts=dict(Counter(r['category'] for r in rows)), errors=errors,
                inventory_complete=not errors and not excluded_directories and
                    not any(r['category']=='symlink_not_audited' for r in rows),
                excluded_symlink_directories=excluded_directories,files=rows,historical_failures=failures,
                note='Recorded decisions are not new quality validation. Retained decisions may require retry after policy changes.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--history', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root, json.loads(args.history.read_text())['jobs'])
    with args.report.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}))


if __name__ == '__main__':
    main()
