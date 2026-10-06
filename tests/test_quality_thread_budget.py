import unittest

from auto_optimize import quality_graph
from hdr_auto import quality_graph as hdr_quality_graph


class QualityThreadBudgetTests(unittest.TestCase):
    def test_hdr_worker_count_keeps_rendering_alignment_and_prefix_identical(self):
        for count in (None,96,720):
            baseline=hdr_quality_graph('score.json','24000/1001',count)
            candidate=hdr_quality_graph('score.json','24000/1001',count,threads=4)
            self.assertEqual(candidate,baseline.replace('n_threads=2:','n_threads=4:'))
        for value in (0,8,True,'4'):
            with self.assertRaises(ValueError):hdr_quality_graph('score.json','24',threads=value)

    def test_default_is_unchanged(self):
        self.assertIn('libvmaf=n_threads=2:', quality_graph('score.json', '24000/1001'))

    def test_only_metric_worker_count_changes(self):
        for fields in (False, True):
            baseline=quality_graph('score.json','24000/1001',separate_fields=fields)
            candidate=quality_graph('score.json','24000/1001',separate_fields=fields,threads=4)
            self.assertEqual(candidate,baseline.replace('n_threads=2:','n_threads=4:'))

    def test_invalid_budget_cannot_become_auto_or_unbounded(self):
        for value in (0,-1,8,True,2.0,'4',None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                quality_graph('score.json','24/1',threads=value)


if __name__ == '__main__':
    unittest.main()
