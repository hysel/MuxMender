from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import research_hdr_sdr_long as research


class LongSDRResearchTests(unittest.TestCase):
    def test_av1_changes_only_encoder_not_quality_or_preservation_policy(self):
        from output_presets import preset
        policy=preset('tv1080');before=dict(policy)
        command=research.nvenc_research_options(policy,'av1')
        self.assertEqual(command[command.index('-c:v')+1],'av1_nvenc')
        self.assertEqual(command[command.index('-bf')+1],'0')
        self.assertNotIn('-b_ref_mode',command)
        self.assertEqual(policy,before)
        with self.assertRaises(ValueError):research.nvenc_research_options(policy,'other')

    def test_efficient_encoder_keeps_the_preset_limits_unchanged(self):
        from output_presets import preset
        policy=preset('tv1080');before=dict(policy)
        command=research.nvenc_research_options(policy)
        for key,value in (('-preset','p7'),('-bf','3'),('-rc-lookahead','32'),('-multipass','fullres')):
            self.assertEqual(command[command.index(key)+1],value)
        self.assertEqual(policy,before)
        self.assertEqual(policy['mean'],95);self.assertEqual(policy['video_bps'],8000000)
        self.assertLess(int(command[command.index('-maxrate')+1]),policy['video_bps'])
        self.assertLess(int(command[command.index('-b:v')+1]),policy['video_bps'])

    def test_frame_reader_is_bounded_and_reads_all_frames(self):
        command=research.probe_command(Path('reference.mkv'),True)
        self.assertEqual(command[command.index('-threads')+1],'2')
        self.assertIn('-show_frames',command)
        self.assertNotIn('-read_intervals',command)
        self.assertNotIn('-show_entries',command)
        self.assertNotIn('-show_data_hash',command)
        self.assertEqual(command[-1],'reference.mkv')

    def test_metadata_probe_still_collects_track_chapter_and_byte_evidence(self):
        command=research.probe_command(Path('input.mkv'))
        for flag in ('-show_streams','-show_chapters','-show_format','-show_data_hash'):
            self.assertIn(flag,command)

    def test_scratch_cleanup_keeps_review_output_and_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            scratch=('mobius-lossless-reference.mkv','mobius-video.mkv','audio-relay.mka','source-excerpt-001.mkv')
            keep=('mobius-1080p-with-tracks.mkv','result.json','source-excerpt-notes.txt')
            for name in scratch+keep:(root/name).write_bytes(b'fixture')
            with patch.object(research,'run',side_effect=RuntimeError('fixture')):
                with self.assertRaises(RuntimeError):research.run_with_cleanup(root)
            self.assertTrue(all(not (root/n).exists() for n in scratch))
            self.assertTrue(all((root/n).exists() for n in keep))
