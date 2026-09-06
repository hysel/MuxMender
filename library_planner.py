"""Reusable read-only library inventory. No encoders or media writes."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
import subprocess
from pathlib import Path
import time
import uuid
import muxmender as mm


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
    parser.add_argument('--reports',type=Path,default=Path(__file__).resolve().parent/'reports')
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
