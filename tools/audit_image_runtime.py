"""Read-only Linux runtime inventory for release review; no media or host access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def nonredistributable(configuration):
    return '--enable-nonfree' in configuration.split() or 'nonfree and unredistributable' in configuration.lower()


def collect():
    if sys.platform != 'linux':
        raise RuntimeError('Image inventory is Linux-only')
    paths = {Path(p).resolve() for p in [shutil.which('ffmpeg'), shutil.which('ffprobe'),
             '/usr/local/bin/ffmpeg', '/usr/local/bin/ffprobe',
             '/opt/muxmender-readers/ffprobe-cuda'] if p and Path(p).is_file()}
    readers = []
    for path in sorted(paths):
        result = subprocess.run([str(path), '-version'], capture_output=True, text=True,
                                timeout=15, check=True)
        output = result.stdout + result.stderr
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        readers.append(dict(path=str(path), sha256=digest, version_output=output,
                            redistribution_blocked=nonredistributable(output)))
    packages = subprocess.run(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n'],
                              capture_output=True, text=True, timeout=30, check=True).stdout
    return dict(schema=1, readers=readers, packages=packages.splitlines(),
                redistribution_blocked=any(r['redistribution_blocked'] for r in readers))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-redistributable', action='store_true')
    args = parser.parse_args()
    result = collect()
    print(json.dumps(result, indent=2))
    if args.require_redistributable and result['redistribution_blocked']:
        raise SystemExit('Nonfree FFmpeg configuration found; do not publish this image')


if __name__ == '__main__':
    main()
