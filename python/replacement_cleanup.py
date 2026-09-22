"""Remove private generated artifacts only after re-verifying a published replacement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import re
from collections import Counter

MEDIA={'.mkv','.mp4','.avi','.hevc','.h264','.ivf','.yuv','.wav','.bin','.ac3','.m4v'}


def disposable(path):
    return (path.suffix.lower() in MEDIA or path.suffix=='.framehash'
            or path.name.endswith(('-frames.jsonl','-frames.json','-all-packets.txt','-vmaf.json'))
            or re.search(r'-stream-\d+\.txt$',path.name) is not None)


def prune_generated(directory, *, execute=False, guard=lambda:None):
    """Caller must establish terminal ownership and protect source/recovery state."""
    safe_path(directory);directory=directory.resolve(strict=True)
    files=[];links=Counter()
    for path in directory.rglob('*'):
        if not disposable(path):continue
        safe_path(path)
        if not path.is_file() or not path.resolve().is_relative_to(directory):continue
        s=path.stat();files.append((path,identity(path),s.st_nlink));links[(s.st_dev,s.st_ino)]+=1
    # Internal hardlinks are disposable only if every link is in this manifest.
    files=[x for x in files if links[x[1][:2]]==x[2]]
    report=dict(state='preview',at=time.time(),files=len(files),bytes=sum(s[2] for _,s,_ in files),
                removed=[],retained='Receipts, history, quality summaries, errors and logs')
    if not execute:return report
    journal=directory/'artifact-cleanup.jsonl';safe_path(journal);removed=Counter()
    with journal.open('a',encoding='utf-8') as log:
        try:
            for path,expected,nlink in files:
                guard();safe_path(path);s=path.stat()
                if identity(path)!=expected or s.st_nlink!=nlink-removed[expected[:2]]:
                    raise ValueError('Generated artifact changed during cleanup')
                log.write(json.dumps(dict(action='remove',path=str(path),bytes=expected[2],at=time.time()))+'\n')
                log.flush();os.fsync(log.fileno());path.unlink();removed[expected[:2]]+=1
                report['removed'].append(str(path))
            report['state']='cleaned'
        finally:
            log.write(json.dumps(report)+'\n');log.flush();os.fsync(log.fileno())
    return report


def cleanup_terminal(directory, *, execute=False, media_root=None, guard=lambda:None):
    directory=Path(directory).absolute();safe_path(directory);directory=directory.resolve(strict=True)
    status_path=directory/'status.json';safe_path(status_path)
    status=json.loads(status_path.read_text());state=status.get('state')
    allowed=state in ('stopped-original-retained','full-output-rejected-insufficient-savings')
    allowed=allowed or (state=='trials-completed' and status.get('decision',{}).get('action')=='keep_original')
    if not allowed or status.get('original_retained') is not True:
        raise ValueError('Cleanup requires a terminal rejected/failed run with its original retained')
    if any(directory.rglob('replacement.json')) or any(directory.rglob('replacement-journal.jsonl')):
        raise ValueError('Publication/recovery evidence needs separate verified cleanup')
    source=Path(status['source'])
    if media_root is not None:source=Path(media_root)/source.relative_to('/media')
    safe_path(source);source=source.resolve(strict=True)
    if not source.is_file() or source.is_relative_to(directory):raise ValueError('Source must exist outside the cleanup directory')
    stamp=identity(source);record=identity(status_path)
    def protected():
        guard()
        if identity(source)!=stamp or identity(status_path)!=record:raise ValueError('Source or terminal status changed during cleanup')
    return prune_generated(directory,execute=execute,guard=protected)


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
    def protected():
        if identity(target)!=stamp:raise ValueError('Published target changed during cleanup')
        for key in ('backup','stage'):
            marker=Path(receipt[key])
            if media_root is not None:marker=Path(media_root)/marker.relative_to('/media')
            if marker.exists() or marker.is_symlink():raise ValueError('Recovery files appeared during cleanup')
    report=prune_generated(directory,execute=execute,guard=protected)
    report['target']=str(target)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--media-root',type=Path,help='Host path corresponding to container /media')
    args=parser.parse_args()
    print(json.dumps(cleanup_replaced(args.directory,execute=args.execute,media_root=args.media_root),indent=2))
