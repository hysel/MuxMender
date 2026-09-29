"""Remove private generated artifacts only after re-verifying a published replacement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import re
from collections import Counter

MEDIA={'.mkv','.mp4','.mov','.avi','.hevc','.h265','.h264','.av1','.obu','.ivf','.yuv','.y4m','.rgb','.raw','.pcm','.wav','.bin','.ac3','.aac','.m4v','.rpu','.mka','.thd','.truehd','.eac3','.dts','.flac'}


def disposable(path):
    return (path.suffix.lower() in MEDIA or path.suffix=='.framehash'
            or path.name.endswith(('-frames.jsonl','-frames.json','-all-packets.txt','-vmaf.json'))
            or re.search(r'-stream-\d+\.txt$',path.name) is not None
            or path.name=='rpu.json' or path.name.endswith('-rpu.json')
            or path.name in ('timestamps.txt','source-rpu-packets.xml')
            or (path.name=='metadata.json' and path.parent.name.endswith('-layers')))


def prune_generated(directory, *, execute=False, guard=lambda:None, keep_paths=()):
    """Caller must establish terminal ownership and protect source/recovery state."""
    safe_path(directory);directory=directory.resolve(strict=True)
    keep=set()
    for path in keep_paths:
        path=Path(path);safe_path(path);path=path.resolve(strict=True)
        if not path.is_file() or not path.is_relative_to(directory):raise ValueError('Retained deliverable outside job directory')
        keep.add(path)
    files=[];links=Counter()
    from artifact_manifest import registered_outputs
    registered=registered_outputs(directory)
    for path in directory.rglob('*'):
        if not disposable(path) and path not in registered:continue
        safe_path(path)
        if not path.is_file() or not path.resolve().is_relative_to(directory):continue
        s=path.stat();files.append((path,identity(path),s.st_nlink));links[(s.st_dev,s.st_ino)]+=1
    # Internal hardlinks are disposable only if every link is in this manifest.
    files=[x for x in files if links[x[1][:2]]==x[2] and x[0].resolve() not in keep]
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


def cleanup_finished(directory, *, execute=False):
    """Shared post-task policy. Call only after the owned media processes exit."""
    directory=Path(directory).absolute();safe_path(directory);directory=directory.resolve(strict=True)
    status_path=directory/'status.json';safe_path(status_path)
    status=json.loads(status_path.read_text());state=status.get('state')
    if state in ('stopped-original-retained','full-output-rejected-insufficient-savings') and not status.get('research_only'):
        return cleanup_terminal(directory,execute=execute)
    if state=='trials-completed' and status.get('decision',{}).get('action')=='keep_original':
        return cleanup_terminal(directory,execute=execute)
    research=status.get('research_only') is True and state in (
        'research-completed-not-approved','research-stopped-not-approved','stopped-original-retained')
    sample_success=state=='trials-completed' and status.get('decision',{}).get('action')=='encode_copy'
    if not (state=='validated-copy-awaiting-playback' or research or sample_success):
        raise ValueError('No terminal deliverable policy for this run; files retained')
    if status.get('original_retained') is not True:raise ValueError('Original retention not confirmed')
    if any(directory.rglob('replacement.json')) or any(directory.rglob('replacement-journal.jsonl')):
        raise ValueError('Publication/recovery requires separate verified cleanup')
    source=Path(status['source']);safe_path(source);source=source.resolve(strict=True)
    if not source.is_file() or source.is_relative_to(directory):raise ValueError('Source must exist outside work directory')
    source_stamp=identity(source);status_stamp=identity(status_path)
    keep=[]
    if sample_success:
        report_path=directory/'trials.json';safe_path(report_path)
        report=json.loads(report_path.read_text())
        chosen=status['decision'].get('selected',{}).get('id')
        trials=[t for t in report.get('trials',[]) if t.get('id')==chosen]
        if len(trials)!=1 or not trials[0].get('samples'):raise ValueError('Missing selected sample deliverables')
        for sample in trials[0]['samples']:
            if not sample.get('output'):raise ValueError('Older sample record lacks output paths; retained for review')
            keep.append(Path(sample['output']))
        for ref in report.get('references',[]):
            if ref.get('path'):
                p=Path(ref['path']);safe_path(p)
                if p.resolve(strict=True).is_relative_to(directory):keep.append(p)
    else:
        output=status.get('candidate') if research else status.get('output')
        if not output:raise ValueError('Missing final deliverable path')
        p=Path(output);safe_path(p)
        if not p.resolve().is_relative_to(directory):raise ValueError('Deliverable outside job directory')
        if p.exists():keep.append(p)
        elif not research:raise ValueError('Final deliverable missing')
    keep_stamps={p:identity(p) for p in keep}
    def guard():
        if identity(source)!=source_stamp or identity(status_path)!=status_stamp:raise ValueError('Source or status changed')
        if any(identity(p)!=s for p,s in keep_stamps.items()):raise ValueError('Deliverable changed')
    return prune_generated(directory,execute=execute,guard=guard,keep_paths=keep)


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
