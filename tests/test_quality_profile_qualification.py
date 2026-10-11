import unittest
from unittest.mock import patch
from tools import qualify_quality_profiles as qualification


class QualificationSafetyTests(unittest.TestCase):
    def test_default_original_and_all_nine_explicit_preset_profile_pairs(self):
        self.assertEqual(len(qualification.comparison_cases({})),3)
        matrix=qualification.comparison_cases(dict(preset_matrix=True))
        self.assertEqual(len(matrix),9)
        self.assertEqual(len(set(matrix)),9)
        self.assertEqual({p for p,n in matrix},{'tv1080','mobile720','small480'})
        for bad in ('true',1,None):
            with self.assertRaises(ValueError):qualification.comparison_cases(dict(preset_matrix=bad))

    def test_windows_cannot_run_gpu_or_media_payload(self):
        with patch.object(qualification.sys,'platform','win32'),patch.object(qualification.subprocess,'run') as process:
            with self.assertRaisesRegex(RuntimeError,'Linux research'):qualification.run()
        process.assert_not_called()
