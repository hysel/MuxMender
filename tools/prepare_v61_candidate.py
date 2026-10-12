"""Package the code-only v61 candidate without executing media or Docker."""
import hashlib
import io
from pathlib import Path
import tarfile


def prepare(root, source, destination, expected):
    root=Path(root);source=Path(source)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
        raise ValueError('Source context checksum mismatch')
    additions={name:(root/name).read_bytes().replace(b'\r\n',b'\n') for name in (
        'deploy/truenas/Dockerfile.update','deploy/truenas/check-v61.sh')}
    with tarfile.open(source) as original, tarfile.open(destination,'x') as output:
        for item in original:
            # Runtime dependencies and their notices remain in the pinned base.
            if item.name.startswith('vendor/') or item.name in additions:
                continue
            if item.name.startswith('/') or '..' in Path(item.name).parts or not (item.isfile() or item.isdir()):
                raise ValueError('Unsafe source context member')
            output.addfile(item,original.extractfile(item) if item.isfile() else None)
        for name,data in additions.items():
            item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o644
            output.addfile(item,io.BytesIO(data))
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    args=parser.parse_args()
    print(prepare(Path(__file__).resolve().parents[1],args.source,args.destination,args.sha256))
