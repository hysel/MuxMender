"""Remove private generated artifacts only after re-verifying a published replacement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

MEDIA={'.mkv','.mp4','.avi','.hevc','.h264','.ivf','.yuv','.wav','.bin'}


def identity(path):
    s=path.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)


def safe_path(path):
    for part in (path,*path.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():
            raise ValueError('Cleanup does not follow linked paths')


def checksum(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def cleanup_replaced(directory, *, execute=False, media_root=None):
    directory=Path(directory).absolute();safe_path(directory)
    directory=directory.resolve(strict=True)
    receipt=json.loads((directory/'replacement.json').read_text())
    status=json.loads((directory/'status.json').read_text())
    if receipt.get('state')!='replaced' or status.get('state')!='validated-copy-awaiting-playback':
        raise ValueError('A confirmed validated replacement receipt is required')
    if status.get('source')!=receipt.get('source') or status.get('output_sha256')!=receipt.get('output_sha256'):
        raise ValueError('Replacement and validation records disagree')
    source=Path(receipt['source'])
    if media_root is not None:source=Path(media_root)/source.relative_to('/media')
    if source.absolute().is_relative_to(directory):
        raise ValueError('Source media cannot be inside the cleanup directory')
    target=Path(receipt['target'])
    if media_root is not None:
        target=Path(media_root)/target.relative_to('/media')
    safe_path(target);target=target.resolve(strict=True)
    if target.is_relative_to(directory) or directory.is_relative_to(target.parent):
        raise ValueError('Generated work and published media must be separate')
    stamp=identity(target)
    if stamp[2]!=receipt['output_bytes'] or checksum(target)!=receipt['output_sha256'] or identity(target)!=stamp:
        raise ValueError('Published replacement no longer matches receipt; nothing cleaned')
    # Never remove source-side recovery files, even if the receipt says complete.
    for key in ('backup','stage'):
        marker=Path(receipt[key])
        if media_root is not None:marker=Path(media_root)/marker.relative_to('/media')
        if marker.exists() or marker.is_symlink():raise ValueError('Recovery files still exist')
    files=[]
    for path in directory.rglob('*'):
        if not (path.suffix.lower() in MEDIA or path.name.endswith('-frames.jsonl')):continue
        safe_path(path)
        if not path.is_file() or not path.resolve().is_relative_to(directory):continue
        if path.stat().st_nlink!=1:continue  # Never unlink shared source/recovery inodes.
        files.append((path,identity(path)))
    report=dict(state='preview',at=time.time(),target=str(target),files=len(files),
                bytes=sum(s[2] for _,s in files),removed=[],retained='JSON receipts, history, quality summaries and logs')
    if not execute:return report
    journal=directory/'artifact-cleanup.jsonl'
    safe_path(journal)
    with journal.open('a',encoding='utf-8') as log:
        try:
            for path,expected in files:
                if identity(target)!=stamp:raise ValueError('Published target changed during cleanup')
                safe_path(path)
                if identity(path)!=expected or path.stat().st_nlink!=1:
                    raise ValueError('Generated artifact changed during cleanup')
                log.write(json.dumps(dict(action='remove',path=str(path),bytes=expected[2],at=time.time()))+'\n')
                log.flush();os.fsync(log.fileno())
                path.unlink()
                report['removed'].append(str(path))
            report['state']='cleaned'
        finally:
            log.write(json.dumps(report)+'\n');log.flush();os.fsync(log.fileno())
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--media-root',type=Path,help='Host path corresponding to container /media')
    args=parser.parse_args()
    print(json.dumps(cleanup_replaced(args.directory,execute=args.execute,media_root=args.media_root),indent=2))
