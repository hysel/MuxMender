"""Administrator-only private receipt installation; never changes an app or media."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from host_reader_qualification import verified_receipt


def trusted_directory(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('Qualification destination must have root-owned, non-writable, non-linked parents')


def bounded_read(path,limit):
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('Linked qualification input is not accepted')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=limit:
            raise ValueError('Qualification input must be a bounded regular file')
        data=stream.read(limit+1)
    if not 0<len(data)<=limit:raise ValueError('Missing or oversized qualification input')
    return data


def install(bundle,destination,replace=False):
    if not sys.platform.startswith('linux') or os.geteuid()!=0:
        raise RuntimeError('Run this installer as an administrator on the Linux host')
    bundle=Path(bundle).absolute();destination=Path(destination).absolute()
    trusted_directory(destination.parent)
    payload=verified_receipt(
        json.loads(bounded_read(bundle/'qualification.json',65536)),
        json.loads(bounded_read(bundle/'evidence.json',2*1024*1024)),
        bounded_read(bundle/'ffprobe-cuda',64*1024*1024))
    if not destination.exists():
        destination.mkdir(mode=0o755)
        os.chmod(destination,0o755)
    trusted_directory(destination)
    if stat.S_IMODE(destination.stat().st_mode)!=0o755:
        raise ValueError('Dedicated qualification directory must be mode 0755 so the non-root app can read it')
    target=destination/'qualification.json'
    if target.exists() or target.is_symlink():
        info=target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('Existing receipt is not trusted')
        if target.read_bytes()==payload:
            if stat.S_IMODE(info.st_mode)!=0o444:
                os.chmod(target,0o444)
                return 'Existing verified receipt made readable; app and queue unchanged'
            return 'Already installed; no changes'
        if not replace:raise ValueError('A different receipt exists; inspect it before using --replace')
    temporary=None
    try:
        fd,temporary=tempfile.mkstemp(prefix='.qualification-',dir=destination)
        with os.fdopen(fd,'wb') as stream:
            stream.write(payload);os.fchmod(stream.fileno(),0o444)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target);temporary=None
        directory_fd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:
        if temporary is not None:os.unlink(temporary)
    return 'Verified private receipt installed; app mounts and production queue unchanged'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--destination',type=Path,default=Path('/var/lib/muxmender-reader-qualification'))
    parser.add_argument('--replace',action='store_true')
    args=parser.parse_args()
    print(install(args.bundle,args.destination,args.replace))


if __name__=='__main__':main()
