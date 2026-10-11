"""Validate a reviewed public Docker context; never infer redistribution approval."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


def extract_context(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        if len(members) > 20000 or sum(m.size for m in members) > 4 * 1024**3:
            raise ValueError('Release context is oversized')
        seen = set()
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or '..' in name.parts or '\\' in member.name or ':' in member.name
                    or member.name in seen or not (member.isfile() or member.isdir())):
                raise ValueError('Unsafe or duplicate archive member: ' + member.name)
            seen.add(member.name)
        bundle.extractall(destination, filter='data')


def audit(root, version, revision):
    root = Path(root).resolve(strict=True)
    if not re.fullmatch(r'\d{8}-v\d+', version) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Use an exact app version and full source commit')
    manifest = json.loads((root / 'public-release.json').read_text())
    if (manifest.get('schema') != 1 or manifest.get('version') != version
            or manifest.get('revision') != revision
            or manifest.get('redistribution_reviewed') is not True
            or manifest.get('privacy_reviewed') is not True):
        raise ValueError('Matching redistribution and privacy review required')
    materials = manifest.get('materials', [])
    required = {'app-license', 'third-party-notices', 'corresponding-source', 'build-instructions'}
    if not isinstance(materials, list) or not required.issubset({m.get('role') for m in materials}):
        raise ValueError('Missing license/source/build materials')
    for material in materials:
        name = PurePosixPath(material['path'])
        if name.is_absolute() or '..' in name.parts or '\\' in material['path']:
            raise ValueError('Unsafe material path')
        path = root / material['path']
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError('Missing or linked material')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != material['sha256']:
            raise ValueError('Material checksum mismatch: ' + material['path'])
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    with args.archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != args.sha256:
        raise ValueError('Release context checksum mismatch')
    extract_context(args.archive, args.destination)
    result = audit(args.destination, args.version, args.revision)
    print(json.dumps({'version': result['version'], 'revision': result['revision'],
                      'reviewed_materials': len(result['materials'])}))


if __name__ == '__main__':
    main()
