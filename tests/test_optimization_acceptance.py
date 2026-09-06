import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from optimization_acceptance import savings_decision, savings_summary
import dv_full_file as full
from test_muxmender import sample


class AcceptanceTests(unittest.TestCase):
    def test_summary_uses_weighted_totals_and_decimal_units(self):
        result = savings_summary([(1_000_000_000, 500_000_000), (3_000_000_000, 2_500_000_000)])
        self.assertEqual(result['saved_percent'], 25)
        self.assertEqual(result['saved_MB'], 1000)
        self.assertEqual(result['saved_GB'], 1)
        self.assertEqual(result['saved_TB'], .001)

    def test_empty_summary_and_size_increase(self):
        self.assertEqual(savings_summary([])['saved_percent'], 0)
        self.assertEqual(savings_summary([(100, 110)])['saved_percent'], -10)

    def test_equal_or_larger_never_qualifies_even_at_zero_threshold(self):
        for size in (100,101,300):
            self.assertFalse(savings_decision(100,size,0)['eligible'])
        self.assertFalse(savings_decision(100,96)['eligible'])
        self.assertTrue(savings_decision(100,94)['eligible'])

    def test_invalid_thresholds_are_rejected(self):
        for threshold in (-1,100,float('nan'),float('inf')):
            with self.assertRaises(ValueError): savings_decision(100,50,threshold)

    def test_exact_threshold_qualifies(self):
        self.assertTrue(savings_decision(100,90,10)['eligible'])
        self.assertTrue(savings_decision(100,95,5)['eligible'])

    def test_bad_sample_prevents_full_encode(self):
        info=sample(video_codec='hevc',dolby_vision=True,dolby_vision_profile=8,
                    dolby_vision_compatibility_id=1,dolby_vision_rpu_present=True)
        with tempfile.TemporaryDirectory() as folder:
            args=SimpleNamespace(source=Path('original.mkv'),execute=True,
                experimental_nvidia=True,min_savings=5,ffmpeg='ffmpeg',ffprobe='ffprobe',
                dovi_tool='dovi_tool',work_dir=Path(folder)/'must-not-be-created')
            with patch.object(full.mm,'probe',return_value=info), \
                 patch.object(full.shutil,'which',return_value='tool'), \
                 patch.object(full.mm,'ffmpeg_encoder_names',return_value={'hevc_nvenc'}), \
                 patch.object(full.mm,'gpu_vendors',return_value=['nvidia']), \
                 patch.object(full,'nvidia_savings_preflight',return_value=savings_decision(100,300)), \
                 patch.object(full.np,'stage') as encode:
                self.assertEqual(full.run(args),0)
                encode.assert_not_called()
                self.assertFalse(args.work_dir.exists())
