import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from tests.test_muxmender import sample
from dv_preservation_test import require_candidate, validate_timeline, run, static_hdr, compare_static_hdr, canonical_rpu, experimental_encoder_options
from dv_preservation_test import sample_encoder_options, require_nvidia_frames


class DVExperimentTests(unittest.TestCase):
    def test_nvidia_sample_is_explicit_and_keeps_ten_bit_color(self):
        info = sample(dolby_vision=True, video_codec='hevc', dolby_vision_profile=8,
                      dolby_vision_compatibility_id=1, dolby_vision_rpu_present=True)
        self.assertEqual(sample_encoder_options(info), experimental_encoder_options(info))
        opts = sample_encoder_options(info, True)
        self.assertEqual(opts[opts.index('-c:v')+1], 'hevc_nvenc')
        self.assertEqual(opts[opts.index('-pix_fmt')+1], 'p010le')
        self.assertEqual(opts[opts.index('-color_trc')+1], 'smpte2084')
        self.assertEqual(opts[opts.index('-bf')+1], '0')
        self.assertNotIn('-vf', opts)
        with self.assertRaises(ValueError):
            sample_encoder_options(sample(dolby_vision=True, dolby_vision_profile=5), True)

    def test_nvidia_sample_rejects_other_dynamic_hdr_and_interlacing(self):
        require_nvidia_frames([dict(interlaced_frame=0, repeat_pict=0)])
        for frame in (dict(interlaced_frame=1), dict(interlaced_frame=0, repeat_pict=1),
                      dict(interlaced_frame=0, side_data_list=[dict(side_data_type='HDR Dynamic Metadata SMPTE2094-40 (HDR10+)')])):
            with self.assertRaises(ValueError):
                require_nvidia_frames([frame])

    def test_qp_changes_do_not_change_preset_or_color(self):
        base = experimental_encoder_options(sample())
        tuned = experimental_encoder_options(sample(), 21, 23)
        self.assertEqual(tuned[tuned.index('-quality')+1], 'quality')
        for flag in ('-color_primaries', '-color_trc', '-colorspace', '-pix_fmt'):
            self.assertEqual(tuned[tuned.index(flag)+1], base[base.index(flag)+1])
        self.assertEqual(tuned[tuned.index('-qp_i')+1], '21')
        self.assertEqual(tuned[tuned.index('-qp_p')+1], '23')
        for invalid in (-1, 52, float('nan'), 20.5, True):
            with self.assertRaises(ValueError):
                experimental_encoder_options(sample(), invalid, 20)

    def test_rpu_canonicalization_preserves_values_and_frame_order(self):
        a = [{'rpu_data_crc32': 1, 'ext_metadata_blocks': [{'Level1': 20}, {'Level6': 30}]}]
        b = [{'rpu_data_crc32': 2, 'ext_metadata_blocks': [{'Level6': 30}, {'Level1': 20}]}]
        self.assertEqual(canonical_rpu(a), canonical_rpu(b))
        self.assertNotEqual(canonical_rpu(a), canonical_rpu([{'ext_metadata_blocks': [{'Level1': 21}, {'Level6': 30}]}]))
        self.assertNotEqual(canonical_rpu(a + [{'frame': 2}]), canonical_rpu([{'frame': 2}] + a))

    def test_profile_gate(self):
        for profile in (None, 5, 7, 20):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                require_candidate(sample(dolby_vision=True, dolby_vision_profile=profile))

    def test_timeline(self):
        frames = [{'best_effort_timestamp_time': str(n/24)} for n in range(10)]
        validate_timeline(frames, list(reversed(frames)))
        with self.assertRaises(ValueError):
            validate_timeline(frames, frames[:-1])
        with self.assertRaises(ValueError):
            validate_timeline(frames, [{'best_effort_timestamp_time': str(n/24+.04)} for n in range(10)])

    def test_duration_bounds(self):
        for seconds in (0, 31, float('nan'), float('inf')):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                run(SimpleNamespace(seconds=seconds))

    def test_start_bounds(self):
        for start in (-1, float('nan'), float('inf')):
            with self.subTest(start=start), self.assertRaises(ValueError):
                run(SimpleNamespace(seconds=30, start=start))

    def test_dry_run_does_not_write_or_encode(self):
        info = sample(dolby_vision=True, video_codec='hevc', dolby_vision_profile=8,
                      dolby_vision_compatibility_id=1, dolby_vision_rpu_present=True)
        args = SimpleNamespace(source=Path('source.mkv'), seconds=10, execute=False,
                               ffmpeg='ffmpeg', ffprobe='ffprobe', dovi_tool='dovi_tool')
        with patch('dv_preservation_test.Path.resolve', return_value=args.source), \
             patch('dv_preservation_test.shutil.which', return_value='tool'), \
             patch('dv_preservation_test.mm.probe', return_value=info), \
             patch('dv_preservation_test.Path.mkdir') as mkdir, \
             patch('dv_preservation_test.np.stage') as stage:
            self.assertEqual(run(args), 0)
            mkdir.assert_not_called()
            stage.assert_not_called()

    def test_static_hdr_not_confused_with_dv(self):
        self.assertEqual(static_hdr([{'side_data_list': [{'side_data_type': 'DOVI RPU Data'}]}]), [])

    def test_static_hdr_tolerance_is_tiny_and_reported(self):
        def frames(x):
            return [{'side_data_list': [{'side_data_type': 'Mastering display metadata', 'white_point_x': x}]}]
        self.assertEqual(len(compare_static_hdr(frames('15635/50000'), frames('15634/50000'))), 1)
        with self.assertRaises(ValueError):
            compare_static_hdr(frames('15635/50000'), frames('15633/50000'))
        with self.assertRaises(ValueError):
            compare_static_hdr(frames('15635/50000'), [{'side_data_list': []}])
