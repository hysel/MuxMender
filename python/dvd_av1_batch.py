"""Opt-in DVD MPEG-2 to AMD AV1, copy-only and dry-run by default."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
import uuid
from fractions import Fraction
from pathlib import Path

from amd_av1_batch import disjoint, fingerprint
from encoder_capabilities import probe_encoder
from job_tracking import tracked_call, progress
from mux_integrity import verify_av1_display_geometry
from native_pipeline import stage


def probe(path, ffprobe):
    return json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_streams',
        '-show_chapters', '-show_format', '-of', 'json', str(path)], text=True, timeout=60))


def eligibility(data):
    videos = [s for s in data['streams'] if s['codec_type'] == 'video']
    if len(videos) != 1:
        return 'Requires exactly one video track'
    v = videos[0]
    if (v.get('codec_name'), v.get('width'), v.get('height'), v.get('pix_fmt'),
        v.get('sample_aspect_ratio'), v.get('field_order')) != ('mpeg2video',720,480,'yuv420p','8:9','tt'):
        return 'Outside tested NTSC DVD profile; HEVC/AV1 and other formats are not re-encoded'
    if v.get('avg_frame_rate') != '30000/1001':
        return 'Requires 29.97 interlaced input'
    if any(s.get('side_data_type') != 'CPB properties' for s in v.get('side_data_list', [])):
        return 'Unexpected video side data; Dolby Vision/HDR/rotation requires separate flow'
    if float(data['format']['duration']) <= 0:
        return 'Invalid duration'
    return None


def save(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(path)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(8*1024**2):
            value.update(chunk)
    return value.hexdigest()


def command(ffmpeg, source, output):
    return [ffmpeg, '-hide_banner', '-nostdin', '-n', '-v', 'warning', '-i', str(source),
            '-map', '0', '-map_metadata', '0', '-map_chapters', '0', '-c', 'copy',
            '-vf', 'bwdif=mode=send_field:parity=auto:deint=all,format=nv12',
            '-c:v', 'av1_amf', '-quality', 'quality', '-rc', 'cqp', '-qp_i', '80', '-qp_p', '80',
            '-progress', 'pipe:1', '-nostats', str(output)]


def packet_hashes(path, selector, ffprobe, timeout):
    raw = subprocess.check_output([ffprobe,'-v','error','-select_streams',selector,
        '-show_packets','-show_data_hash','sha256','-show_entries','packet=data_hash',
        '-of','json',str(path)],text=True,timeout=timeout)
    packets = json.loads(raw).get('packets', [])
    if any('data_hash' not in p for p in packets):
        raise ValueError('Missing copied-packet hash evidence')
    return [p['data_hash'] for p in packets]


def validate(source_data, output, ffmpeg, ffprobe, timeout):
    actual = probe(output, ffprobe)
    old = source_data['streams']; new = actual['streams']
    if len(old) != len(new):
        raise ValueError('Track count changed')
    for a, b in zip(old, new):
        if a['codec_type'] != b['codec_type']:
            raise ValueError('Track order changed')
        if a['codec_type'] != 'video' and a['codec_name'] != b['codec_name']:
            raise ValueError('Copied codec changed')
        if a.get('disposition') != b.get('disposition'):
            raise ValueError('Track dispositions changed')
        for tag in ('language', 'title'):
            if a.get('tags', {}).get(tag) != b.get('tags', {}).get(tag):
                raise ValueError('Track metadata changed')
    if abs(float(actual['format']['duration']) - float(source_data['format']['duration'])) > 1:
        raise ValueError('Duration changed')
    if source_data.get('chapters', []) != actual.get('chapters', []):
        raise ValueError('Chapter metadata changed')
    original = next(s for s in old if s['codec_type'] == 'video')
    encoded = next(s for s in new if s['codec_type'] == 'video')
    clean = {k:original[k] for k in ('width', 'height', 'sample_aspect_ratio')}
    # All decoded frames are observed, without retaining large per-frame logs.
    frames = 0
    def observe(line):
        nonlocal frames
        match = re.search(r' sar:(\S+) s:(\d+)x(\d+)', line)
        if match:
            sar, w, h = match.groups()
            if Fraction(sar.replace(':','/')) != Fraction(8,9):
                raise ValueError('Decoded pixel aspect ratio changed')
            verify_av1_display_geometry(clean, encoded, [(int(w),int(h))])
            frames += 1
        return 'showinfo' in line
    stage([ffmpeg,'-hide_banner','-nostdin','-v','info','-xerror','-i',str(output),
           '-map','0:v:0','-map','0:a?','-vf','showinfo','-progress','pipe:1','-nostats','-f','null','-'],
          float(actual['format']['duration']),70,30, timeout=timeout, stall=120, observe=observe)
    if frames == 0:
        raise ValueError('No decoded frame evidence')
    return dict(frames_checked=frames, geometry=verify_av1_display_geometry(clean, encoded, [(720,480)]),
                playback_review_required=True)


def run(args):
    source, root = disjoint(args.source, args.output_dir)
    paths = sorted(source.rglob('*.mkv')) if source.is_dir() else [source]
    plan = []
    for path in paths:
        if path.is_symlink():
            raise ValueError('Symlink source requires explicit review')
        before = fingerprint(path)
        data = probe(path, args.ffprobe)
        reason = eligibility(data)
        if fingerprint(path) != before:
            raise ValueError('Source changed during scan')
        plan.append(dict(source=str(path), fingerprint=before, action='skip' if reason else 'encode', reason=reason))
    if not args.execute:
        print(json.dumps(dict(dry_run=True, plan=plan, original_deletion=False), indent=2))
        return 0
    if not args.accept_deinterlace:
        raise ValueError('Execution requires --accept-deinterlace (29.97i to 59.94p; no resize)')
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root/('dvd-av1-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    run_dir.mkdir()
    save(run_dir/'plan.json', plan)
    capability = probe_encoder(args.ffmpeg, 'av1_amf')
    save(run_dir/'hardware.json', capability)
    if capability['status'] != 'working':
        raise RuntimeError('AMD AV1 runtime unavailable: '+capability['detail']+'; no automatic CPU fallback')
    errors = 0
    for index, row in enumerate(plan):
        if row['action'] == 'skip': continue
        path = Path(row['source'])
        target = root/path.relative_to(source if source.is_dir() else source.parent)
        target = target.with_name(target.stem+'.AV1.mkv')
        if not target.resolve().is_relative_to(root):
            raise ValueError('Output path escapes output root through a link')
        receipt = target.with_suffix('.receipt.json')
        progress('DVD AV1 '+path.name,index,len(plan),unit='files',directory=run_dir)
        try:
            if target.exists():
                previous = json.loads(receipt.read_text()) if receipt.exists() else {}
                if previous.get('source') == str(path) and previous.get('source_sha256') == digest(path) and previous.get('output_sha256') == digest(target):
                    row['state']='resumed-verified'; continue
                raise ValueError('Existing output not verified for this source; never overwrite')
            if shutil.disk_usage(root).free < max(args.min_free_gib*1024**3, path.stat().st_size*2):
                raise RuntimeError('Insufficient output disk space')
            before = fingerprint(path); source_hash = digest(path)
            if before != row['fingerprint']: raise ValueError('Source changed since plan')
            data = probe(path,args.ffprobe)
            partial = run_dir/(str(index)+'.partial.mkv')
            stage(command(args.ffmpeg,path,partial),float(data['format']['duration']),
                  0,70,timeout=args.timeout,stall=120)
            checks = validate(data,partial,args.ffmpeg,args.ffprobe,args.timeout)
            for selector in ('a','s'):
                if packet_hashes(path,selector,args.ffprobe,args.timeout) != packet_hashes(partial,selector,args.ffprobe,args.timeout):
                    raise ValueError('Copied audio/subtitle packet payload changed')
            checks['copied_packet_hashes_verified'] = True
            if fingerprint(path)!=before or digest(path)!=source_hash:
                raise ValueError('Source changed; output not published')
            if partial.stat().st_size >= path.stat().st_size:
                raise ValueError('No disk savings; candidate retained, not published')
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.resolve().is_relative_to(root):
                raise ValueError('Output path changed during conversion')
            # Exclusive copy prevents an output created concurrently being overwritten.
            with partial.open('rb') as src,target.open('xb') as dst:
                shutil.copyfileobj(src,dst,8*1024**2)
            output_hash=digest(partial)
            if digest(target)!=output_hash: raise ValueError('Publication checksum mismatch')
            save(receipt,dict(source=str(path),source_sha256=source_hash,output_sha256=output_hash,
                              validation=checks,saved_percent=100*(1-target.stat().st_size/path.stat().st_size)))
            partial.unlink()  # Owned generated intermediate only; source never deleted.
            row.update(state='verified-awaiting-playback',output=str(target))
        except Exception as exc:
            errors += 1; row.update(state='failed-original-retained',error=str(exc))
        finally:
            save(run_dir/'status.json',plan)
    progress('DVD batch finished',len(plan),len(plan),unit='files',directory=run_dir)
    return 1 if errors else 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--accept-deinterlace',action='store_true')
    parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--timeout',type=float,default=7200)
    parser.add_argument('--min-free-gib',type=float,default=8)
    args=parser.parse_args(argv)
    if not 0 < args.timeout <= 86400 or not 1 <= args.min_free_gib < 100000:
        parser.error('Invalid timeout or free-space threshold')
    return tracked_call(lambda:run(args),'DVD AMD AV1 batch') if args.execute else run(args)


if __name__=='__main__':raise SystemExit(main())
