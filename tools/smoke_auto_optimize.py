"""Tiny generated CPU fixture integration test; never accesses library media.

CPU encoders substitute for GPU encoders ONLY inside mocks in this test process.
Relaxed VMAF floors exercise orchestration, not production-quality certification.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
import auto_optimize as ao


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffprobe', required=True)
    parser.add_argument('--output-root', required=True, type=Path)
    parser.add_argument('--early-screen-only', action='store_true', help='Prove an impossible size budget skips remaining clips and full encoding')
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='auto-smoke-', dir=args.output_root))
    inputs = root/'input'; inputs.mkdir()
    source = inputs/'generated.mkv'
    subprocess.run([args.ffmpeg, '-hide_banner', '-nostdin', '-n', '-v', 'error',
        '-f', 'lavfi', '-i', 'testsrc2=size=256x144:rate=24:duration=12',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=12',
        '-vf', 'setfield=prog,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=limited',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '0',
        '-g', '24', '-threads', '2', '-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709',
        '-pix_fmt', 'yuv420p', '-colorspace', 'bt709',
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
        '-c:a', 'ac3', str(source)], check=True, timeout=60)
    original_hash = ao.digest(source)
    original_encode = ao.encode_command
    def test_encode(ffmpeg, source, output, settings, info, streams):
        if settings['codec'] == 'av1':
            with patch.object(ao.mm, 'encoder_options', return_value=['-c:v', 'libaom-av1',
                 '-cpu-used', '8', '-crf', '28', '-b:v', '0', '-threads', '2', '-row-mt', '1']):
                command = original_encode(ffmpeg, source, output, settings, info, streams)
        else:
            command = original_encode(ffmpeg, source, output, settings, info, streams)
            command[command.index('-preset')+1] = 'ultrafast'
            command[-1:-1] = ['-x265-params', 'pools=1:frame-threads=1:log-level=error']
        return command
    with patch.dict(ao.mm.HARDWARE_ENCODERS, {'nvidia': {'hevc': 'libx265', 'av1': 'libaom-av1'}}), \
         patch.object(ao, 'probe_encoder', return_value={'status': 'working', 'scope': 'MOCK FOR CPU SMOKE ONLY'}), \
         patch.object(ao, 'encode_command', side_effect=test_encode):
        code = ao.main([str(source), '--output-dir', str(root/'output'), '--execute', '--encode-best',
            '--hardware', 'nvidia', '--playback-verified-codecs', 'hevc', 'av1', '--qualities', 'balanced',
            '--seconds', '1', '--vmaf-mean', '0', '--vmaf-p5', '0', '--minimum-savings-percent', '99.9' if args.early_screen_only else '0',
            '--min-free-gib', '1', '--timeout', '180', '--ffmpeg', args.ffmpeg, '--ffprobe', args.ffprobe])
    assert code == 0
    runs = list((root/'output').glob('auto-*'))
    state = json.loads((runs[0]/'status.json').read_text())
    if args.early_screen_only:
        assert state['state']=='trials-completed' and state['decision']['action']=='keep_original',state
        trials=json.loads((runs[0]/'trials.json').read_text())
        assert len(trials['trials'])==2
        assert all(len(t['samples'])==1 and t['size_screen']['early_bound'] for t in trials['trials']),trials
        assert not list(runs[0].glob('full-*.mkv'))
        assert not list(runs[0].glob('*-vmaf.json'))
        assert ao.digest(source)==original_hash
        print('PASS: 2 clips instead of 6; no quality/full encode; original unchanged:',root)
        return
    assert state['state']=='validated-copy-awaiting-playback', state
    trials = json.loads((runs[0]/'trials.json').read_text())
    assert all(s['quality_pass'] and s['decode_pass'] and s['preservation_pass']
               for t in trials['trials'] for s in t['samples']), trials
    assert ao.digest(source) == original_hash
    print('PASS: six trials, measured selection, full copy, validation, source unchanged:', root)


if __name__ == '__main__':
    main()
