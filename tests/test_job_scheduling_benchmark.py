import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


class SchedulingBenchmarkTests(unittest.TestCase):
    def test_linux_guard_precedes_media_work(self):
        path=Path(__file__).resolve().parents[1]/'tools'/'benchmark_job_scheduling.py'
        spec=importlib.util.spec_from_file_location('benchmark_scheduling',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module.sys,'platform','win32'):
            with self.assertRaisesRegex(RuntimeError,'Linux app benchmark only'):module.main()

    def test_baseline_gates_and_nonpublication(self):
        text=(Path(__file__).resolve().parents[1]/'tools'/'benchmark_job_scheduling.py').read_text()
        self.assertIn("vmaf_mean=case.get('mean',94),vmaf_p5=90",text)
        self.assertIn("mean=90,profile='space-saver'",text)
        self.assertIn('workflow.validate(',text)
        self.assertIn('workflow.quality(',text)
        self.assertIn("get_context('spawn')",text)
        self.assertNotIn('replace_validated',text)
        self.assertIn('prune_generated(root,execute=True)',text)
        self.assertIn("sys.path[:0]=['/opt/muxmender','/opt/muxmender-runtime']",text)
        self.assertIn('inspect_h264_default_range(',text)
        self.assertIn("legacy_color.resolve(before,sampled,'inspect')",text)
        self.assertIn("root/'engine.json'",text)


if __name__=='__main__':unittest.main()
