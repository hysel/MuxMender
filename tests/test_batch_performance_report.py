import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'tools'/'analyze_batch_performance.py'
spec=importlib.util.spec_from_file_location('batch_performance_report',path)
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


class BatchPerformanceReportTests(unittest.TestCase):
    def test_latest_batch_filters_history_and_duplicate_records(self):
        identifier='a'*32
        controls=dict(jobs=[dict(id=identifier,batch_id='new',created=2,state='replaced',
                    saved_bytes=1_000_000_000,artifact_cleanup=dict(state='cleaned')),
                    dict(id='b'*32,batch_id='old',created=1,state='failed')])
        job=dict(id='record',directory='ui-requests/request-'+identifier+'/job-fixture',
                 performance_seconds=dict(encoding=10,validation_wait=30))
        result=report.summarize(controls,dict(jobs=[job,job,dict(job,id='old',directory='unrelated')]))
        self.assertEqual(result['counts'],{'replaced':1})
        self.assertEqual(result['confirmed_saved_gb'],1)
        self.assertEqual(result['cleaned_replacements'],1)
        self.assertEqual(result['measured_records'],1)
        self.assertEqual(result['stage_share_percent']['validation_wait'],75)

    def test_bad_counters_cannot_poison_report_or_expose_paths(self):
        identifier='a'*32
        controls=dict(jobs=[dict(id=identifier,batch_id='batch',created=1,state='running')])
        counters={'encoding':float('nan'),'other':-1,'gpu_wait':True,'source/path':20}
        result=report.summarize(controls,dict(jobs=[dict(id='record',
               directory='request-'+identifier+'/job-fixture',performance_seconds=counters)]))
        self.assertEqual(result['observed_stage_seconds'],{})
        self.assertEqual(result['measured_records'],0)
        self.assertNotIn('source/path',str(result))

    def test_empty_batch_does_not_fabricate_completion(self):
        with self.assertRaises(ValueError):report.summarize(dict(jobs=[]),dict(jobs=[]))


if __name__=='__main__':unittest.main()
