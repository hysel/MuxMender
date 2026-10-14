import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cpu_allocation import detect,preference,recommendation,scoring_ceiling


class AllocationTests(unittest.TestCase):
    def test_fractional_quota_and_affinity(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'cpu.max').write_text('150000 100000')
            with patch('cpu_allocation.os.cpu_count',return_value=32),patch('cpu_allocation.os.sched_getaffinity',return_value={0,1,2,3},create=True):
                result=detect(root)
            self.assertEqual(result['effective_cpus'],1.5)
            self.assertEqual(result['logical_cpus'],32)
            self.assertEqual(recommendation(result)['recommended_scoring_threads'],1)

    def test_v1_quota(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'cpu').mkdir()
            (root/'cpu/cpu.cfs_quota_us').write_text('200000')
            (root/'cpu/cpu.cfs_period_us').write_text('100000')
            with patch('cpu_allocation.os.cpu_count',return_value=16),patch('cpu_allocation.os.sched_getaffinity',return_value=set(range(16)),create=True):
                self.assertEqual(detect(root)['effective_cpus'],2)

    def test_recommendation_never_promises_unqualified_threads(self):
        self.assertEqual(recommendation({'effective_cpus':128})['recommended_scoring_threads'],4)
        self.assertEqual(recommendation({'effective_cpus':8},setting=preference('shared'))['recommended_scoring_threads'],2)
        self.assertEqual(recommendation({'effective_cpus':8},{'cpu_percent':90})['recommended_scoring_threads'],1)
        self.assertEqual(recommendation({'effective_cpus':8},{'available_gib':2})['recommended_scoring_threads'],1)
        self.assertEqual(recommendation({})['recommended_scoring_threads'],1)

    def test_custom_restricts_does_not_increase_engine_choice(self):
        with patch('cpu_allocation.capacity',return_value={'effective_cpus':16}):
            with patch.dict(os.environ,{'MUXMENDER_CPU_MODE':'custom','MUXMENDER_SCORING_CEILING':'1'}):
                self.assertEqual(scoring_ceiling(4),1)
            with patch.dict(os.environ,{'MUXMENDER_CPU_MODE':'custom','MUXMENDER_SCORING_CEILING':'128'}):
                self.assertEqual(scoring_ceiling(2),2)
        for value in (0,-1,True,2.5,1025):
            with self.assertRaises(ValueError):preference('custom',value)

    def test_ui_explains_scope(self):
        from ui.app import HTML
        self.assertIn('id="cpu-mode"',HTML)
        self.assertIn('id="cpu-advice"',HTML)
        self.assertIn('not an OS CPU limit',HTML)
