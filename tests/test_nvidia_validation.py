import copy
import unittest

from validate_nvidia import validate_source, copied_subset, compare_sample, metadata_equal, parse_args, disposition_options, startup_audio_lead


class NvidiaValidationTests(unittest.TestCase):
    def test_audio_prefix_detected_even_with_unchanged_track_packets(self):
        streams = [dict(index=0, codec_type='video'), dict(index=1, codec_type='audio')]
        video = dict(stream_index=0, pts_time='0.083')
        audio = [dict(stream_index=1, pts_time=t) for t in ('0.097', '0.129', '10.945')]
        bad = dict(streams=streams, packets=[*audio, video])
        fixed = dict(streams=streams, packets=[video, *audio])
        self.assertAlmostEqual(startup_audio_lead(bad), 10.862)
        self.assertEqual(startup_audio_lead(fixed), 0)
        self.assertIsNone(startup_audio_lead(dict(streams=streams, packets=audio)))
        self.assertIsNone(startup_audio_lead(dict(streams=streams, packets=[dict(stream_index=0, pts_time='nan')])))

    def source(self):
        return {'streams': [dict(index=0, codec_type='video', codec_name='h264', width=1920,
                                height=1040, pix_fmt='yuv420p', color_primaries='bt709',
                                color_transfer='bt709', color_space='bt709', color_range='tv')]}

    def test_dolby_and_unknown_color_fail_closed(self):
        source = self.source()
        validate_source(source, 'SDR')
        source['streams'][0]['side_data_list'] = [{'side_data_type': 'DOVI configuration record'}]
        with self.assertRaisesRegex(ValueError, 'Dolby Vision'):
            validate_source(source, 'SDR')
        source = self.source()
        del source['streams'][0]['color_transfer']
        with self.assertRaises(ValueError):
            validate_source(source, 'SDR')

    def test_sample_bounds(self):
        self.assertEqual(parse_args([]).seconds, 30)
        for args in (['--seconds', '61'], ['--seconds', 'nan'], ['--start', '-1'], ['--gpu', '-1']):
            with self.assertRaises(SystemExit):
                parse_args(args)

    def test_missing_static_hdr_does_not_pass(self):
        self.assertFalse(metadata_equal({'Mastering display metadata': {'max_luminance': '1000/1'}}, {}))
        self.assertTrue(metadata_equal({'test': {'value': '2/2'}}, {'test': {'value': '1/1'}}))

    def test_copied_subset_checks_common_offset_and_packet_bytes(self):
        source = {'streams': [{'index': 0, 'codec_type': 'video'}, {'index': 1, 'codec_type': 'audio'}],
                  'packets': [dict(stream_index=i, pts_time='300', duration_time='1', data_hash=str(i), size='100') for i in range(2)]}
        sample = copy.deepcopy(source)
        for packet in sample['packets']:
            packet['pts_time'] = '0'
        self.assertEqual(copied_subset(source, sample), 300)
        sample['packets'][1]['pts_time'] = '0.5'
        with self.assertRaisesRegex(ValueError, 'timing'):
            copied_subset(source, sample)
        sample['packets'][1]['data_hash'] = 'changed'
        with self.assertRaises(ValueError):
            copied_subset(source, sample)

    def test_compare_rejects_resize_missing_frames_and_hdr_loss(self):
        source = self.source()
        output = copy.deepcopy(source)
        output['streams'][0]['codec_name'] = 'hevc'
        frames = [{'best_effort_timestamp_time': '0', 'interlaced_frame': 0, 'side_data_list': [
            {'side_data_type': 'Content light level metadata', 'max_content': 1000}]}]
        self.assertTrue(all(compare_sample(source, output, frames, frames, 'hevc').values()))
        output['streams'][0]['height'] = 1080
        checks = compare_sample(source, output, frames, [], 'hevc')
        self.assertFalse(checks['height'])
        self.assertFalse(checks['frame_count'])
        self.assertFalse(checks['static_hdr_metadata'])

    def test_unknown_field_order_requires_decoded_progressive_frames(self):
        source = self.source()
        output = copy.deepcopy(source)
        output['streams'][0].update(codec_name='hevc', field_order='progressive')
        frames = [dict(best_effort_timestamp_time='0', interlaced_frame=0)]
        self.assertTrue(compare_sample(source, output, frames, frames, 'hevc')['field_order'])
        frames[0]['interlaced_frame'] = 1
        self.assertFalse(compare_sample(source, output, frames, frames, 'hevc')['field_order'])

    def test_disposition_zero_is_explicit(self):
        data = dict(streams=[dict(disposition={'default': 0, 'forced': 0}),
                             dict(disposition={'default': 0, 'forced': 1})])
        self.assertEqual(disposition_options(data), ['-disposition:0','0','-disposition:1','forced'])


if __name__ == '__main__':
    unittest.main()
