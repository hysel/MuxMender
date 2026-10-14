"""Fetch pinned upstream build inputs on a disposable runner; never publish."""
import hashlib
from pathlib import Path
import shutil
import sys
import urllib.request

from build_app_release import FFMPEG9_SOURCE_CHECKSUMS
from install_fel_runtime import CHECKSUMS, PACKAGES

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'ffmpeg-9.0.2.tar.xz': 'https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz',
    'nv-codec-headers-n13.0.19.0.tar.gz': 'https://codeload.github.com/FFmpeg/nv-codec-headers/tar.gz/refs/tags/n13.0.19.0',
    'vmaf-3.0.0.tar.gz': 'https://codeload.github.com/Netflix/vmaf/tar.gz/refs/tags/v3.0.0',
    'libplacebo-7.351.0.tar.gz': 'https://codeload.github.com/haasn/libplacebo/tar.gz/refs/tags/v7.351.0',
    'vulkan-headers-libplacebo.tar.gz': 'https://codeload.github.com/KhronosGroup/Vulkan-Headers/tar.gz/cacef3039d277c448c89336290ec3937270b0996',
}


def fetch(url, destination, expected):
    if not url.startswith('https://'):
        raise ValueError('HTTPS required')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read(256 * 1024 * 1024 + 1)
    if len(data) > 256 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Build input checksum mismatch: ' + destination.name)
    with destination.open('xb') as stream:
        stream.write(data)


def main():
    if sys.platform != 'linux':
        raise RuntimeError('Run on the Linux build runner, not the development PC')
    for name, url in SOURCES.items():
        fetch(url, ROOT / 'vendor/ffmpeg9-source' / name, FFMPEG9_SOURCE_CHECKSUMS[name])
    shutil.copyfile(ROOT / 'deploy/truenas/ffmpeg9-source.sha256',
                    ROOT / 'vendor/ffmpeg9-source/source.sha256')
    for name in PACKAGES:
        fetch('https://conda.anaconda.org/conda-forge/linux-64/' + name,
              ROOT / 'vendor/fel-runtime-archives' / name, CHECKSUMS[name])
    fetch('https://github.com/bbeny123/FelBaker/releases/download/1.0.0/felbaker-linux-x64-avx2.zip',
          ROOT / 'vendor/fel-runtime-archives/felbaker-linux-x64-avx2.zip', CHECKSUMS['felbaker-linux-x64-avx2.zip'])
    fetch('https://raw.githubusercontent.com/bbeny123/FelBaker/1.0.0/LICENSE',
          ROOT / 'vendor/fel-runtime-archives/LICENSE', CHECKSUMS['LICENSE'])
    fetch('https://github.com/quietvoid/dovi_tool/releases/download/2.3.3/dovi_tool-2.3.3-x86_64-unknown-linux-musl.tar.gz',
          ROOT / 'vendor/dovi.tar.gz', '5dae82cb2becd3b9fd726127f936a8d32635e60746d16238fdfded12aa05988c')
    fetch('https://github.com/quietvoid/hdr10plus_tool/releases/download/1.7.2/hdr10plus_tool-1.7.2-x86_64-unknown-linux-musl.tar.gz',
          ROOT / 'vendor/hdr10plus.tar.gz', '06385f37a639d61ba21d4be3150c863846933bc3b58110e094d8fc8f1c2249f2')
    reader = ROOT / 'reader-build'
    reader.mkdir()
    for name in ('ffmpeg-9.0.2.tar.xz', 'nv-codec-headers-n13.0.19.0.tar.gz'):
        shutil.copyfile(ROOT / 'vendor/ffmpeg9-source' / name, reader / name)
    shutil.copyfile(ROOT / 'tools/patch_cuda_ffprobe.py', reader / 'patch_cuda_ffprobe.py')
    shutil.copyfile(ROOT / 'deploy/truenas/Dockerfile.hdr-gpu-reader', reader / 'Dockerfile')
    notices = ROOT / 'public-materials'
    notices.mkdir()
    (notices / 'REVIEW-PENDING.md').write_text(
        'Build verification only. Source and notice review must finish before distribution.\n')


if __name__ == '__main__':
    main()
