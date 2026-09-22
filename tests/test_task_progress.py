import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import task_progress as tp
from job_tracking import Job


class TaskProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_checksum_matches_and_reports_bytes(self):
        source=self.root/'file';source.write_bytes(b'abc'*100)
        with patch.object(tp,'progress') as report:
            self.assertEqual(tp.digest(source),hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertTrue(any('GB checked' in c.kwargs.get('detail','') for c in report.call_args_list))
        self.assertEqual(report.call_args.kwargs['stage_percent'],100)

    def test_bounded_timestamp_progress_normalizes_start(self):
        path=self.root/'frames';path.write_text('best_effort_timestamp_time=15|width=1920\n\n')
        percent,detail=tp.probe_status(path,20,5)
        self.assertEqual(percent,50)
        self.assertIn('10.0 seconds',detail)
        self.assertIsNone(tp.probe_status(path,None)[0])

    def test_probe_preserves_evidence_and_reports_completion(self):
        path=self.root/'frames'
        command=[sys.executable,'-c','print("best_effort_timestamp_time=1|width=1920")']
        with patch.object(tp,'progress') as report:
            tp.run_probe(command,path,'Checking',10,lambda:None,2)
        self.assertIn('width=1920',path.read_text())
        self.assertEqual(report.call_args.kwargs['stage_percent'],100)

    def test_json_frame_progress_and_missing_time(self):
        path=self.root/'frames.json'
        path.write_text('{\n "best_effort_timestamp_time": "15.000",\n "width":1920\n')
        self.assertEqual(tp.probe_status(path,20,5)[0],50)
        path.write_text('{\n "width":1920\n')
        self.assertIsNone(tp.probe_status(path,20)[0])

    def test_failed_probe_never_reports_success(self):
        with patch.object(tp,'progress') as report:
            with self.assertRaises(subprocess.CalledProcessError):
                tp.run_probe([sys.executable,'-c','raise SystemExit(2)'],self.root/'frames','Checking',10,lambda:None)
        self.assertFalse(any(c.kwargs.get('stage_percent')==100 for c in report.call_args_list))

    def test_timeout_stops_owned_child(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            tp.run_probe([sys.executable,'-c','import time;time.sleep(10)'],self.root/'frames','Checking',.05,lambda:None)

    def test_stage_clock_not_reset_by_heartbeat_or_repeated_updates(self):
        job=Job(self.root,'Test')
        job.save(phase='Scan');start=job.data['stage_started']
        job.save();job.save(phase='Scan',stage_percent=20)
        self.assertEqual(job.data['stage_started'],start)
        job.save(phase='Validate')
        self.assertGreaterEqual(job.data['stage_started'],start)


if __name__=='__main__':unittest.main()
