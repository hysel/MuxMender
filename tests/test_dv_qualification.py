import copy
import unittest
from dv_qualification import assess,parse_args


class QualificationTests(unittest.TestCase):
    def test_current_savings_default_and_explicit_options(self):
        base=['--source','fixture.mkv','--work-dir','work','--cq','29','--dovi-tool','dovi_tool']
        self.assertEqual(parse_args(base).minimum_savings_percent,25)
        for minimum in (25,20,15,10):
            self.assertEqual(parse_args(base+['--minimum-savings-percent',str(minimum)]).minimum_savings_percent,minimum)
        for minimum in ('nan','inf','-1','100'):
            with self.assertRaises(SystemExit):parse_args(base+['--minimum-savings-percent',minimum])

    def test_savings_threshold_boundary_and_no_publication(self):
        reports=self.reports()
        for r in reports:r['output_video_bytes']=75
        self.assertTrue(assess(reports,25)['eligible'])
        reports[0]['output_video_bytes']=76
        self.assertFalse(assess(reports,25)['eligible'])
        self.assertTrue(assess(reports,20)['eligible'])
        self.assertFalse(assess(reports,20)['publication_authorized'])

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
