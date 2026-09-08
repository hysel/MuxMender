"""Library inventory and explicit preview-first cleanup; no encoders."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
import re
import subprocess
from pathlib import Path
import time
import uuid
import muxmender as mm


def cleanup_reason(path, root, primary, samples=False):
    """Names nominate candidates only; subtitles and the chosen main video stay."""
    if os.path.samefile(path, primary):
        return None
    if path.suffix.lower() == '.nfo':
        return 'NFO metadata file; review before permanent deletion'
    if samples and path.suffix.lower() in mm.MEDIA_EXTENSIONS:
        folders = path.relative_to(root).parts[:-1]
        if any(part.casefold() in ('sample','samples') for part in folders) or re.search(r'(?i)(?:^|[._ -])sample$', path.stem):
            return 'Explicit sample folder/name; not inferred from duration; review identity'
    return None


def create_cleanup_plan(video, samples=False):
    primary = Path(os.path.abspath(video))
    mm.check_rename_path(primary)
    if not primary.is_file() or primary.suffix.lower() not in mm.MEDIA_EXTENSIONS:
        raise ValueError('Cleanup planning requires the main video file to protect')
    root = primary.parent
    entries = []
    def linked(path):
        return path.is_symlink() or bool(getattr(path.lstat(),'st_file_attributes',0) & 0x400)
    def error(exc):
        raise exc
    for parent, folders, names in os.walk(root, followlinks=False, onerror=error):
        folders[:] = sorted(name for name in folders if not name.startswith('.') and not linked(Path(parent)/name))
        for name in sorted(names):
            path = Path(parent)/name
            if linked(path) or not path.is_file():
                continue
            reason = cleanup_reason(path, root, primary, samples)
            if reason:
                entries.append(dict(source=str(path), identity=mm.rename_identity(path), status='ready', reason=reason))
    return dict(schema='muxmender-cleanup-v1', root=str(root), samples=bool(samples),
                primary_video=dict(path=str(primary), identity=mm.rename_identity(primary)), entries=entries,
                bytes_nominated=sum(e['identity']['size'] for e in entries),
                note='Preview only. Review every candidate. Explicit apply permanently deletes selected ready files, never directories. All subtitles and ordinary main-video names are excluded.')


def apply_cleanup_plan(plan_path):
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if plan.get('schema') != 'muxmender-cleanup-v1' or type(plan.get('samples')) is not bool:
        raise ValueError('Unsupported cleanup plan')
    root, primary = Path(plan['root']), Path(plan['primary_video']['path'])
    if not root.is_absolute() or not primary.is_absolute() or primary.parent != root or primary.suffix.lower() not in mm.MEDIA_EXTENSIONS:
        raise ValueError('Cleanup requires an absolute root containing the protected main video')
    def check_primary():
        mm.check_rename_path(primary)
        if not primary.is_file() or mm.rename_identity(primary) != plan['primary_video']['identity']:
            raise ValueError('Protected main video changed since preview')
    check_primary()
    ready = [entry for entry in plan['entries'] if entry['status'] == 'ready']
    seen = set()
    def check(entry):
        path = Path(entry['source'])
        if not path.is_absolute():
            raise ValueError('Cleanup paths must be absolute')
        mm.check_rename_path(path)
        path.resolve().relative_to(root.resolve())
        if not path.is_file() or mm.rename_identity(path) != entry['identity']:
            raise ValueError('Cleanup candidate changed since preview: '+str(path))
        if not cleanup_reason(path, root, primary, plan['samples']):
            raise ValueError('Cleanup candidate is protected or outside the allowed file types')
        return path
    # Complete the entire validation pass before the first deletion.
    for entry in ready:
        path = check(entry)
        key = str(path.resolve()).casefold()
        if key in seen:
            raise ValueError('Duplicate cleanup entry')
        seen.add(key)
    journal = plan_path.with_name(plan_path.stem+'.cleanup-'+uuid.uuid4().hex[:8]+'.jsonl')
    with journal.open('x',encoding='utf-8') as log:
        for entry in ready:
            path = Path(entry['source'])
            try:
                check_primary()
                path = check(entry)
                log.write(json.dumps(dict(status='starting',source=str(path),identity=entry['identity']))+'\n')
                log.flush(); os.fsync(log.fileno())
                path.unlink()
            except (OSError,ValueError) as exc:
                log.write(json.dumps(dict(status='failed',source=str(path),error=str(exc)))+'\n')
                log.flush(); os.fsync(log.fileno())
                raise RuntimeError(f'Cleanup stopped; earlier deletions remain recorded in {journal}: {exc}') from exc
            log.write(json.dumps(dict(status='deleted',source=str(path)))+'\n')
            log.flush(); os.fsync(log.fileno())
    return len(ready), journal


def probe_with_frame_color(path,ffprobe):
    info=mm.probe(path,ffprobe)
    fields=('color_primaries','color_transfer','color_space','color_range')
    missing=[key for key in fields if getattr(info,key) in ('unknown','unspecified','',None)]
    if missing:
        data=mm.run_json([ffprobe,'-v','error','-select_streams','v:0','-read_intervals','%+#8',
            '-show_frames','-show_entries','frame='+','.join(fields),'-of','json',str(path)])
        frames=data.get('frames',[])
        for key in missing:
            values={f.get(key,'unknown') for f in frames}
            if len(frames)>=2 and len(values)==1 and not values.intersection({'unknown','unspecified','',None}):
                setattr(info,key,next(iter(values)))
        info.hdr=info.hdr or info.color_transfer in mm.KNOWN_HDR_TRANSFERS
    return info


def classify(info):
    """Recommendations are candidates, never promises of savings or compatibility."""
    if info.dolby_vision:
        route = mm.assess_dolby_preservation(info)['route']
        if route == 'profile8.1-research-candidate':
            return 'specialized-dv', 'Profile 8.1 candidate for the experimental AMD preservation CLI; not the ordinary Web UI encoder'
        return 'needs-review', 'Unsupported Dolby Vision preservation path: ' + route
    unknown = [k for k in ('color_primaries','color_transfer','color_space','color_range')
               if getattr(info,k) in (None,'','unknown','unspecified','reserved')]
    if unknown:
        return 'needs-review', 'Unspecified ' + ', '.join(unknown) + '; color is not guessed'
    if info.hdr:
        return 'needs-review', 'HDR static/dynamic metadata needs a separately validated preservation route'
    if info.width <= 0 or info.height <= 0 or info.bit_depth not in (8,10):
        return 'needs-review', 'Unsupported dimensions or bit depth'
    if info.video_codec in ('hevc','av1'):
        return 'keep-as-is', 'Efficient codec already present; no savings assumed'
    if info.video_codec == 'h264':
        return 'preview-candidate', 'Test SDR HEVC/AV1 at original resolution; preflight and playback review required'
    return 'needs-review', 'Legacy or unvalidated codec/timing route; original unchanged'


def enumerate_media(source, excluded=(), guard=lambda:None):
    source = Path(source).resolve(strict=True)
    def blocked(path):
        resolved = path.resolve()
        return any(resolved == root or root in resolved.parents for root in excluded)
    if source.is_file():
        if source.suffix.lower() not in mm.MEDIA_EXTENSIONS or blocked(source):
            raise ValueError('Not an eligible media file')
        return [source]
    files=[]
    def error(exc):
        raise exc  # Never silently report a complete scan after an inaccessible folder.
    for parent, children, names in os.walk(source,onerror=error,followlinks=False):
        guard()
        children[:] = sorted(name for name in children if not (Path(parent)/name).is_symlink()
                             and not getattr(Path(parent)/name,'is_junction',lambda:False)()
                             and not blocked(Path(parent)/name))
        for name in sorted(names):
            path=Path(parent)/name
            if path.suffix.lower() in mm.MEDIA_EXTENSIONS and not path.is_symlink() and not blocked(path):
                if '.partial' not in name.lower() and '.muxmender' not in name.lower():
                    files.append(path)
    return files


def scan(source, directory, ffprobe='ffprobe', guard=lambda:None, update=lambda *a:None, excluded=()):
    directory=Path(directory)
    paths=enumerate_media(source,tuple(Path(p).resolve() for p in excluded),guard)
    counts=Counter(); codecs=Counter(); total=0
    update('Read-only scan',0)
    print(f'Found {len(paths)} media files; metadata only',flush=True)
    with (directory/'files.jsonl').open('x',encoding='utf-8') as output:
        for index,path in enumerate(paths):
            guard()
            try:
                before=path.stat(); info=probe_with_frame_color(path,ffprobe); after=path.stat()
                row=asdict(info)
                row['fingerprint']={'size':before.st_size,'mtime_ns':before.st_mtime_ns}
                row['color_check']='Missing stream fields may be recovered from consistent explicit tags on the first eight decoded frames; no inferred defaults'
                row['action'],row['reason']=classify(info)
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                    row.update(action='needs-review',reason='Source changed externally during scan')
                total+=info.size_bytes; codecs[info.video_codec]+=1
            except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as exc:
                row={'path':str(path),'action':'probe-error','reason':str(exc)}
            row.update(id=index,savings_estimate=None)
            output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush()
            counts[row['action']]+=1
            print(f"[{index+1}/{len(paths)}] {row['action']}: {path}",flush=True)
            update('Read-only scan',100*(index+1)/max(1,len(paths)))
    result=dict(status='scan-complete',source=str(source),files=len(paths),actions=dict(counts),
                codecs=dict(codecs),size_bytes=total,savings_estimate=None)
    with (directory/'summary.json').open('x',encoding='utf-8') as out: json.dump(result,out,indent=2)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--reports',type=Path,default=Path(__file__).resolve().parent.parent/'reports')
    args=parser.parse_args()
    from job_tracking import tracked_call,phase
    from runtime_support import TerminalProgress
    def work():
        directory=args.reports/('scan-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        directory.mkdir(parents=True,exist_ok=False)
        bar=TerminalProgress('Read-only library scan')
        def update(label,percent):
            phase(directory,label,percent);bar.update(percent)
        result=scan(args.source,directory,args.ffprobe,update=update,excluded=(args.reports,))
        print(f'REPORT: {directory / "summary.json"}',flush=True)
        return int(bool(result['actions'].get('probe-error')))
    return tracked_call(work,'Read-only library scan',args.reports)


if __name__=='__main__': raise SystemExit(main())
