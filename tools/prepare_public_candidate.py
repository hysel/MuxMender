"""Overlay reviewed code onto an existing private build context for isolated testing."""
import argparse
import hashlib
import io
from pathlib import Path
import tarfile

FILES = ('deploy/truenas/Dockerfile.public', 'deploy/truenas/launch-public-candidate.sh',
         'tools/smoke_app_release.py', 'tools/audit_image_runtime.py', 'LICENSE',
         'tools/prepare_public_candidate.py', 'tools/monitor_release_stage.py',
         'tests/test_release_monitor.py', 'tests/test_release_smoke.py', 'docs/container-release-operations.md')


def public_reader_member(name):
    if not name.startswith('vendor/gpu-reader/'):
        return True
    return name == 'vendor/gpu-reader/ffprobe-cuda' or name.startswith('vendor/gpu-reader/source/')


def prepare(root, original, expected, destination):
    root = Path(root)
    with Path(original).open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
            raise ValueError('Original context checksum mismatch')
    additions = {name: (root / name).read_bytes() for name in FILES}
    additions['public-materials/REVIEW-PENDING.md'] = (
        b'Private research candidate only. Redistribution materials are incomplete. Do not publish.\n')
    with tarfile.open(original) as source, tarfile.open(destination, 'x') as target:
        for member in source.getmembers():
            if member.name not in additions and public_reader_member(member.name):
                target.addfile(member, source.extractfile(member) if member.isfile() else None)
        for name, content in additions.items():
            if name.endswith('.sh') or Path(name).name.startswith('Dockerfile'):
                content = content.replace(b'\r\n', b'\n')
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            entry.mode = 0o644
            target.addfile(entry, io.BytesIO(content))
    with Path(destination).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.root, args.original, args.sha256, args.destination))
