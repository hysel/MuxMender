"""Read-only Linux runtime inventory for release review; no media or host access."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys


def nonredistributable(configuration):
    return '--enable-nonfree' in configuration.split() or 'nonfree and unredistributable' in configuration.lower()


def ffmpeg9_issues(readers, libraries):
    """Check real executable banners and loaded PyAV ABIs, not package labels."""
    issues=[]
    for reader in readers:
        if not re.search(r'(?m)^ff(?:mpeg|probe) version (?:n)?9\.',reader['version_output']):
            issues.append('Not FFmpeg 9: '+reader['path'])
    expected={'libavcodec':63,'libavformat':63,'libavutil':61,
              'libavfilter':12,'libswscale':10,'libswresample':7,'libavdevice':63}
    for name,major in expected.items():
        version=libraries.get(name,[])
        if not version or version[0]!=major:
            issues.append('Unexpected or missing PyAV ABI: '+name)
    return issues


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
    import av
    libraries={name:list(version) for name,version in av.library_versions.items()}
    return dict(schema=1, readers=readers, packages=packages.splitlines(),
                pyav_version=av.__version__,pyav_libraries=libraries,
                ffmpeg9_issues=ffmpeg9_issues(readers,libraries),
                redistribution_blocked=any(r['redistribution_blocked'] for r in readers))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-redistributable', action='store_true')
    parser.add_argument('--require-ffmpeg9', action='store_true')
    args = parser.parse_args()
    result = collect()
    print(json.dumps(result, indent=2))
    if args.require_ffmpeg9 and result['ffmpeg9_issues']:
        raise SystemExit('FFmpeg 9 migration incomplete: '+ '; '.join(result['ffmpeg9_issues']))
    if args.require_redistributable and result['redistribution_blocked']:
        raise SystemExit('Nonfree FFmpeg configuration found; do not publish this image')


if __name__ == '__main__':
    main()
