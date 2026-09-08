import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mux_integrity import verify_startup_interleaving, seek_track_alignment
from mux_integrity import playback_plan, verify_playback_copy
from copy import deepcopy


class PlaybackDefaultsTests(unittest.TestCase):
    def source(self):
        return {'streams': [
            {'index': 0, 'codec_type': 'video', 'codec_name': 'av1', 'disposition': {}},
            {'index': 1, 'codec_type': 'audio', 'codec_name': 'aac', 'channels': 6,
             'channel_layout': '5.1', 'disposition': {'default': 1}},
            {'index': 2, 'codec_type': 'subtitle', 'codec_name': 'subrip',
             'disposition': {'forced': 1, 'default': 1}}]}

    def test_preserves_forced_subtitles_and_reuses_eac3(self):
        data = self.source()
        plan = playback_plan(data, subtitle_track=0)
        self.assertEqual(plan['dispositions'], [[], ['default'], [], ['default', 'forced']])
        self.assertEqual(plan['output_order'], [0, None, 1, 2])
        data['streams'][1]['codec_name'] = 'eac3'
        plan = playback_plan(data)
        self.assertFalse(plan['added_audio'])
        self.assertEqual(plan['dispositions'][1], ['default'])

    def test_ambiguous_audio_and_downmix_are_rejected(self):
        data = self.source()
        data['streams'].append(deepcopy(data['streams'][1]))
        with self.assertRaises(ValueError):
            playback_plan(data)
        data = self.source()
        data['streams'][1]['channels'] = 8
        with self.assertRaises(ValueError):
            playback_plan(data)
        with self.assertRaises(ValueError):
            playback_plan(self.source(), subtitle_track=1)

    def test_existing_compatible_track_moves_first_without_duplication(self):
        data = self.source()
        compatible = deepcopy(data['streams'][1])
        compatible.update(index=3, codec_name='eac3')
        data['streams'].append(compatible)
        plan = playback_plan(data, audio_track=1)
        self.assertFalse(plan['added_audio'])
        self.assertEqual(plan['output_order'], [0, 3, 1, 2])
        self.assertEqual(plan['dispositions'], [[], ['default'], [], ['default', 'forced']])

    @patch('mux_integrity.packet_fingerprints')
    def test_timestamp_change_prevents_publication(self, fingerprints):
        source = self.source()
        source['streams'][1]['codec_name'] = 'eac3'
        plan = playback_plan(source)
        output = deepcopy(source)
        fingerprints.side_effect = [{0: (2, 'original')}, {0: (2, 'shifted')}]
        with self.assertRaisesRegex(RuntimeError, 'timestamps'):
            verify_playback_copy('source', 'output', source, output, plan, 'ffprobe')


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
