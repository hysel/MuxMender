"""Stage a pinned optional FEL runtime in a fresh directory, without host installs.

Supply archives from the upstream FelBaker 1.0.0 and conda-forge releases.
No downloads, drivers, media processing, app restart, or global environment edits.
The default is checksum-only inspection; --execute stages and load-checks it.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import zipfile

PACKAGES={
 'vapoursynth-73-py312h1289d80_0.conda':'0a7d3b353c2d942cfcdef2f228bac43a86aba5139622782bd089e503f757b251',
 'zimg-3.0.6-hecca717_0.conda':'902fbbbccfb39c62ac2c2b9bf76173d91bfbe4d62505d2cf24abbb9bfc6aa026',
 'libstdcxx-15.3.0-h934c35e_5.conda':'275ed81798e6dd504254470d97e9ca1f48f0457d2478f7bfc2ded547238f0d5d',
 'libgcc-15.3.0-h3363355_5.conda':'81e786e79660f2d9834f7bc5dbd25896a53aa4059b49a790c1b346867c61e128',
}
PLUGIN_ARCHIVE='felbaker-linux-x64-avx2.zip'
CHECKSUMS=dict(PACKAGES,**{PLUGIN_ARCHIVE:'71eae3e89990f3e4eff7085a884c253e00c848ce86ff8b213b26445a7090ba04',
 'LICENSE':'1106c3e8dfd738f0402bf0e2be0c1d4420d95c6170fa2600757c3d694d7ead16'})
PLUGIN_SHA256='29cbe4941b13bd7bc1fc90e1b9bc073c44e5692f4288532123680e415c0ae4ec'


def inspect_archives(directory):
    directory=Path(directory).resolve(strict=True)
    for name,expected in CHECKSUMS.items():
        path=directory/name
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=expected:raise ValueError('Runtime archive checksum mismatch: '+name)
    return directory


def unpack_zstd_tar(packed,destination):
    library=ctypes.util.find_library('zstd')
    if not library:raise RuntimeError('Runtime staging needs libzstd; no host installation was attempted')
    zstd=ctypes.CDLL(library)
    zstd.ZSTD_getFrameContentSize.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
    zstd.ZSTD_getFrameContentSize.restype=ctypes.c_ulonglong
    zstd.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
    zstd.ZSTD_decompress.restype=ctypes.c_size_t
    zstd.ZSTD_isError.argtypes=[ctypes.c_size_t];zstd.ZSTD_isError.restype=ctypes.c_uint
    size=zstd.ZSTD_getFrameContentSize(packed,len(packed))
    if not 0<size<256*1024**2:raise ValueError('Unexpected package expansion size')
    buffer=ctypes.create_string_buffer(size)
    actual=zstd.ZSTD_decompress(buffer,size,packed,len(packed))
    if zstd.ZSTD_isError(actual) or actual!=size:raise ValueError('Runtime decompression failed')
    with tarfile.open(fileobj=io.BytesIO(buffer.raw)) as archive:
        archive.extractall(destination,filter='data')


def install(archives,destination):
    if sys.platform!='linux' or platform.machine().lower() not in ('x86_64','amd64') or sys.version_info[:2]!=(3,12):
        raise RuntimeError('This pinned runtime requires Linux x86-64 and Python 3.12')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
    from dv_fel_runtime import cpu_features,child_environment
    if 'avx2' not in cpu_features():raise RuntimeError('This renderer build requires AVX2 CPU instructions')
    archives=inspect_archives(archives);destination=Path(destination).resolve()
    if archives.is_relative_to(destination):raise ValueError('Runtime destination must not contain its source archives')
    destination.mkdir(parents=True,exist_ok=False)
    prefix=destination/'prefix';prefix.mkdir()
    notices=destination/'notices';notices.mkdir()
    for name in PACKAGES:
        with zipfile.ZipFile(archives/name) as package:
            for kind,target in [('pkg',prefix),('info',notices/name.removesuffix('.conda'))]:
                members=[n for n in package.namelist() if n.startswith(kind+'-') and n.endswith('.tar.zst')]
                if len(members)!=1:raise ValueError('Unexpected conda package layout')
                target.mkdir(parents=True,exist_ok=True)
                unpack_zstd_tar(package.read(members[0]),target)
    with zipfile.ZipFile(archives/PLUGIN_ARCHIVE) as package:plugin=package.read('libfelbaker.so')
    if hashlib.sha256(plugin).hexdigest()!=PLUGIN_SHA256:raise ValueError('Renderer library checksum mismatch')
    (destination/'libfelbaker.so').write_bytes(plugin)
    (notices/'FelBaker-LICENSE').write_bytes((archives/'LICENSE').read_bytes())
    data=dict(schema='muxmender-fel-runtime-v1',plugin_sha256=PLUGIN_SHA256,
              python_version=[3,12],required_cpu_features=['avx2'],library_dir='prefix/lib',
              python_dir='prefix/lib/python3.12/site-packages',archives=CHECKSUMS,
              sources=dict(felbaker='https://github.com/bbeny123/felbaker/tree/1.0.0',
                           packages='https://anaconda.org/conda-forge'))
    (destination/'runtime.json').write_text(json.dumps(data,indent=2))
    environment=child_environment(destination/'libfelbaker.so')
    environment['XDG_CONFIG_HOME']=str(destination/'config')
    (destination/'config').mkdir()
    code='import sys,vapoursynth as vs; vs.core.std.LoadPlugin(sys.argv[1]); print(vs.__version__); print(vs.core.fel.Bake)'
    check=subprocess.run([sys.executable,'-B','-c',code,str(destination/'libfelbaker.so')],
                         env=environment,capture_output=True,text=True,timeout=30)
    (destination/'load-check.json').write_text(json.dumps(dict(returncode=check.returncode,stdout=check.stdout,stderr=check.stderr),indent=2))
    if check.returncode:raise RuntimeError('Runtime load check failed; inspect load-check.json. Partial staging was retained.')
    return data


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv)
    if args.execute:result=install(args.archives,args.destination)
    else:inspect_archives(args.archives);result=dict(dry_run=True,archives=CHECKSUMS,destination=str(args.destination))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
