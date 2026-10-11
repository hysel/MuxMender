"""Collect notices and exact Ubuntu source packages inside a disposable container."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request


def collect(destination):
    if sys.platform != 'linux':
        raise RuntimeError('Source collection is Linux-only; never run on the host')
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    notices = destination / 'notices'
    notices.mkdir()
    sources = destination / 'ubuntu-sources'
    sources.mkdir()
    custom = destination / 'custom-sources'
    custom.mkdir()
    # Copy source/build inputs only, never qualification receipts or private evidence.
    context = Path('/build-context')
    for directory in ('vendor/ffmpeg9-source', 'vendor/gpu-reader/source'):
        source_root = context / directory
        if source_root.is_dir():
            for path in source_root.iterdir():
                if path.is_file() and not path.is_symlink():
                    target = custom / directory.replace('/', '_')
                    target.mkdir(exist_ok=True)
                    shutil.copyfile(path, target / path.name)
    upstream = {
        'felbaker-1.0.0.tar.gz': 'https://codeload.github.com/bbeny123/FelBaker/tar.gz/refs/tags/1.0.0',
        'dovi-tool-2.3.3.tar.gz': 'https://codeload.github.com/quietvoid/dovi_tool/tar.gz/refs/tags/2.3.3',
        'hdr10plus-tool-1.7.2.tar.gz': 'https://codeload.github.com/quietvoid/hdr10plus_tool/tar.gz/refs/tags/1.7.2',
        'pyav-18.1.0.tar.gz': 'https://codeload.github.com/PyAV-Org/PyAV/tar.gz/refs/tags/v18.1.0',
    }
    custom_downloads = []
    for name, url in upstream.items():
        try:
            with urllib.request.urlopen(url, timeout=60) as response, (custom / name).open('xb') as target:
                shutil.copyfileobj(response, target)
            with (custom / name).open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            custom_downloads.append(dict(name=name, url=url, sha256=digest, downloaded=True))
        except (OSError, ValueError) as exc:
            custom_downloads.append(dict(name=name, url=url, downloaded=False, error=str(exc)))
    rows = subprocess.check_output(['dpkg-query', '-W',
        '-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n'], text=True).splitlines()
    packages, unique = [], set()
    for row in rows:
        binary, version, source, source_version = row.split('\t')
        source = source or binary.split(':')[0]
        source_version = source_version or version
        unique.add((source, source_version))
        copyright_file = Path('/usr/share/doc') / binary.split(':')[0] / 'copyright'
        if copyright_file.is_file():
            shutil.copyfile(copyright_file, notices / (binary.replace(':', '_') + '-copyright'))
        packages.append(dict(binary=binary, version=version, source=source, source_version=source_version,
                             copyright_found=copyright_file.is_file()))
    wheel_notices = destination / 'python-notices'
    wheel_notices.mkdir()
    for distribution in importlib.metadata.distributions():
        for entry in distribution.files or []:
            if 'license' in str(entry).lower() or 'notice' in str(entry).lower():
                path = Path(distribution.locate_file(entry))
                if path.is_file():
                    target = wheel_notices / distribution.metadata['Name'] / str(entry).replace('../', '')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
    # Only this disposable container's apt settings are changed.
    for path in Path('/etc/apt/sources.list.d').glob('*.sources'):
        text = path.read_text()
        path.write_text(text.replace('Types: deb\n', 'Types: deb deb-src\n'))
    subprocess.run(['apt-get', 'update'], check=True, timeout=180)
    results = []
    for index, (name, version) in enumerate(sorted(unique), 1):
        print(f'SOURCE_PROGRESS={index}/{len(unique)} {name}', flush=True)
        with (destination / 'source-download.log').open('a') as log:
            result = subprocess.run(['apt-get', 'source', '--download-only', name + '=' + version],
                                    cwd=sources, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        results.append(dict(source=name, version=version, downloaded=result.returncode == 0))
        (destination / 'collection-status.json').write_text(json.dumps(dict(
            state='running', completed=index, total=len(unique), updated=time.time())))
    files = []
    for path in sorted(sources.iterdir()):
        if path.is_file():
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            files.append(dict(path=path.name, sha256=digest, size=path.stat().st_size))
    report = dict(schema=1, packages=packages, downloads=results, files=files, custom_downloads=custom_downloads,
        ubuntu_sources_complete=all(r['downloaded'] for r in results),
        redistribution_reviewed=False,
        remaining=['Custom dependencies and wheel bundled libraries need matching source/build materials',
                   'Review transitive license obligations and private reader evidence'])
    (destination / 'source-inventory.json').write_text(json.dumps(report, indent=2))
    (destination / 'collection-status.json').write_text(json.dumps(dict(state='completed',
        completed=len(results), total=len(results), updated=time.time())))
    print(json.dumps({'ubuntu_sources_complete': report['ubuntu_sources_complete'],
                      'source_packages': len(results), 'redistribution_reviewed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    collect(args.destination)
