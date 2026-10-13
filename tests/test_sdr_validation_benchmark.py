import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('bench',Path(__file__).resolve().parents[1]/'tools/benchmark_sdr_validation.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)


class BenchmarkTests(unittest.TestCase):
    def test_both_inputs_gpu_and_bounded(self):
        command=bench.command_for('ffmpeg','reference','candidate','24','scores.json',720,'cuda4')
        self.assertEqual(command.count('-hwaccel'),2)
        graph=command[command.index('-filter_complex')+1]
        self.assertEqual(graph.count('trim=end_frame=720'),2)
        self.assertEqual(graph.count('hwdownload'),2)
        self.assertIn('libvmaf=n_threads=4',graph)
        self.assertIn('-xerror',command)
        self.assertNotIn('n_subsample',graph)

    def test_score_changes_detected(self):
        a=[dict(frameNum=0,metrics=dict(vmaf=94.0))]
        self.assertEqual(bench.compare(a,a),0)
        self.assertEqual(bench.compare(a,[dict(frameNum=0,metrics=dict(vmaf=93.0))]),1)
        with self.assertRaises(ValueError):bench.compare(a,[])
        with self.assertRaises(ValueError):bench.compare(a,[dict(frameNum=0,metrics=dict(vmaf=float('nan')))])
