"""Bounded generated-frame encoder checks; never opens user media."""
import argparse
import json
import subprocess


def probe_encoder(ffmpeg, encoder, width=720, height=480, ten_bit=False, timeout=30):
    if width <= 0 or height <= 0 or timeout <= 0:
        raise ValueError('Positive dimensions and timeout required')
    command = [ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-f', 'lavfi',
               '-i', f'color=size={width}x{height}:rate=30', '-frames:v', '4',
               '-pix_fmt', 'p010le' if ten_bit else 'nv12', '-c:v', encoder,
               '-f', 'null', '-']
    result = dict(encoder=encoder, width=width, height=height, ten_bit=ten_bit,
                  status='unavailable', command=command,
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
    return result


def inventory(ffmpeg='ffmpeg', execute=False):
    import muxmender as mm
    names = mm.ffmpeg_encoder_names(ffmpeg)
    vendors = mm.gpu_vendors()
    rows = []
    for vendor, codecs in mm.HARDWARE_ENCODERS.items():
        for codec, encoder in codecs.items():
            row = dict(vendor=vendor, codec=codec, encoder=encoder,
                       adapter_detected=vendor in vendors, listed=encoder in names,
                       download_url=mm.DOWNLOAD_URLS[vendor], status='not-tested')
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
