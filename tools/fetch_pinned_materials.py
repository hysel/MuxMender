"""Fetch checksum-pinned public source materials; never execute downloaded content."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from job_tracking import Job

HOSTS = {'github.com', 'codeload.github.com', 'ftp.gnu.org',
         'mirrors.ocf.berkeley.edu', 'files.pythonhosted.org', 'launchpad.net',
         'www.gnupg.org', 'deb.debian.org', 'ftp.osuosl.org', 'code.videolan.org',
         'gitlab.com', 'downloads.sourceforge.net', 'bitbucket.org',
         'www.alsa-project.org', 'www.nasm.us', 'ffmpeg.org', 'repo.almalinux.org', 'static.crates.io'}


def checked_row(row):
    url = urllib.parse.urlsplit(row['url'])
    name = row.get('name') or Path(url.path).name
    if (url.scheme != 'https' or url.hostname not in HOSTS or url.username or url.password
            or url.port not in (None, 443) or not re.fullmatch('[A-Za-z0-9._+-]+', name)
            or name in ('.', '..') or not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
        raise ValueError('Material needs an allowed HTTPS URL, safe filename and SHA256 pin')
    return name


def fetch(manifest, destination, reports, resume=False, continue_on_error=False):
    rows = json.loads(Path(manifest).read_text())
    names = [checked_row(row) for row in rows]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate material filenames')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=resume)
    job = Job(reports, 'Public dependency sources and wheel inspection inputs')
    receipts = []
    errors = []
    try:
        for index, (row, name) in enumerate(zip(rows, names)):
            job.save(phase='Downloading checksum-pinned materials', progress_kind='structured',
                     completed=index, total=len(rows), unit='archives',
                     detail=name, stage_percent=None)
            try:
                final = destination / name
                cached = final.exists()
                if cached:
                    if final.is_symlink() or not final.is_file():
                        raise ValueError('Unsafe cached material')
                    with final.open('rb') as stream:
                        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                    size = final.stat().st_size
                else:
                    digest = hashlib.sha256()
                    size = 0
                    partial = destination / (name + '.' + uuid.uuid4().hex + '.partial')
                    with urllib.request.urlopen(row['url'], timeout=60) as response, partial.open('xb') as target:
                        if urllib.parse.urlsplit(response.url).scheme != 'https':
                            raise ValueError('Insecure download redirect')
                        while chunk := response.read(1024 * 1024):
                            size += len(chunk)
                            if size > 1024**3:
                                raise ValueError('Material exceeds size limit')
                            target.write(chunk); digest.update(chunk)
                    actual = digest.hexdigest()
                if actual != row['sha256']:
                    raise ValueError('Material checksum mismatch: ' + name)
                if not cached:
                    partial.rename(final)
                receipts.append(dict(name=name, url=row['url'], sha256=row['sha256'], size=size, cached=cached))
            except (OSError, ValueError) as exc:
                errors.append(dict(name=name, url=row['url'], error=str(exc)))
                (destination / 'download-errors.json').write_text(json.dumps(errors, indent=2))
                if not continue_on_error:
                    raise
            (destination / 'download-receipts.json').write_text(json.dumps(receipts, indent=2))
        (destination / 'download-errors.json').write_text(json.dumps(errors, indent=2))
        if errors:
            raise RuntimeError(f'{len(errors)} material downloads remain unresolved; see download-errors.json')
        job.save(state='completed', phase='Pinned material downloads verified',
                 finished=time.time(),
                 completed=len(rows), total=len(rows), unit='archives',
                 detail='Archives retained for review; nothing executed or published')
    except Exception as exc:
        job.save(state='failed', phase='Material download failed', detail=str(exc), finished=time.time())
        raise
    return receipts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Revalidate cached files; never overwrite a mismatch')
    parser.add_argument('--continue-on-error', action='store_true', help='Collect other sources while retaining each failure')
    args = parser.parse_args()
    receipts=fetch(args.manifest, args.destination, args.reports, args.resume, args.continue_on_error)
    print(json.dumps(dict(verified=len(receipts),destination=str(args.destination))))
