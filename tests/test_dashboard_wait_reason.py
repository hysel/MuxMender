import unittest
from types import SimpleNamespace
from app_service import standalone_wait_reason
from ui.controls import SCRIPT


class DashboardWaitReasonTests(unittest.TestCase):
    def test_names_external_work_not_queue_owned_work(self):
        jobs=[dict(state='running',directory='ui-requests/request-a/job',title='Queue movie')]
        catalog=SimpleNamespace(snapshot=lambda:jobs)
        self.assertFalse(standalone_wait_reason(catalog))
        jobs.append(dict(state='running',directory='dv-test/run',title='Dolby Vision test'))
        reason=standalone_wait_reason(catalog)
        self.assertIn('Dolby Vision test',reason)
        self.assertNotIn('Queue movie',reason)
        self.assertIn('reported active',reason)
        self.assertIn('recovery',reason)

    def test_separate_gpu_engines_and_unknown_not_zero(self):
        for field in ('gpu_compute_percent','gpu_encode_percent','gpu_decode_percent','available_gib'):
            self.assertIn(field,SCRIPT)
        self.assertIn("suffix:'Unavailable'",SCRIPT)
