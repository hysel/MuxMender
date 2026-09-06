import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mux_integrity import verify_startup_interleaving, seek_track_alignment


class PublicationInterleavingTests(unittest.TestCase):
    def test_seek_requires_audio_as_well_as_video(self):
        data = {'streams': [{'index': 0, 'codec_type': 'video'}, {'index': 1, 'codec_type': 'audio'}],
                'packets': [{'stream_index': 0, 'pts_time': '1616.198'}, {'stream_index': 0, 'pts_time': '1657.865'}]}
        self.assertFalse(seek_track_alignment(data))
        data['packets'].append({'stream_index': 1, 'pts_time': '1616.200'})
        self.assertTrue(seek_track_alignment(data))
        data['packets'][-1]['pts_time'] = '1620.000'
        self.assertFalse(seek_track_alignment(data))
    @patch('mux_integrity.subprocess.run')
    def test_unsafe_prefix_rejected_and_correct_order_accepted(self, run):
        streams = [{'index': 0, 'codec_type': 'video'}, {'index': 1, 'codec_type': 'audio'}]
        video = {'stream_index': 0, 'pts_time': '0.083'}
        audio = [{'stream_index': 1, 'pts_time': '0.097'}, {'stream_index': 1, 'pts_time': '10.945'}]
        for packets, expected in ((audio + [video], False), ([video] + audio, True), (audio, False)):
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps({'streams': streams, 'packets': packets}))
            self.assertEqual(verify_startup_interleaving('sample.mkv', 'ffprobe')[0], expected)

    @patch('mux_integrity.subprocess.run')
    def test_failed_or_timed_out_probe_cannot_pass(self, run):
        run.return_value = SimpleNamespace(returncode=1, stdout='')
        self.assertFalse(verify_startup_interleaving('sample.mkv', 'ffprobe')[0])
        run.side_effect = subprocess.TimeoutExpired('ffprobe', 30)
        with self.assertRaises(subprocess.TimeoutExpired):
            verify_startup_interleaving('sample.mkv', 'ffprobe')
