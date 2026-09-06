import unittest

from mux_integrity import video_stage_command, finalize_command


class NvidiaMuxTests(unittest.TestCase):
    def test_video_stage_excludes_other_tracks_and_preserves_timing(self):
        command = ['ffmpeg', '-n', '-i', 'source.mkv', '-map', '0', '-c:v', 'hevc_nvenc', '-disposition:1', 'default', 'stage.mkv']
        stage = video_stage_command(command)
        self.assertEqual(command[command.index('-map') + 1], '0')
        self.assertEqual(stage[stage.index('-map') + 1], '0:v:0')
        self.assertIn('-copyts', stage)
        self.assertNotIn('-disposition:1', stage)
        self.assertEqual(stage[stage.index('-fps_mode') + 1], 'passthrough')
        self.assertEqual(stage[stage.index('-enc_time_base:v') + 1], 'demux')

    def test_finalize_preserves_nonstandard_stream_order_and_dispositions(self):
        probe = {'streams': [
            {'index': 0, 'codec_type': 'audio', 'disposition': {'default': 1}},
            {'index': 1, 'codec_type': 'subtitle', 'disposition': {'default': 0}},
            {'index': 2, 'codec_type': 'video', 'disposition': {'default': 1}},
            {'index': 3, 'codec_type': 'attachment', 'disposition': {}},
        ]}
        command = finalize_command('video.mkv', 'original.mkv', 'final.mkv', probe, 'ffmpeg')
        mapping = [command[i+1] for i, arg in enumerate(command) if arg == '-map']
        self.assertEqual(mapping, ['1:0', '1:1', '0:v:0', '1:3'])
        self.assertEqual(command[command.index('-disposition:1') + 1], '0')
        self.assertEqual(command[command.index('-c') + 1], 'copy')
        self.assertEqual(command[command.index('-map_chapters') + 1], '1')
        self.assertNotEqual(command[command.index('-max_interleave_delta') + 1], '0')

    def test_extra_video_fails_closed(self):
        with self.assertRaises(ValueError):
            finalize_command('v', 's', 'o', {'streams': [{'codec_type': 'video'}, {'codec_type': 'video'}]}, 'ffmpeg')
