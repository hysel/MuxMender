import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('av1_intermediate',Path(__file__).resolve().parents[1]/'tools'/'qualify_av1_intermediate.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class IntermediateTests(unittest.TestCase):
    def rows(self):return [dict(source_bytes=100,output_bytes=80,quality=dict(passed=True,mean=94,p5=90.1,frames=300)) for _ in range(5)]

    def test_all_scenes_quality_and_savings_required(self):
        rows=self.rows();self.assertTrue(module.sample_eligible(rows,10))
        self.assertFalse(module.sample_eligible(rows[:4],10))
        self.assertFalse(module.sample_eligible(rows,25))
        rows[-1]['quality']['p5']=89.9;self.assertFalse(module.sample_eligible(rows,10))

    def test_invalid_evidence_cannot_pass(self):
        for value in (float('nan'),float('inf'),True,None):
            rows=self.rows();rows[-1]['quality']['mean']=value
            self.assertFalse(module.sample_eligible(rows,10))
        rows=self.rows();rows[-1]['quality']['frames']=0
        self.assertFalse(module.sample_eligible(rows,10))

    def test_windows_guard(self):
        with patch.object(module.sys,'platform','win32'):
            with self.assertRaisesRegex(RuntimeError,'Linux image qualification only'):module.main()


if __name__=='__main__':unittest.main()
