"""Explicitly selected, journaled replacement of a fully validated MKV output."""
import json
import math
import os
import re
import shutil
import time
from pathlib import Path
from autonomous_queue import write
from task_progress import digest
from job_tracking import progress, workflow_stage


def target_for(source, media, writable):
    if writable is None:raise ValueError('Replacement is not enabled in app settings')
    source=Path(source);media=Path(media);writable=Path(writable)
    relative=source.relative_to(media)
    target=writable/relative
    for root,path in ((media,source),(writable,target)):
        if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
            raise ValueError('Replacement path escapes media mount')
        cursor=path
        while cursor!=root:
            if cursor.is_symlink():raise ValueError('Symlinks cannot be replaced')
            cursor=cursor.parent
    if not os.path.samefile(source,target):raise ValueError('Writable mount must expose the exact same source files as the read-only mount')
    return target


class DestinationConflict(ValueError):
    pass


from media_naming import readable_destination


def destination_for(original):
    destination=readable_destination(original)
    if destination!=original and any(p.name.casefold()==destination.name.casefold() for p in original.parent.iterdir()):
        raise DestinationConflict('Original kept: destination filename already exists: '+destination.name)
    return destination


def replace_validated(source, media, writable, result_dir, minimum_savings, job_id, stopped=lambda:False):
    workflow_stage('publish')
    if not math.isfinite(minimum_savings) or not 0<=minimum_savings<100:
        raise ValueError('Replacement savings threshold must be finite and in [0,100)')
    if not isinstance(job_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',job_id):
        raise ValueError('Invalid publication job identifier')
    result_dir=Path(result_dir).resolve(strict=True)
    status=json.loads((result_dir/'status.json').read_text())
    plan_path=result_dir/'plan.json'
    if plan_path.exists() and (json.loads(plan_path.read_text()).get('color_inspection') or {}).get('assumed'):
        raise ValueError('Assumed color cannot authorize source replacement')
    selection=json.loads((result_dir/'selection.json').read_text())
    if status.get('state')!='validated-copy-awaiting-playback' or status.get('source')!=str(source):
        raise ValueError('Full-file validation required before replacement')
    chosen=selection.get('selected') or {}
    if selection.get('action')!='encode_copy' or not any(c.get('id')==chosen.get('id') and c.get('rejected_reasons')==[] for c in selection.get('candidates',[])):
        raise ValueError('Selected candidate did not pass quality checks')
    output=Path(status['output'])
    if output.is_symlink() or output.resolve(strict=True).parent!=result_dir or output.suffix!='.mkv':
        raise ValueError('Invalid validated output path')
    original=target_for(source,media,writable)
    target=destination_for(original)
    before=original.stat()
    if before.st_size<=0 or output.stat().st_size<=0:
        raise ValueError('Empty source/output cannot be published')
    saving=100*(1-output.stat().st_size/before.st_size)
    if output.stat().st_size>=before.st_size or saving<minimum_savings:raise ValueError('Full output does not meet minimum savings')
    if digest(original)!=status.get('source_sha256') or digest(output)!=status.get('output_sha256'):
        raise ValueError('Source or output changed since validation')
    if stopped():raise RuntimeError('Replacement cancelled before publication')
    if shutil.disk_usage(target.parent).free<output.stat().st_size+1024**3:
        raise ValueError('Insufficient media storage for a verified staged copy')
    # Same-directory hard link preserves the original across an atomic replace.
    stage=target.with_name(target.name+'.muxmender-'+job_id+'.staging')
    backup=original.with_name(original.name+'.muxmender-'+job_id+'.original')
    if stage.exists() or backup.exists():raise ValueError('Prior replacement files require manual recovery; refusing to overwrite')
    journal=result_dir/'replacement.json'
    record=dict(state='staging',source=str(source),target=str(target),backup=str(backup),stage=str(stage),
                source_sha256=status['source_sha256'],output_sha256=status['output_sha256'],original_bytes=before.st_size,output_bytes=output.stat().st_size,saved_bytes=before.st_size-output.stat().st_size)
    write(journal,record)
    progress('Publishing validated copy',detail='Copying to source storage; original retained')
    copied=0;last=0
    with output.open('rb') as src,stage.open('xb') as dst:
        for block in iter(lambda:src.read(8*1024*1024),b''):
            if stopped():raise RuntimeError('Publication cancelled; original retained')
            dst.write(block);copied+=len(block)
            if time.monotonic()-last>=2:
                progress('Publishing validated copy',stage_percent=100*copied/record['output_bytes'],
                         detail=f'{copied/1e9:.2f} of {record["output_bytes"]/1e9:.2f} GB copied')
                last=time.monotonic()
        progress('Flushing published copy to storage',detail='Waiting for storage synchronization; original retained')
        dst.flush();os.fsync(dst.fileno())
    shutil.copystat(original,stage)
    if digest(stage)!=status['output_sha256']:raise ValueError('Staged copy failed verification; original retained')
    target_for(source,media,writable)
    if digest(original)!=status['source_sha256'] or stopped():raise ValueError('Source changed or shutdown requested; original retained')
    if destination_for(original)!=target:
        raise DestinationConflict('Folder contents changed during encoding/publication; original retained')
    record['state']='ready';write(journal,record)
    os.link(original,backup)  # Exclusive creation; unsupported hard links fail safely.
    if target==original:
        os.replace(stage,target)
    else:
        # Atomic no-clobber publication: never overwrite a destination created meanwhile.
        try:os.link(stage,target)
        except FileExistsError as exc:raise DestinationConflict('Destination appeared during publication; original retained') from exc
        stage.unlink()
    record['state']='published-verifying';write(journal,record)
    if digest(target)!=status['output_sha256']:
        raise ValueError('Published verification failed; original backup retained for recovery')
    # Flush directory operations before removing the last original link.
    if os.name=='posix':
        fd=os.open(target.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    if target!=original:
        if digest(original)!=status['source_sha256']:raise ValueError('Original changed after publication; original and recovery backup retained')
        original.unlink()
    backup.unlink()
    record['state']='replaced';write(journal,record)
    # Cleanup failure must not relabel a successfully published replacement as a
    # failed encode or invite a duplicate replacement. Preserve a retryable note.
    try:
        from replacement_cleanup import cleanup_replaced
        workflow_stage('cleanup')
        progress('Cleaning completed replacement artifacts',detail='Rechecking published file before removing redundant work files')
        record['artifact_cleanup']=cleanup_replaced(result_dir,execute=True)
    except Exception as exc:
        record['artifact_cleanup']=dict(state='needs-attention',error=str(exc))
    write(journal,record)
    return record
