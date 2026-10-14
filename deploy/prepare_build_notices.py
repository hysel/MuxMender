"""Verify required notice bytes before building; not a license-review approval."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from audit_public_release import extract_context


def validate(root):
    root = Path(root).resolve(strict=True)
    materials = root / 'public-materials'
    required = ('MuxMender-LICENSE', 'THIRD-PARTY-NOTICES.txt',
                'BUILD-INSTRUCTIONS.txt', 'notice-index.json', 'source-index.json')
    for name in required:
        path = materials / name
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError('Missing required release material: ' + name)
    if (materials / 'REVIEW-PENDING.md').exists():
        raise ValueError('Placeholder notices cannot be packaged')
    rows = json.loads((materials / 'notice-index.json').read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError('Nonempty notice index required')
    seen = set()
    for row in rows:
        name = row['path']
        parts = PurePosixPath(name)
        if (parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name
                or not parts.parts or parts.parts[0] != 'public-materials' or name in seen):
            raise ValueError('Unsafe or duplicate notice path')
        seen.add(name)
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(materials.resolve()) or not path.is_file():
            raise ValueError('Missing or linked notice: ' + name)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != row['sha256']:
            raise ValueError('Notice checksum mismatch: ' + name)
    for path in materials.rglob('*'):
        if path.is_symlink():
            raise ValueError('Linked release material')
        if path.is_file() and path.relative_to(root).as_posix() not in seen and path != materials / 'notice-index.json':
            raise ValueError('Unindexed release material: ' + str(path))
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{64}', args.sha256):
        raise ValueError('SHA256 required')
    with args.archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != args.sha256:
            raise ValueError('Notice archive checksum mismatch')
    extract_context(args.archive, args.destination)
    print(json.dumps(dict(verified_notices=validate(args.destination), publication_approved=False)))


if __name__ == '__main__':
    main()
