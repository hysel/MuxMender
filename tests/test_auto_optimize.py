import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import auto_optimize as ao


def source_data():
    return dict(streams=[dict(index=0, codec_type='video', codec_name='h264',
        width=1920, height=1080, pix_fmt='yuv420p', field_order='progressive',
        color_space='bt709', color_primaries='bt709', color_transfer='bt709',
        color_range='tv', sample_aspect_ratio='1:1', avg_frame_rate='24/1', disposition={})],
        chapters=[], format=dict(duration='120'))


class AutoOptimizeTests(unittest.TestCase):
    def test_intermediate_hevc_changes_only_cq_and_preserves_safe_flags(self):
        options = ['-c:v', 'hevc_nvenc', '-preset', 'p6', '-cq', '21']
        for cq in (22, 23, 24):
            with patch.object(ao.mm, 'encoder_options', return_value=options):
                cmd = ao.encode_command('ffmpeg', Path('input'), Path('output'),
                    dict(codec='hevc', quality='balanced', encoder='hevc_nvenc', nvenc_cq=cq),
                    None, source_data()['streams'])
            self.assertEqual(cmd[cmd.index('-cq')+1], str(cq))
            self.assertEqual(cmd[cmd.index('-preset')+1], 'p6')
            self.assertIn('-n', cmd)
            self.assertNotIn('-vf', cmd)
            self.assertNotIn('-r', cmd)
            self.assertEqual(options[-1], '21')
        with patch.object(ao.mm, 'encoder_options', return_value=options):
            with self.assertRaises(ValueError):
                ao.encode_command('ffmpeg', Path('input'), Path('output'),
                    dict(codec='hevc', quality='balanced', encoder='hevc_nvenc', nvenc_cq=30),
                    None, source_data()['streams'])

    def test_metric_clock_uses_matching_ordinals_not_rounded_pts(self):
        graph = ao.quality_graph('quality.json', '24000/1001')
        self.assertEqual(graph.count('setpts=N*1001/(24000*TB)'), 2)
        self.assertNotIn('PTS-STARTPTS', graph)
        with self.assertRaises(ValueError):
            ao.quality_graph('../outside.json', '24/1')
    def test_positions_are_distinct_and_bounded(self):
        self.assertEqual(ao.sample_positions(120, 10), [16.5, 55, 93.5])
        for duration, seconds in [(5, 1), (float('inf'), 1), (100, 0), (1000, 61)]:
            with self.assertRaises(ValueError):
                ao.sample_positions(duration, seconds)

    def test_source_gate(self):
        ao.eligibility(source_data())
        for key, value in [('pix_fmt', 'yuv420p10le'), ('field_order', 'tt'),
                           ('color_transfer', 'smpte2084'), ('color_range', 'unknown'),
                           ('side_data_list', [{'side_data_type': 'DOVI configuration record'}])]:
            data = source_data()
            data['streams'][0][key] = value
            with self.assertRaises(ValueError):
                ao.eligibility(data)

    def test_quality_requires_all_frames_and_poor_tail_fails(self):
        scores = dict(frames=[dict(metrics=dict(vmaf=99)) for _ in range(100)])
        self.assertTrue(ao.quality_summary(scores, 100, 95, 90)['passed'])
        for frame in scores['frames'][:6]:
            frame['metrics']['vmaf'] = 80
        self.assertFalse(ao.quality_summary(scores, 100, 95, 90)['passed'])
        with self.assertRaises(ValueError):
            ao.quality_summary(scores, 101, 95, 90)
        scores['frames'][0]['metrics']['vmaf'] = float('nan')
        with self.assertRaises(ValueError):
            ao.quality_summary(scores, 100, 95, 90)

    def test_metadata_blocks_resize_color_and_flags(self):
        original = source_data()
        after = copy.deepcopy(original)
        after['streams'][0]['codec_name'] = 'hevc'
        ao.metadata_check(original, after, 'hevc')
        for key, value in [('height', 1082), ('color_transfer', 'unknown'), ('disposition', {'default': 1})]:
            bad = copy.deepcopy(after)
            bad['streams'][0][key] = value
            with self.assertRaises(ValueError):
                ao.metadata_check(original, bad, 'hevc')

    def test_frame_and_packet_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'a', Path(folder)/'b'
            row = 'width=1920|height=1080|pix_fmt=yuv420p|sample_aspect_ratio=1:1|interlaced_frame=0|repeat_pict=0|best_effort_timestamp_time=0.000\n'
            a.write_text(row); b.write_text(row)
            self.assertEqual(ao.compare_frames(a, b), 1)
            for bad in [row.replace('0.000', '0.1'), row.replace('1080', '1082'), row.replace('0.000', 'nan'), row+row]:
                b.write_text(bad)
                with self.assertRaises(ValueError):
                    ao.compare_frames(a, b)
            a.write_text('pts_time=0|duration_time=0.04|data_hash=SHA256:a\n')
            b.write_text(a.read_text())
            ao.compare_packets(a, b)
            b.write_text('pts_time=0|duration_time=0.04\n')
            with self.assertRaises(ValueError):
                ao.compare_packets(a, b)

    def test_encode_is_copy_only_except_video(self):
        with patch.object(ao.mm, 'encoder_options', return_value=['-c:v', 'hevc_nvenc']):
            cmd = ao.encode_command('ffmpeg', Path('input'), Path('output'),
                dict(codec='hevc', quality='balanced', encoder='hevc_nvenc'), None, source_data()['streams'])
        self.assertIn('-n', cmd)
        self.assertNotIn('-y', cmd)
        self.assertNotIn('-vf', cmd)
        self.assertNotIn('-r', cmd)
        self.assertIn('-copyts', cmd)
        self.assertEqual(cmd[cmd.index('-c')+1], 'copy')

    def test_dry_run_no_output_and_no_gpu_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'input').mkdir()
            source = base/'input'/'source.mkv'
            source.write_bytes(b'original')
            out = base/'output'
            with patch.object(ao.Workflow, 'probe', return_value=source_data()), patch.object(ao, 'probe_encoder') as gpu:
                self.assertEqual(ao.main([str(source), '--output-dir', str(out)]), 0)
            gpu.assert_not_called()
            self.assertFalse(out.exists())
            self.assertEqual(source.read_bytes(), b'original')

    def test_output_inside_source_blocked_before_job_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source.mkv'
            source.write_bytes(b'original')
            output = Path(folder)/'output'
            with patch.object(ao, 'tracked_call') as tracked:
                with self.assertRaises(ValueError):
                    ao.main([str(source), '--output-dir', str(output), '--execute'])
            tracked.assert_not_called()
            self.assertFalse(output.exists())

    def test_unknown_playback_does_not_start_trials(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'input').mkdir()
            source = base/'input'/'source.mkv'; source.write_bytes(b'original')
            with patch.object(ao.Workflow, 'probe', return_value=source_data()), patch.object(ao, 'probe_encoder') as gpu:
                with self.assertRaises(ValueError):
                    ao.main([str(source), '--output-dir', str(base/'output'), '--execute'])
            gpu.assert_not_called()

    def test_low_space_aborts_before_gpu_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'input').mkdir()
            source = base/'input'/'source.mkv'; source.write_bytes(b'original')
            with patch.object(ao.Workflow, 'probe', return_value=source_data()), \
                 patch.object(ao.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), \
                 patch.object(ao, 'probe_encoder') as gpu:
                with self.assertRaises(RuntimeError):
                    ao.main([str(source), '--output-dir', str(base/'output'), '--execute',
                             '--playback-verified-codecs', 'hevc'])
            gpu.assert_not_called()
            self.assertEqual(source.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
