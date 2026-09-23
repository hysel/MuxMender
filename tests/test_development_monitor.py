import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import sys
import unittest
from unittest.mock import patch

from tools.monitor_remote_research import REMOTE_TRACKED


@unittest.skipUnless(sys.platform == 'linux', 'Remote reader tests run on Linux only')
class DevelopmentMonitorTests(unittest.TestCase):
    def snapshot(self,root):
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture):exec(REMOTE_TRACKED,{'ROOTS':[str(root)]})
        return json.loads(capture.getvalue())[0]

    def test_latest_tracked_job_not_old_failed_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for label,record in [('old',dict(state='failed',started=1,finished=2)),
                                 ('new',dict(state='running',started=3,updated=time.time(),pid=os.getpid(),
                                             phase='Checking quality',stage_percent=42,workflow_stage='compare'))]:
                folder=root/label;folder.mkdir();(folder/'job.json').write_text(json.dumps(record))
            result=self.snapshot(root)
            self.assertEqual(result['state'],'running')
            self.assertEqual(result['completed'],0)
            self.assertEqual(result['stage_percent'],42)
            self.assertEqual(result['failures'],0)

    def test_keep_decision_is_not_validated_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'job.json').write_text(json.dumps(dict(state='completed',started=1,finished=2)))
            folder=root/'auto-fixture';folder.mkdir()
            (folder/'status.json').write_text(json.dumps(dict(state='trials-completed')))
            result=self.snapshot(root)
            self.assertEqual((result['validated'],result['retained'],result['failures']),(0,1,0))

    def test_missing_job_does_not_report_completion(self):
        with tempfile.TemporaryDirectory() as tmp,self.assertRaises(RuntimeError):self.snapshot(Path(tmp))

    def test_nested_workflow_output_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'job.json').write_text(json.dumps(dict(state='completed',started=1,finished=2)))
            folder=root/'generated'/'output'/'auto-fixture';folder.mkdir(parents=True)
            (folder/'status.json').write_text(json.dumps(dict(state='validated-copy-awaiting-playback')))
            self.assertEqual(self.snapshot(root)['validated'],1)

    def test_incomplete_evaluation_is_not_quality_keep(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'job.json').write_text(json.dumps(dict(state='completed',started=1,finished=2)))
            folder=root/'auto-fixture';folder.mkdir()
            (folder/'status.json').write_text(json.dumps(dict(state='trials-completed',decision=dict(reason_code='evaluation_inconclusive'))))
            result=self.snapshot(root)
            self.assertEqual(result['retained'],0)
            self.assertEqual(result['evaluation_errors'],1)

    def test_dead_remote_process_is_stale_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'job.json').write_text(json.dumps(dict(state='running',started=1,updated=time.time(),pid=0)))
            with patch('os.kill',side_effect=AssertionError('Signal calls are forbidden')):result=self.snapshot(root)
            self.assertEqual(result['updated'],0)
            self.assertEqual(result['completed'],0)


if __name__=='__main__':unittest.main()
