import unittest
from unittest.mock import patch
from media_workflow import file_age_settings, file_age_match
from ui.controls import PANEL, SCRIPT


class FileAgeTests(unittest.TestCase):
    def test_ui_has_labelled_age_controls_and_preview_invalidation(self):
        self.assertIn('for="file-age-unit"', PANEL)
        self.assertIn('for="file-age-value"', PANEL)
        self.assertIn('aria-describedby="file-age-help"', PANEL)
        self.assertIn("settings.age_unit=controlElement('file-age-unit').value", SCRIPT)
        self.assertIn("controlElement('file-age-value').addEventListener('input',invalidatePreview)", SCRIPT)

    def test_all_needs_no_creation_date(self):
        with patch('media_workflow.creation_time', side_effect=AssertionError):
            self.assertEqual(file_age_match('unused', {}), (True, None))

    def test_units_and_inclusive_boundaries(self):
        for unit, seconds in [('hours',3600),('days',86400),('weeks',604800)]:
            for birth, expected in [(2000000-seconds,True),(2000000,True),
                                     (2000000-seconds-1,False),(2000001,False)]:
                with patch('media_workflow.creation_time',return_value=birth):
                    self.assertEqual(file_age_match('x',file_age_settings(unit,1),2000000)[0],expected)

    def test_missing_birth_date_not_modified_date(self):
        with patch('media_workflow.creation_time',return_value=None):
            self.assertEqual(file_age_match('x',file_age_settings('days',1)),
                             (False,'creation_date_unavailable'))

    def test_invalid_settings(self):
        for unit,value in [('months',1),('hours',0),('days',True),('weeks',1.5),('days',None),('days',100001)]:
            with self.assertRaises(ValueError):file_age_settings(unit,value)
