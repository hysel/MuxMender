"""Exercise the real shared NVIDIA workflow with generated SDR media only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffprobe', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--minimum-savings-percent', type=float, default=25)
    parser.add_argument('--engine', type=Path, default=Path(__file__).resolve().parents[1] / 'python' / 'auto_optimize.py')
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    inputs = root / 'input'
    inputs.mkdir()
    source = inputs / 'generated-source.mkv'
    started = time.time()
    subprocess.run([args.ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-n',
        '-f', 'lavfi', '-i', 'testsrc2=size=1920x1080:rate=24:duration=12',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=12',
        '-vf', 'setfield=prog', '-c:v', 'libx264', '-preset', 'ultrafast',
        '-crf', '0', '-threads', '2', '-g', '24', '-pix_fmt', 'yuv420p',
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
        '-color_range', 'tv', '-c:a', 'ac3', str(source)], check=True, timeout=180)
    before = digest(source)
    engine = args.engine
    command = [sys.executable, '-u', '-B', str(engine), str(source),
        '--output-dir', str(root / 'output'), '--execute', '--encode-best',
        '--hardware', 'nvidia', '--playback-verified-codecs', 'hevc', 'av1',
        '--qualities', 'balanced', '--seconds', '2', '--vmaf-mean', '90',
        '--vmaf-p5', '90', '--minimum-savings-percent', str(args.minimum_savings_percent), '--min-free-gib', '2',
        '--timeout', '900', '--ffmpeg', args.ffmpeg, '--ffprobe', args.ffprobe]
    with (root / 'workflow.log').open('x') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, timeout=1800)
    states = [json.loads(p.read_text()) for p in (root / 'output').glob('auto-*/status.json')]
    summary = dict(exit_code=result.returncode, source_unchanged=digest(source)==before,
        seconds=round(time.time()-started, 3), source_bytes=source.stat().st_size,
        states=states, scope='Generated SDR end-to-end check, not real-library or HDR qualification')
    (root / 'report.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    return 0 if result.returncode == 0 and summary['source_unchanged'] and any(
        s.get('state') == 'validated-copy-awaiting-playback' for s in states) else 1


if __name__ == '__main__':
    raise SystemExit(main())
