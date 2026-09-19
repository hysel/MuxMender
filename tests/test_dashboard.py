import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from dashboard import Catalog, make_handler, progress, tail, apply_outcome, file_savings, batch_savings
from job_tracking import tracked_call


class DashboardTests(unittest.TestCase):
    def test_codec_run_identity_source_and_execution_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            run=root/'auto-test';run.mkdir()
            job=root/'job-20260916-123821-example';job.mkdir()
            source='/media/TV/Example/episode.mkv'
            (job/'job.json').write_text(json.dumps(dict(title='Measured codec selection',
                state='completed',linked_run=str(run),started=1,updated=2)))
            (run/'status.json').write_text(json.dumps(dict(state='trials-completed',source=source,
                decision=dict(action='keep_original',reason='Quality threshold not met'))))
            (run/'plan.json').write_text(json.dumps(dict(hevc_nvenc_cq=[22,23,24])))
            rows=Catalog(root,[root]).snapshot()
            self.assertEqual(len(rows),1)
            row=rows[0]
            self.assertEqual(row['source'],source)
            self.assertIn('HEVC CQ 22/23/24',row['title'])
            self.assertIn('episode.mkv',row['title'])
            self.assertIn('123821-example',row['title'])
            self.assertEqual(row['state'],'skipped')
            self.assertEqual(row['execution_state'],'completed')
            self.assertEqual(row['detail'],'Quality threshold not met')

    def test_external_scan_job_discovery_and_live_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);repo=base/'repo';repo.mkdir();external=base/'external'
            job=external/'Library-Scans'/'job-test';job.mkdir(parents=True)
            run=external/'Library-Scans'/'scan-test';run.mkdir()
            record=dict(title='Read-only library scan',state='running',pid=1,started=time.time(),updated=time.time(),linked_run=str(run),phase='Read-only scan',percent=22.5)
            (job/'job.json').write_text(json.dumps(record))
            (job/'terminal.log').write_text('MUXMENDER_PROGRESS=22.5\n')
            with patch('dashboard.alive',return_value=True):
                self.assertEqual(Catalog(repo).snapshot(),[])
                catalog=Catalog(repo,[external]);jobs=catalog.snapshot()
                self.assertEqual(len(jobs),1)
                self.assertEqual(jobs[0]['percent'],22.5)
                self.assertEqual(catalog.logs[jobs[0]['id']],job/'terminal.log')
                record['percent']=45;(job/'job.json').write_text(json.dumps(record))
                (job/'terminal.log').write_text('MUXMENDER_PROGRESS=45\n')
                catalog.cached_at=0
                self.assertEqual(catalog.snapshot()[0]['percent'],45)
    def test_file_savings_requires_final_valid_result(self):
        for status in ('running', 'failed', 'cancelled', ''):
            self.assertIsNone(file_savings(dict(status=status, total_savings_percent=90)))
        for value in (True, '70', float('nan'), float('inf'), 101, None):
            self.assertIsNone(file_savings(dict(status='verified', total_savings_percent=value)))
        self.assertEqual(file_savings(dict(status='validated-experimental-full-file-awaiting-playback', total_savings_percent=70.2)), 70.2)
        self.assertEqual(file_savings(dict(status='verified', total_savings_percent=-10)), -10)

    def test_batch_savings_weighted_and_excludes_pending_or_cached(self):
        rows = [dict(status='validated-copy', fingerprint=dict(size=100), savings_percent=80),
                dict(status='validated-copy', fingerprint=dict(size=300), savings_percent=40)]
        for state in ('converting', 'failed-retained', 'already-validated'):
            rows.append(dict(status=state, fingerprint=dict(size=9000), savings_percent=99))
        self.assertEqual(batch_savings(dict(entries=rows)), dict(percent=50, files=2))
        self.assertIsNone(batch_savings(dict(entries=[])))

    def test_explicit_external_artifact_root_exposes_savings_only_when_allowed(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as external:
            run = Path(folder)/'reports'/'job'; run.mkdir(parents=True)
            (run/'job.json').write_text(json.dumps(dict(state='completed', linked_run=external)))
            (Path(external)/'validation.json').write_text(json.dumps(dict(status='verified', total_savings_percent=66.5)))
            self.assertIsNone(Catalog(folder).snapshot()[0]['file_savings_percent'])
            self.assertEqual(Catalog(folder, [external]).snapshot()[0]['file_savings_percent'], 66.5)

    def test_unfinished_validation_cannot_revive_finished_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); run=root/'reports'/'run';run.mkdir(parents=True)
            (run/'validation.json').write_text(json.dumps(dict(status='running')))
            for state in ('completed','failed','interrupted'):
                result=apply_outcome(dict(state=state,phase='Last completed step'),run,root)
                self.assertEqual(result['state'],state)
                self.assertTrue(result['validation_pending'])
                self.assertEqual(result['result']['status'],'running')

    def test_revalidation_review_and_cleanup_preserve_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);run=root/'reports'/'run';run.mkdir(parents=True)
            initial=dict(state='failed',error='old mismatch')
            (run/'job.json').write_text(json.dumps(initial))
            (run/'validation.json').write_text(json.dumps(dict(status='failed',finished=1,error='old mismatch')))
            report=dict(status='verified-full-file-awaiting-playback',finished=2,output=str(run/'missing.mkv'))
            (run/'revalidation-ok.json').write_text(json.dumps(report))
            data=apply_outcome(initial,run,root)
            self.assertEqual(data['state'],'verified')
            self.assertEqual(data['execution_error'],'old mismatch')
            (run/'playback-review.json').write_text(json.dumps(dict(approved=True,validation_report='wrong.json')))
            self.assertEqual(apply_outcome(initial,run,root)['state'],'verified')
            (run/'playback-review.json').write_text(json.dumps(dict(approved=True,validation_report='revalidation-ok.json')))
            data=apply_outcome(initial,run,root)
            self.assertEqual(data['state'],'playback-approved')
            self.assertFalse(data['awaiting_playback'])
            self.assertIn('output removed',data['phase'])
            self.assertEqual(json.loads((run/'job.json').read_text()),initial)
            self.assertEqual(apply_outcome(dict(state='running'),run,root)['state'],'running')
            (run/'revalidation-new.json').write_text(json.dumps(dict(status='failed',finished=3,error='new failure')))
            self.assertEqual(apply_outcome(initial,run,root)['state'],'failed')

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

    def test_current_encoder_log_fills_missing_structured_eta(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)/'reports'/'job-eta'; run.mkdir(parents=True)
            (run/'job.json').write_text(json.dumps(dict(state='running', pid=123,
                updated=time.time(), progress_kind='structured', percent=0,
                phase='Encoding video', stage_percent=None, stage_eta=None)))
            (run/'terminal.log').write_text('Encoding [==                  ] 10.0% | elapsed 20s | ETA 180s\nEncoding [====                ] 20.0% | elapsed 40s | ETA 160s\n')
            with patch('dashboard.alive', return_value=True):
                job = Catalog(folder).snapshot()[0]
            self.assertEqual(job['percent'], 0)
            self.assertEqual(job['stage_percent'], 20)
            self.assertEqual(job['stage_eta'], 160)

    def test_dashboard_has_no_animated_progress(self):
        from dashboard import HTML
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
