import sys
import unittest
from unittest.mock import patch
from pathlib import Path

import muxmender as mm
import native_pipeline as np
from streaming_pipeline import pipe_encode, source_stream_packets, run, full_range, full_remux_command, RunGuard
from tests.test_muxmender import sample
from types import SimpleNamespace
import tempfile


class StreamingTests(unittest.TestCase):
    def test_full_file_is_explicit_and_rejects_ranges(self):
        self.assertFalse(mm.parse_args(['source.mkv']).full_file_streaming)
        args = mm.parse_args(['source.mkv', '--full-file-streaming'])
        self.assertEqual(full_range(args, sample(duration_seconds=3264)), (0, 3264))
        args.preview_range_explicit = True
        with self.assertRaises(ValueError):
            full_range(args, sample())
        args.preview_range_explicit = False
        for duration in (0, float('nan'), float('inf'), 86401):
            with self.assertRaises(ValueError):
                full_range(args, sample(duration_seconds=duration))

    def test_full_remux_has_no_cut_or_overwrite(self):
        command = full_remux_command('ffmpeg', 'original', 'video', 'new')
        for forbidden in ('-ss', '-t', '-shortest', '-y'):
            self.assertNotIn(forbidden, command)
        self.assertIn('-n', command)
        self.assertEqual(command[command.index('-map_chapters') + 1], '0')

    def test_stop_and_disk_reserve_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = RunGuard(Path(directory), reserve=1024)
            with patch('streaming_pipeline.shutil.disk_usage', return_value=SimpleNamespace(free=1)):
                with self.assertRaisesRegex(RuntimeError, 'Free space'):
                    guard()
            (Path(directory) / 'STOP').touch()
            with self.assertRaisesRegex(RuntimeError, 'Stop requested'):
                guard()

    @patch('streaming_pipeline.np.checked_json')
    def test_audio_hash_comparison_rebases_only_clip_packets(self, checked):
        checked.return_value = {'packets': [
            {'stream_index': 1, 'pts_time': '299.968000', 'data_hash': 'before'},
            {'stream_index': 1, 'pts_time': '300.000000', 'data_hash': 'keep', 'duration_time': '0.032000'},
            {'stream_index': 1, 'pts_time': '360.000000', 'data_hash': 'after'}]}
        packets = source_stream_packets('ffprobe', 'original.mkv', 'a', 300, 60)
        self.assertEqual(packets, [{'stream_index': 1, 'pts_time': '0.000000', 'data_hash': 'keep', 'duration_time': '0.032000'}])
        self.assertIn('270%365', checked.call_args.args[0])

    @patch('streaming_pipeline.np.stage')
    @patch('streaming_pipeline.pipe_encode')
    @patch('streaming_pipeline.np.checked_json', return_value={'streams': [{'start_time': '0'}]})
    @patch('streaming_pipeline.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='--stream-output'))
    @patch('streaming_pipeline.shutil.which', return_value='tool')
    @patch('streaming_pipeline.mm.gpu_vendors', return_value=['amd'])
    @patch('streaming_pipeline.mm.ffmpeg_encoder_names', return_value={'hevc_amf'})
    @patch('streaming_pipeline.mm.probe', return_value=sample(dolby_vision=True, dolby_vision_profile=5))
    @patch('native_pipeline.Path.is_file', return_value=True)
    def test_dry_run_never_starts_gpu_or_creates_output(self, isfile, probe, encoders, vendors, which, subprocess_run, checked, pipe, stage):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'not-created'
            args = mm.parse_args(['original.mkv', '--streaming-delivery-test', '--dolby-preview-backend', 'd3d11', '--dolby-vision-policy', 'hdr-preview', '--preview-seconds', '60', '--output-dir', str(output)])
            self.assertEqual(run(args, Path('original.mkv')), 0)
            pipe.assert_not_called()
            stage.assert_not_called()
            self.assertFalse(output.exists())

    def test_binary_pipe_and_separate_summary(self):
        producer = [sys.executable, '-u', '-c', 'import sys; sys.stdout.buffer.write(bytes(range(256))*1000); sys.stdout.flush(); print(\'MUXMENDER_DV_PREVIEW={"ok":true,"frames":24}\',file=sys.stderr,flush=True)']
        consumer = [sys.executable, '-u', '-c', 'import sys; data=sys.stdin.buffer.read(); assert data==bytes(range(256))*1000; print("out_time_us=1000000",flush=True)']
        self.assertEqual(pipe_encode(producer, consumer, 1, 10, 5)['frames'], 24)

    def test_consumer_failure_stops_producer(self):
        producer = [sys.executable, '-u', '-c', 'import time; time.sleep(30)']
        consumer = [sys.executable, '-c', 'raise SystemExit(7)']
        with self.assertRaisesRegex(RuntimeError, 'consumer exited'):
            pipe_encode(producer, consumer, 1, 5, 3)

    def test_producer_failure_is_not_successful_empty_encode(self):
        with self.assertRaisesRegex(RuntimeError, 'producer exited'):
            pipe_encode([sys.executable, '-c', 'raise SystemExit(9)'],
                        [sys.executable, '-c', 'import sys; sys.stdin.buffer.read()'], 1, 5, 3)

    def test_pipeline_stall_is_bounded(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            pipe_encode([sys.executable, '-c', 'import time; time.sleep(30)'],
                        [sys.executable, '-c', 'import sys; sys.stdin.buffer.read()'], 1, 5, .2)

    @patch('native_pipeline.Path.is_file', return_value=True)
    def test_only_streaming_gets_sixty_second_limit(self, _):
        args = mm.parse_args(['source.mkv', '--dolby-preview-backend', 'd3d11', '--dolby-vision-policy', 'hdr-preview', '--preview-seconds', '60'])
        np.validate_options(args, Path('source.mkv'), max_seconds=60)
        with self.assertRaises(ValueError):
            np.validate_options(args, Path('source.mkv'))
        args.preview_seconds = 61
        with self.assertRaises(ValueError):
            np.validate_options(args, Path('source.mkv'), max_seconds=60)
