import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('real_qualification', Path(__file__).resolve().parents[1]/'tools/qualify_ffmpeg_real.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OutcomeTests(unittest.TestCase):
    def test_validated_copy_requires_success(self):
        self.assertEqual(module.outcome({'state':'validated-copy-awaiting-playback'},0),'validated_copy')
        self.assertEqual(module.outcome({'state':'validated-copy-awaiting-playback'},1),'needs_attention')

    def test_completion_does_not_imply_validated_copy(self):
        self.assertEqual(module.outcome({'state':'trials-completed'},0),'needs_attention')
        self.assertEqual(module.outcome({'state':'trials-completed','decision':{'action':'keep_original','reason_code':'already_efficient_for_settings'}},0),'original_kept')
        self.assertEqual(module.outcome({'state':'trials-completed','decision':{'action':'keep_original','reason_code':'evaluation_inconclusive'}},0),'needs_attention')
        self.assertEqual(module.outcome({},0),'needs_attention')
        self.assertEqual(module.outcome({'state':'full-output-rejected-insufficient-savings'},0),'original_kept')


if __name__ == '__main__':
    unittest.main()
