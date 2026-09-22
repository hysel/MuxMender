"""Bounded generated-frame encoder checks; never opens user media."""
import argparse
import json
import subprocess
import csv
import hashlib
import os
from pathlib import Path
import shutil
import time
import uuid


def nvidia_profile(compute_capability):
    """Architecture hints, never permission to skip a real capability test."""
    generation = {'3.0':'Kepler','3.5':'Kepler','3.7':'Kepler',
                  '5.0':'Maxwell','5.2':'Maxwell','5.3':'Maxwell',
                  '6.0':'Pascal','6.1':'Pascal','6.2':'Pascal',
                  '7.0':'Volta','7.5':'Turing','8.0':'Ampere','8.6':'Ampere',
                  '8.9':'Ada','12.0':'Blackwell'}.get(str(compute_capability), 'Unknown')
    modern = generation in ('Ada','Blackwell')
    return dict(generation=generation, codec_order=['av1','hevc'] if modern else ['hevc','av1'],
                advisory=True, note='Generation is a hint; exact model, driver and runtime probe decide availability. No codec is excluded by this profile.')


def nvidia_adapters():
    """Discover visible adapters without assuming host and container indices match."""
    fields='uuid,name,driver_version,memory.total,compute_cap'
    for query in (fields,fields.rsplit(',',1)[0]):
        try:
            raw=subprocess.check_output(['nvidia-smi','--query-gpu='+query,'--format=csv,noheader,nounits'],
                                        text=True,stderr=subprocess.DEVNULL,timeout=5)
            rows=[]
            for row in csv.reader(raw.splitlines(),skipinitialspace=True):
                if len(row) not in (4,5) or not row[0].startswith('GPU-'):
                    continue
                rows.append(dict(uuid=row[0],name=row[1],driver=row[2],memory_mib=row[3],
                                 profile=nvidia_profile(row[4] if len(row)==5 else '')))
            return rows
        except (OSError,subprocess.SubprocessError):
            continue
    return []


def codec_order(vendor, adapters):
    # Multiple GPUs need explicit device routing before using a per-card hint.
    return adapters[0]['profile']['codec_order'] if vendor=='nvidia' and len(adapters)==1 else ['hevc','av1']


def _cache_path(ffmpeg, encoder, width, height, pixel_format, adapters, cache_dir):
    if not cache_dir or not encoder.endswith('_nvenc') or len(adapters)!=1:
        return None
    try:
        executable=Path(shutil.which(str(ffmpeg)) or ffmpeg).resolve(strict=True)
        stat=executable.stat()
        version=subprocess.check_output([str(executable),'-version'],text=True,
                                        stderr=subprocess.STDOUT,timeout=5)
        key=dict(schema=1, executable=str(executable), size=stat.st_size, modified=stat.st_mtime_ns,
                 version=version, adapters=adapters, encoder=encoder,width=width,height=height,pixel_format=pixel_format,
                 visibility={k:os.environ.get(k) for k in ('CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER')})
        return Path(cache_dir)/(hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()+'.json')
    except (OSError,subprocess.SubprocessError):
        return None


def probe_encoder(ffmpeg, encoder, width=720, height=480, ten_bit=False, timeout=30, pixel_format=None,
                  *, adapters=None, cache_dir=None):
    if width <= 0 or height <= 0 or timeout <= 0:
        raise ValueError('Positive dimensions and timeout required')
    pixel_format=pixel_format or ('p010le' if ten_bit else 'nv12')
    allowed={'nv12','p010le','yuv444p16le'}|{f'yuv{c}p{d}' for c in ('420','422','444') for d in ('','10le','12le')}
    if pixel_format not in allowed:raise ValueError('Unsupported probe pixel format')
    adapters = nvidia_adapters() if adapters is None and encoder.endswith('_nvenc') else (adapters or [])
    cache = _cache_path(ffmpeg,encoder,width,height,pixel_format,adapters,cache_dir)
    if cache:
        try:
            entry=json.loads(cache.read_text(encoding='utf-8'))
            if entry['result']['status']=='working' and 0 <= time.time()-entry['checked_at'] < 86400:
                return dict(entry['result'],cached=True,checked_at=entry['checked_at'])
        except (OSError,ValueError,KeyError,TypeError):
            pass
    command = [ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-f', 'lavfi',
               '-i', f'nullsrc=size={width}x{height}:rate=30,format={pixel_format}', '-frames:v', '4',
               '-pix_fmt', pixel_format, '-c:v', encoder,
               '-f', 'null', '-']
    result = dict(encoder=encoder, width=width, height=height, ten_bit=ten_bit,pixel_format=pixel_format,
                  status='unavailable', command=command, adapters=adapters, cached=False,
                  scope='Four synthetic frames; not proof of all formats, GPU adapters, or client playback')
    try:
        process = subprocess.run(command, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=timeout)
        result.update(status='working' if process.returncode == 0 else 'failed',
                      returncode=process.returncode, detail=process.stderr.strip()[-3000:])
    except subprocess.TimeoutExpired:
        result.update(status='timed-out', detail=f'Encoder initialization exceeded {timeout}s')
    except OSError as exc:
        result['detail'] = str(exc)
    if cache and result['status']=='working':
        temporary=cache.with_name(cache.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            cache.parent.mkdir(parents=True,exist_ok=True)
            temporary.write_text(json.dumps(dict(checked_at=time.time(),result=result)),encoding='utf-8')
            os.replace(temporary,cache)
        except OSError:
            pass  # Cache storage failure must never block conversion.
        finally:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
    return result


def inventory(ffmpeg='ffmpeg', execute=False):
    import muxmender as mm
    names = mm.ffmpeg_encoder_names(ffmpeg)
    vendors = mm.gpu_vendors()
    adapters = nvidia_adapters() if 'nvidia' in vendors else []
    rows = []
    for vendor, codecs in mm.HARDWARE_ENCODERS.items():
        for codec, encoder in codecs.items():
            row = dict(vendor=vendor, codec=codec, encoder=encoder,
                       adapter_detected=vendor in vendors, listed=encoder in names,
                       download_url=mm.DOWNLOAD_URLS[vendor], status='not-tested')
            if vendor=='nvidia':row['adapters']=adapters
            if execute and row['adapter_detected'] and row['listed']:
                row.update(probe_encoder(ffmpeg, encoder))
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--execute', action='store_true', help='Initialize detected encoders sequentially with synthetic frames')
    args = parser.parse_args()
    print(json.dumps(inventory(args.ffmpeg, args.execute), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
