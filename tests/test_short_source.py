import unittest
from auto_optimize import reference_plan


class ShortSourceTests(unittest.TestCase):
    def test_selector_requires_complete_source_identity_for_single_reference(self):
        from codec_selection import select_candidate
        report=dict(schema='muxmender-codec-trials-v1',source_id='a'*64,source_bytes=100,
                    color_mode='sdr',references=[dict(id='0',bytes=100,whole_source=True,sha256='a'*64)],trials=[])
        self.assertEqual(select_candidate(report)['action'],'keep_original')
        for key,value in [('whole_source',False),('sha256','b'*64),('bytes',99)]:
            ref=report['references'][0].copy();report['references'][0][key]=value
            with self.assertRaises(ValueError):select_candidate(report)
            report['references'][0]=ref

    def test_short_source_is_one_complete_reference(self):
        for duration in (0.04,0.5,3,5.999):
            self.assertEqual(reference_plan(duration,10),dict(seconds=duration,positions=[0.0],whole_source=True))

    def test_long_sources_keep_three_scene_sampling(self):
        for duration in (6,30,120):
            plan=reference_plan(duration,10)
            self.assertFalse(plan['whole_source'])
            self.assertEqual(len(plan['positions']),3)
            self.assertTrue(all(p+plan['seconds']<=duration for p in plan['positions']))

    def test_invalid_inputs_still_rejected(self):
        for duration,requested in [(0,10),(float('nan'),10),(1,0),(1,float('inf'))]:
            with self.assertRaises(ValueError):reference_plan(duration,requested)

    def test_long_form_uses_five_separated_sections(self):
        plan=reference_plan(3600,10)
        self.assertEqual(len(plan['positions']),5)
        self.assertTrue(all(b-a>plan['seconds'] for a,b in zip(plan['positions'],plan['positions'][1:])))
        self.assertLessEqual(plan['positions'][-1]+plan['seconds'],3600)
