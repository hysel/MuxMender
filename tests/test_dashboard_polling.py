import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from dashboard import Catalog


class DashboardPollingTests(unittest.TestCase):
    def test_slow_discovery_never_blocks_poll_or_starts_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory)
            entered=threading.Event();release=threading.Event();finished=threading.Event()
            def slow():
                entered.set();release.wait(2)
                catalog.jobs=[dict(id='history')];catalog.cached_at=time.time();finished.set()
            with patch.object(catalog,'snapshot',side_effect=slow) as scan:
                try:
                    start=time.monotonic();first=catalog.poll()
                    self.assertLess(time.monotonic()-start,.5)
                    self.assertEqual(first['jobs'],[])
                    self.assertTrue(entered.wait(1))
                    for _ in range(10):self.assertTrue(catalog.poll()['catalog_refreshing'])
                    self.assertEqual(scan.call_count,1)
                finally:
                    release.set();self.assertTrue(finished.wait(1))
                self.assertEqual(catalog.poll()['jobs'],[dict(id='history')])

    def test_live_read_does_not_walk_history_or_mutate_old_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.cached_at=time.time()
            old=dict(id='active',directory='run',state='running',updated=1,stage_percent=5)
            catalog.jobs=[old,dict(id='history',state='completed')]
            with patch.object(catalog,'snapshot') as scan,patch.object(catalog,'read',return_value=dict(state='running',updated=2,stage_percent=50)):
                catalog._refresh_poll()
            scan.assert_not_called()
            self.assertEqual(catalog.jobs[0]['stage_percent'],50)
            self.assertEqual(old['stage_percent'],5)
            self.assertEqual(catalog.jobs[1],dict(id='history',state='completed'))

    def test_failed_refresh_retains_evidence_and_reports_error(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.jobs=[dict(id='old',updated=1)]
            with patch.object(catalog,'snapshot',side_effect=OSError('unavailable')):
                catalog._refresh_poll()
            result=catalog.poll()
            self.assertTrue(result['catalog_error'])
            self.assertEqual(result['jobs'][0]['updated'],1)
            self.assertFalse(result['catalog_refreshing'])

    def test_finished_live_job_requests_fresh_outcome_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.cached_at=time.time()
            catalog.jobs=[dict(directory='run',state='running')]
            with patch.object(catalog,'read',return_value=dict(state='completed')):catalog._refresh_poll()
            self.assertEqual(catalog.cached_at,0)

    def test_pollers_are_single_flight_and_separate_render_errors(self):
        from ui.workspace import SCRIPT as workspace
        from ui.controls import SCRIPT as controls
        self.assertIn('if(userPollBusy)return',workspace)
        self.assertIn('if(controlPollBusy)return',controls)
        for script in (workspace,controls):
            self.assertIn('AbortSignal.timeout(30000)',script)
            self.assertIn('received=true',script)
            self.assertIn('Display update failed',script)
