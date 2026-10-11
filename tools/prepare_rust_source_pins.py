"""Read Cargo locks as data and list checksum-pinned crate sources; never run Cargo."""
import argparse
import json
from pathlib import Path
import re
import tarfile
import tomllib


def pins(archives):
    rows = {}
    for path in archives:
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if not member.isfile() or not member.name.endswith('/Cargo.lock'):
                    continue
                if member.size > 4 * 1024**2:
                    raise ValueError('Oversized Cargo lock')
                lock = tomllib.loads(archive.extractfile(member).read().decode())
                for package in lock.get('package', []):
                    source = package.get('source')
                    if not source:
                        continue  # Workspace sources are already in the parent archive.
                    if source != 'registry+https://github.com/rust-lang/crates.io-index':
                        raise ValueError('Nonstandard source requires separate pinned materials')
                    name, version, digest = package['name'], package['version'], package.get('checksum', '')
                    if (not re.fullmatch('[A-Za-z0-9_-]+', name)
                            or not re.fullmatch('[A-Za-z0-9.+-]+', version)
                            or not re.fullmatch('[0-9a-f]{64}', digest)):
                        raise ValueError('Invalid crate source pin')
                    key = (name, version)
                    row = dict(name=f'{name}-{version}.crate',
                               url=f'https://static.crates.io/crates/{name}/{name}-{version}.crate', sha256=digest)
                    if key in rows and rows[key]['sha256'] != digest:
                        raise ValueError('Conflicting crate checksum')
                    rows[key] = row
    if not rows:
        raise ValueError('No pinned registry dependencies found')
    return [rows[key] for key in sorted(rows)]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, nargs='+', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    with args.destination.open('x') as target:
        target.write(json.dumps(pins(args.archives), indent=2))
