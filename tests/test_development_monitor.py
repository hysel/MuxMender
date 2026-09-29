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

from tools.monitor_remote_research import REMOTE_TRACKED,entry_key


class MonitorIdentityTests(unittest.TestCase):
    def test_same_server_jobs_have_distinct_identity(self):
        a=dict(host='research',title='first');b=dict(host='research',title='second')
        self.assertNotEqual(entry_key(a),entry_key(b))
        a.update(id='stable',roots=['/work/new-root'])
        b.update(id='stable',title='renamed')
        self.assertEqual(entry_key(a),entry_key(b))


@unittest.skipUnless(sys.platform == 'linux', 'Remote reader tests run on Linux only')
class DevelopmentMonitorTests(unittest.TestCase):
    def test_service_pid_is_used_for_cross_container_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'job.json').write_text(json.dumps(dict(state='running',started=1,updated=123,pid=0)))
            for pid,expected in [(os.getpid(),123),(0,0)]:
                capture=io.StringIO()
                with patch('subprocess.check_output',return_value=str(pid)) as probe,contextlib.redirect_stdout(capture):
                    exec(REMOTE_TRACKED,{'ROOTS':[str(root)],'SERVICE_UNIT':'qualification.service'})
                self.assertEqual(json.loads(capture.getvalue())[0]['updated'],expected)
                self.assertEqual(probe.call_args.args[0],['systemctl','show','qualification.service','--property=MainPID','--value'])

    def test_finished_nested_fixture_cannot_hide_running_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for folder,record in [(root/'job-parent',dict(state='running',started=1,updated=time.time(),pid=os.getpid())),
                                  (root/'fixture'/'job-child',dict(state='completed',started=2,finished=3))]:
                folder.mkdir(parents=True);(folder/'job.json').write_text(json.dumps(record))
            self.assertEqual(self.snapshot(root)['state'],'running')

    def test_separate_roots_do_not_hide_older_running_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            roots=[Path(tmp)/name for name in ('running','finished')]
            for index,root in enumerate(roots):
                root.mkdir()
                (root/'job.json').write_text(json.dumps(dict(state='running' if index==0 else 'completed',
                    started=index+1,updated=time.time(),pid=os.getpid())))
            capture=io.StringIO()
            with contextlib.redirect_stdout(capture):exec(REMOTE_TRACKED,{'ROOTS':[str(r) for r in roots]})
            results=json.loads(capture.getvalue())
            self.assertEqual(len(results),2)
            self.assertEqual([r['state'] for r in results],['running','completed'])
            self.assertEqual(sum(r['completed'] for r in results),1)

    def test_live_child_supplies_stage_but_parent_controls_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            parent=root/'job-parent';parent.mkdir()
            child=root/'output'/'job-child';child.mkdir(parents=True)
            parent_record=dict(state='running',started=2,updated=200,pid=os.getpid(),phase='Wrapper')
            (parent/'job.json').write_text(json.dumps(parent_record))
            child_record=dict(state='running',started=3,updated=190,stage_updated=189,
                              phase='Checking frames',stage_percent=42,stage_eta=15,
                              detail='420 pictures checked',workflow_stage='validate')
            (child/'job.json').write_text(json.dumps(child_record))
            result=self.snapshot(root)
            self.assertEqual((result['state'],result['completed']),('running',0))
            self.assertEqual((result['phase'],result['stage_percent']),('Checking frames',42))
            self.assertEqual((result['updated'],result['stage_updated']),(190,189))
            # Neither a finished child nor an old attempt may hide the parent.
            for update in [dict(state='completed'),dict(state='running',started=1)]:
                child_record.update(update)
                (child/'job.json').write_text(json.dumps(child_record))
                self.assertEqual(self.snapshot(root)['phase'],'Wrapper')
            child_record.update(state='running',started=3,updated=0)
            (child/'job.json').write_text(json.dumps(child_record))
            self.assertEqual(self.snapshot(root)['updated'],0)
            parent_record.update(state='completed',finished=201)
            (parent/'job.json').write_text(json.dumps(parent_record))
            self.assertEqual(self.snapshot(root)['completed'],1)

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
            (folder/'status.json').write_text(json.dumps(dict(state='trials-completed',decision={'action':'keep_original'})))
            result=self.snapshot(root)
            self.assertEqual((result['validated'],result['retained'],result['failures']),(0,1,0))

    def test_successful_samples_are_not_size_quality_keeps_or_full_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'job.json').write_text(json.dumps(dict(state='completed',started=1,finished=2)))
            folder=root/'auto-fixture';folder.mkdir()
            (folder/'status.json').write_text(json.dumps(dict(state='trials-completed',decision={'action':'encode_copy'})))
            result=self.snapshot(root)
            self.assertEqual((result['validated'],result['retained'],result['failures']),(0,0,0))

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
