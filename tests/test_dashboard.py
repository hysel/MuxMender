import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from dashboard import Catalog, make_handler, progress, tail
from job_tracking import tracked_call


class DashboardTests(unittest.TestCase):
    def test_weighted_progress_and_stage_eta(self):
        data = progress('Stage (10-65% overall) [=====               ] 25.0% | elapsed 100s | ETA 300s\nMUXMENDER_PROGRESS=23.8\n')
        self.assertEqual(data['percent'], 23.8)
        self.assertEqual(data['stage_eta'], 300)

    def test_legacy_running_job_reads_log_and_final_report_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)/'reports'/'dv-full-20260905-104650-example'
            run.mkdir(parents=True)
            (run/'status.json').write_text(json.dumps(dict(phase='encode', percent=10, pid=123)))
            (run/'terminal.log').write_text('MUXMENDER_PROGRESS=57.1\n')
            with patch('dashboard.alive', return_value=True):
                job = Catalog(folder).snapshot()[0]
            self.assertEqual(job['state'], 'running')
            self.assertEqual(job['percent'], 57.1)
            (run/'validation.json').write_text(json.dumps(dict(status='verified-full-file-awaiting-playback', output=str(run/'missing.mkv'))))
            job = Catalog(folder).snapshot()[0]
            self.assertEqual(job['state'], 'verified')
            self.assertEqual(job['percent'], 100)
            self.assertTrue(job['awaiting_playback'])
            self.assertIn('Not present', job['output_state'])

    def test_dead_job_and_malformed_json(self):
        with tempfile.TemporaryDirectory() as folder:
            run=Path(folder)/'reports'/'job-test'; run.mkdir(parents=True)
            (run/'job.json').write_text(json.dumps(dict(state='running',pid=123,started=time.time(),updated=time.time())))
            (run/'status.json').write_text('{')
            with patch('dashboard.alive', return_value=False):
                self.assertEqual(Catalog(folder).snapshot()[0]['state'], 'interrupted')

    def test_tracked_cli_keeps_result_and_log(self):
        with tempfile.TemporaryDirectory() as folder:
            def work():
                print('MUXMENDER_PROGRESS=42.0')
                return 0
            self.assertEqual(tracked_call(work, 'Test job', Path(folder)/'reports'), 0)
            catalog=Catalog(folder); job=catalog.snapshot()[0]
            self.assertEqual(job['state'], 'completed')
            self.assertEqual(job['percent'], 100)
            self.assertIn('42.0',tail(catalog.logs[job['id']]))

    def test_http_read_only_and_path_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Catalog(folder)))
            worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            try:
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
                for method,path,status in [('GET','/',200),('GET','/api/jobs',200),('GET','/api/log?id=../../secrets',404),('GET','/../secret',404),('POST','/api/jobs',501)]:
                    connection.request(method,path); response=connection.getresponse()
                    self.assertEqual(response.status,status); response.read()
                connection.request('GET','/api/jobs',headers={'Host':'evil.example'})
                response=connection.getresponse(); self.assertEqual(response.status,403); response.read()
                connection.close()
            finally:
                server.shutdown(); server.server_close(); worker.join()

    def test_linked_run_deduplicated_and_completed_tracker_not_running(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); job=root/'reports'/'job-example'; run=root/'reports'/'dv-example'
            job.mkdir(parents=True); run.mkdir()
            (job/'job.json').write_text(json.dumps(dict(state='completed', linked_run=str(run), pid=123, updated=time.time())))
            (run/'status.json').write_text(json.dumps(dict(phase='finished',percent=100,pid=123)))
            with patch('dashboard.alive', return_value=True):
                jobs=Catalog(folder).snapshot()
            self.assertEqual(len(jobs),1)
            self.assertEqual(jobs[0]['state'],'completed')

    def test_external_paths_are_not_served(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as external:
            run=Path(folder)/'reports'/'job-example'; run.mkdir(parents=True)
            (run/'job.json').write_text(json.dumps(dict(state='completed',linked_run=external)))
            (Path(external)/'validation.json').write_text(json.dumps(dict(status='failed',source='private')))
            job=Catalog(folder).snapshot()[0]
            self.assertIsNone(job['source'])
            self.assertEqual(job['state'],'completed')

    def test_tracked_exception_persists_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            def fail():
                raise RuntimeError('test')
            with self.assertRaises(RuntimeError):
                tracked_call(fail, 'Failure fixture', Path(folder)/'reports')
            self.assertEqual(Catalog(folder).snapshot()[0]['state'],'failed')

    def test_structured_progress_does_not_reuse_previous_stage_100(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)/'reports'/'job-progress'; run.mkdir(parents=True)
            (run/'job.json').write_text(json.dumps(dict(state='running', pid=123,
                updated=time.time(), progress_kind='structured', percent=50,
                completed=1, total=2, stage_percent=None, stage_eta=None,
                phase='Checking output')))
            (run/'terminal.log').write_text('MUXMENDER_PROGRESS=100\n')
            (run/'validation.json').write_text(json.dumps(dict(status='running')))
            with patch('dashboard.alive', return_value=True):
                job = Catalog(folder).snapshot()[0]
            self.assertEqual(job['percent'], 50)
            self.assertIsNone(job['stage_percent'])
            self.assertEqual(job['completed'], 1)
            self.assertEqual(job['phase'], 'Checking output')

    def test_dashboard_has_no_animated_progress(self):
        from dashboard_ui import HTML
        self.assertNotIn('<progress', HTML)
        self.assertNotIn('@keyframes', HTML)
        self.assertNotIn('animation:', HTML)
        self.assertNotIn('transition:width', HTML)

    def test_completed_scan_with_errors_is_not_interrupted(self):
        from job_tracking import progress as update
        with tempfile.TemporaryDirectory() as folder:
            def work():
                update('Scan complete', 4, 4, unit='files', completion_state='completed-with-errors')
                return 1
            self.assertEqual(tracked_call(work, 'Scan', Path(folder)/'reports'), 1)
            job = Catalog(folder).snapshot()[0]
            self.assertEqual(job['state'], 'completed-with-errors')
            self.assertEqual(job['percent'], 100)
