import copy
import unittest
from dv_qualification import assess


class QualificationTests(unittest.TestCase):
    def reports(self):
        return [dict(status='verified-structure', original_stat_unchanged=True,
                     original_video_bytes=100, output_video_bytes=50,
                     quality={'self': {'passed': True}, 'candidate': {'passed': True}})
                for _ in range(3)]

    def test_aggregate_savings_not_each_scene(self):
        reports = self.reports()
        reports[0]['output_video_bytes'] = 110
        decision = assess(reports, 10)
        self.assertTrue(decision['eligible'])
        self.assertFalse(decision['publication_authorized'])

    def test_each_scene_requires_quality_and_self_check(self):
        for key in ('self', 'candidate'):
            reports = self.reports()
            reports[2]['quality'][key]['passed'] = False
            before = copy.deepcopy(reports)
            self.assertFalse(assess(reports, 10)['eligible'])
            self.assertEqual(reports, before)

    def test_incomplete_preservation_rejected(self):
        reports = self.reports()
        reports[1]['original_stat_unchanged'] = False
        with self.assertRaises(ValueError): assess(reports, 10)
        with self.assertRaises(ValueError): assess(reports[:2], 10)
