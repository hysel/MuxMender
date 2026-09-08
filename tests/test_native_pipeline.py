import argparse
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from native_pipeline import allow_cpu, encode_command, progress, remux_command, stage, validate_options, video_payload, comparison_window, matching_timeline
from muxmender import parse_args
from tests.test_muxmender import sample


class NativePipelineTests(unittest.TestCase):
    def test_comparison_reads_past_clip_boundaries(self):
        self.assertEqual(comparison_window(300, 10), '295%315')
        self.assertEqual(comparison_window(0, 10), '0%15')

    def test_reordered_packet_timeline_and_missing_frame(self):
        def summary(times):
            return {'streams': [{'index': 0, 'codec_type': 'video'}],
                    'packets': [{'stream_index': 0, 'pts_time': str(t)} for t in times]}
        source = summary([299, 300.008, 300.092, 300.050, 311])
        self.assertTrue(matching_timeline(source, summary([0, .042, .084]), 300, 310))
        self.assertFalse(matching_timeline(source, summary([0, .084]), 300, 310))
        self.assertFalse(matching_timeline(source, summary([0, .042, .100]), 300, 310))

    def test_progress_mapping(self):
        self.assertEqual(progress('MUXMENDER_PROGRESS=45', 10), 45)
        self.assertEqual(progress('out_time_us=5000000', 10), 50)
        self.assertIsNone(progress('out_time_us=N/A', 10))
        self.assertIsNone(progress('encoder log', 10))

    def test_remux_aligns_timestamps_and_copies_streams(self):
        cmd = remux_command('ffmpeg', Path('original.mkv'), Path('ref.mkv'), Path('new.mkv'), 300, 10)
        self.assertIn('-copyts', cmd)
        self.assertEqual(cmd.count('-ss'), 2)
        self.assertIn('-itsoffset', cmd)
        self.assertIn('0:a?', cmd)
        self.assertIn('0:s?', cmd)
        self.assertIn('0:t?', cmd)
        self.assertIn('-n', cmd)
        self.assertNotIn('-y', cmd)

    def test_encode_preserves_dimensions_and_uses_no_clobber(self):
        for encoder in ('hevc_amf', 'hevc_nvenc', 'hevc_qsv', 'libx265'):
            cmd = encode_command('ffmpeg', 'in.mkv', 'new.mkv', sample(), encoder, 'balanced')
            self.assertIn(encoder, cmd)
            self.assertIn('-n', cmd)
            self.assertNotIn('-y', cmd)
            self.assertNotIn('-vf', cmd)
            self.assertEqual(cmd[cmd.index('-c:a') + 1], 'copy')
            self.assertEqual(cmd[cmd.index('-c:s') + 1], 'copy')

    @patch('native_pipeline.Path.is_file', return_value=True)
    def test_safety_options(self, _):
        for flags in (['--delete-originals'], ['--overwrite-output'], ['--resolution', '720p'], ['--report', 'original.mkv'], ['--preview-seconds', '11']):
            args = parse_args(['original.mkv', '--native-delivery-test', '--dolby-preview-backend', 'd3d11', '--dolby-vision-policy', 'hdr-preview', *flags])
            with self.assertRaises(ValueError):
                validate_options(args, Path('original.mkv'))

    def test_payload_compares_only_same_window_video(self):
        summary = {'streams': [{'index': 0, 'codec_type': 'video'}, {'index': 1, 'codec_type': 'audio'}], 'packets': [
            {'stream_index': 0, 'pts_time': '299.9', 'size': '500'},
            {'stream_index': 0, 'pts_time': '300', 'size': '100'},
            {'stream_index': 0, 'pts_time': '309.9', 'size': '200'},
            {'stream_index': 0, 'pts_time': '310', 'size': '500'},
            {'stream_index': 1, 'pts_time': '301', 'size': '500'}]}
        self.assertEqual(video_payload(summary, 300, 310), (2, 300))

    @patch('native_pipeline.sys.stdin.isatty', return_value=False)
    def test_cpu_fallback_is_not_silent(self, _):
        self.assertFalse(allow_cpu(argparse.Namespace(hardware_fallback='ask'), 'test failure', True))
        self.assertFalse(allow_cpu(argparse.Namespace(hardware_fallback='never'), 'test failure', True))
        self.assertTrue(allow_cpu(argparse.Namespace(hardware_fallback='cpu'), 'test failure', True))
        self.assertFalse(allow_cpu(argparse.Namespace(hardware_fallback='cpu'), 'test failure', False))

    def test_subprocess_failure_is_propagated(self):
        with self.assertRaises(RuntimeError):
            stage([sys.executable, '-c', 'raise SystemExit(7)'], 1, timeout=5)

    @patch('job_tracking.stage_progress')
    def test_stage_updates_dashboard_separately_from_overall_checkpoints(self, update):
        stage([sys.executable,'-c','print("out_time_us=5000000",flush=True)'],10,offset=10,span=55,timeout=5)
        self.assertIn((50.0,None),[call.args for call in update.call_args_list])
        self.assertEqual(update.call_args.args,(100,0))

    def test_subprocess_is_bounded(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            stage([sys.executable, '-c', 'import time; time.sleep(20)'], 1, timeout=0.5, stall=0)


if __name__ == '__main__':
    unittest.main()
