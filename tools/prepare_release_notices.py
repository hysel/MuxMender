"""Prepare private release-review materials without approving or publishing them."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from job_tracking import Job

NOTICE_GROUPS = {'ubuntu-notices', 'python-notices', 'wheel-notices', 'rust-notices-r2',
                 'recovered-notices-r2', 'conda-materials'}
CUSTOM_GROUPS = {'custom-sources', 'upstream', 'wheel-sources'}


def copy_upstream_notices(source, destination, label):
    """Read upstream archives as data, retaining short license/notice files."""
    copied = []
    with tarfile.open(fileobj=source, mode='r|*') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if not member.isfile() or len(path.parts) > 4:
                continue
            if not re.match(r'^(LICENSE|COPYING|NOTICE|COPYRIGHT|AUTHORS)([._-]|$)', path.name, re.I):
                continue
            if path.is_absolute() or '..' in path.parts or '\\' in member.name or ':' in member.name:
                raise ValueError('Unsafe upstream notice path')
            if member.size > 1024**2:
                raise ValueError('Oversized upstream notice')
            target = destination/'public-materials/notices/upstream'/label/member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as stream, target.open('xb') as output:
                shutil.copyfileobj(stream, output)
            copied.append(dict(path=target.relative_to(destination).as_posix(),
                               sha256=digest(target), size=member.size))
    return copied


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(bundle_dir, destination, root=ROOT):
    bundle_dir, destination, root = map(Path, (bundle_dir, destination, root))
    receipt = json.loads((bundle_dir / 'bundle-receipt.json').read_text())
    name = receipt['bundle']
    if name != PurePosixPath(name).name or '\\' in name or ':' in name:
        raise ValueError('Source bundle must be a local filename')
    bundle = bundle_dir / name
    if bundle.is_symlink() or digest(bundle) != receipt['sha256']:
        raise ValueError('Source bundle checksum mismatch')
    if not re.fullmatch('[0-9a-f]{40}', receipt['revision']):
        raise ValueError('Missing source revision')
    destination.mkdir(parents=True, exist_ok=False)
    materials = destination / 'public-materials'
    materials.mkdir()
    catalog = json.loads((bundle_dir / 'source-file-catalog.json').read_text())
    expected = {row['path']: row for row in catalog}
    copied = []
    with tarfile.open(bundle) as archive:
        seen = set()
        for member in archive:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or '\\' in member.name
                    or ':' in member.name or member.name in seen or not member.isfile()):
                raise ValueError('Unsafe source bundle member')
            seen.add(member.name)
            if path.parts and path.parts[0] in CUSTOM_GROUPS and member.name.endswith(('.tar.gz', '.tar.xz', '.tar.bz2')):
                # The outer bundle was checksum-verified before reading any nested data.
                with archive.extractfile(member) as stream:
                    copied.extend(copy_upstream_notices(stream, destination, member.name))
            if not path.parts or path.parts[0] not in NOTICE_GROUPS:
                continue
            # Keep original notice bytes and recipe/patch context, never execute them.
            row = expected.get(member.name)
            if not row or member.size != row['size'] or member.size > 16 * 1024**2:
                raise ValueError('Uncatalogued or oversized notice')
            target = materials / 'notices' / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
            if digest(target) != row['sha256']:
                raise ValueError('Notice checksum mismatch')
            copied.append({'path': target.relative_to(destination).as_posix(),
                           'sha256': row['sha256'], 'size': row['size']})
    if not copied:
        raise ValueError('No dependency notices found')
    shutil.copyfile(root / 'LICENSE', materials / 'MuxMender-LICENSE')
    source_index = {'schema': 1, 'bundle': name, 'sha256': receipt['sha256'],
                    'size': receipt['size'], 'revision': receipt['revision'],
                    'publication_url': None, 'files': catalog}
    (materials / 'source-index.json').write_text(json.dumps(source_index, indent=2), encoding='utf-8')
    (materials / 'notice-index.json').write_text(json.dumps(copied, indent=2), encoding='utf-8')
    (materials / 'THIRD-PARTY-NOTICES.txt').write_text(
        'Dependency notices and original package recipes are under notices/.\n'
        'Licenses for custom FFmpeg, GPU reader, HDR tools and embedded wheel\n'
        'libraries also remain in their matching source archives. See source-index.json.\n'
        'MuxMender is MIT licensed; that license does not replace dependency licenses.\n'
        'This is a private review draft, not completed redistribution clearance.\n', encoding='utf-8')
    (materials / 'BUILD-INSTRUCTIONS.txt').write_text(
        'Source snapshot: ' + receipt['revision'] + '\n'
        'Use app-source.tar from the separate corresponding-source bundle.\n'
        'The runtime recipe is deploy/truenas/Dockerfile.public; custom FFmpeg uses\n'
        'deploy/truenas/build_ffmpeg9.sh. The reader recipe is\n'
        'deploy/truenas/Dockerfile.hdr-gpu-reader with tools/patch_cuda_ffprobe.py.\n'
        'Preserve pinned upstream archives and patches. Conda recipes and patches\n'
        'are in notices/conda-materials; wheel sources include upstream build recipes.\n'
        'Do not execute Linux binaries on Windows. Build and qualify on Linux/NVIDIA.\n'
        'This draft does not claim bit-for-bit reproduction or completed source review.\n', encoding='utf-8')
    roles = [('app-license', 'MuxMender-LICENSE'),
             ('third-party-notices', 'notice-index.json'),
             ('build-instructions', 'BUILD-INSTRUCTIONS.txt')]
    manifest = {'schema': 1, 'revision': receipt['revision'],
                'redistribution_reviewed': False, 'privacy_reviewed': False,
                'materials': [{'role': role, 'path': 'public-materials/' + filename,
                               'sha256': digest(materials / filename)} for role, filename in roles],
                'source_asset': {k: source_index[k] for k in ('bundle', 'sha256', 'size')},
                'remaining': ['Complete source/license and privacy review',
                              'Bind final version/revision and separate source asset',
                              'Public publication approval and anonymous pull']}
    # Deliberately not public-release.json: the publication audit must reject a draft.
    (destination / 'release-review.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return {'notices': len(copied), 'notice_bytes': sum(r['size'] for r in copied),
            'source_bundle_copied_into_image': False, 'reviewed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-dir', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    job = Job(args.reports, 'Public image notice and source-index preparation')
    try:
        job.save(phase='Verifying source bundle and preparing release notices')
        result = prepare(args.bundle_dir, args.destination)
        job.save(state='completed', phase='Release review materials prepared', finished=time.time(),
                 detail='Private draft only; no publication, deployment or media changes')
        print(json.dumps(result))
    except Exception as exc:
        job.save(state='failed', phase='Release material preparation failed', finished=time.time(), detail=str(exc))
        raise
