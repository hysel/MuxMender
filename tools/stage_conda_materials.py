"""Inspect pinned runtime packages without loading native libraries or processing media.

Uses Python 3.14's zstd decoder and PyYAML to retain licenses, recipes and
patches. Source recipes are evidence, not completed redistribution clearance.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile


def retained_members(archive):
    members = archive.getmembers()
    if len(members) > 20000 or sum(m.size for m in members) > 64 * 1024**2:
        raise ValueError('Oversized package metadata')
    seen = set()
    selected = []
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or '..' in path.parts or '\\' in member.name
                or ':' in member.name or member.name in seen
                or not (member.isfile() or member.isdir())):
            raise ValueError('Unsafe package metadata')
        seen.add(member.name)
        if member.isfile() and (member.name.startswith(('info/recipe/', 'info/licenses/'))
                               or member.name in ('info/about.json', 'info/index.json')):
            selected.append(member)
    return selected


def source_rows(recipe):
    rows = recipe.get('source', [])
    if isinstance(rows, dict):
        rows = [rows]
    result = []
    for row in rows:
        urls = row.get('url', [])
        if isinstance(urls, str):
            urls = [urls]
        digest = row.get('sha256', '')
        if not urls or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Source recipe needs URLs and a SHA256 pin')
        result.append(dict(urls=urls, sha256=digest, patches=row.get('patches') or []))
    return result


def stage(archives, destination):
    from compression import zstd
    import yaml
    from install_fel_runtime import inspect_archives, PACKAGES
    archives = inspect_archives(archives)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    rows = []
    for name in PACKAGES:
        with zipfile.ZipFile(archives / name) as package:
            info = [n for n in package.namelist() if n.startswith('info-') and n.endswith('.tar.zst')]
            if len(info) != 1 or package.getinfo(info[0]).file_size > 64 * 1024**2:
                raise ValueError('Unexpected metadata archive')
            # Bounded streaming prevents a compressed metadata expansion bomb.
            with zstd.ZstdFile(io.BytesIO(package.read(info[0]))) as stream:
                expanded = stream.read(64 * 1024**2 + 1)
            if len(expanded) > 64 * 1024**2:
                raise ValueError('Oversized metadata expansion')
        target = destination / name.removesuffix('.conda')
        with tarfile.open(fileobj=io.BytesIO(expanded)) as archive:
            for member in retained_members(archive):
                path = target / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.extractfile(member).read())
        recipe = yaml.safe_load((target / 'info/recipe/meta.yaml').read_text())
        about = json.loads((target / 'info/about.json').read_text())
        rows.append(dict(package=name, license=about.get('license'),
                         recipe_revision=about.get('extra', {}).get('sha'),
                         sources=source_rows(recipe), redistribution_reviewed=False))
    (destination / 'conda-source-inventory.json').write_text(json.dumps(rows, indent=2))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.archives, args.destination), indent=2))
