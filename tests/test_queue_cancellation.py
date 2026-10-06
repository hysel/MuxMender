import copy
from pathlib import Path
import tempfile
import unittest
import sys
import subprocess
from unittest.mock import patch
from control_service import Controls


class QueueCancellationTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'),'Linux process ownership and signals only')
    def test_owned_active_worker_stops_but_publisher_is_not_signalled(self):
        job=dict(self.enqueue(),id='owned-worker',state='running',cancel_requested=True)
        self.controls.state['jobs'].append(job)
        child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
        self.controls.children[job['id']]=child
        try:
            self.controls.cancel_child(job['id'],child)
            self.assertIsNotNone(child.poll())
            child2=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
            self.controls.children[job['id']]=child2;job['publishing']=True
            try:
                self.controls.cancel_child(job['id'],child2)
                self.assertIsNone(child2.poll())
            finally:child2.terminate();child2.wait(timeout=5)
        finally:
            if child.poll() is None:child.terminate();child.wait(timeout=5)

    def test_active_cancellation_pauses_and_signals_only_owned_nonpublisher(self):
        from unittest.mock import Mock
        waiting=self.enqueue()
        active=dict(copy.deepcopy(waiting),id='active-fixture',state='running')
        publisher=dict(copy.deepcopy(waiting),id='publisher-fixture',state='running',publishing=True)
        self.controls.state['jobs'].extend([active,publisher])
        child=Mock();child.poll.return_value=None
        self.controls.children.update({'active-fixture':child,'publisher-fixture':Mock()})
        preview=self.controls.action(dict(action='clear-queue-preview',include_running=True))
        with patch('control_service.threading.Thread') as thread:
            result=self.confirm(preview)
        self.assertEqual(result['stopping'],2)
        self.assertEqual(result['cancelled'],1)
        self.assertTrue(self.controls.state['paused'])
        self.assertTrue(active['cancel_requested']);self.assertTrue(publisher['cancel_requested'])
        self.assertEqual(thread.call_count,1)
        self.assertEqual(thread.call_args.kwargs['args'],('active-fixture',child))
        self.assertEqual(active['state'],'running')
        self.assertEqual(self.source.read_bytes(),b'original fixture')

    def test_active_cancel_save_failure_does_not_signal_or_mutate(self):
        waiting=self.enqueue();active=dict(copy.deepcopy(waiting),id='active',state='running')
        self.controls.state['jobs'].append(active)
        preview=self.controls.action(dict(action='clear-queue-preview',include_running=True))
        with patch.object(self.controls,'save',side_effect=OSError('disk')),patch('control_service.threading.Thread') as thread:
            with self.assertRaises(OSError):self.confirm(preview)
        self.assertFalse(self.controls.state['paused']);self.assertNotIn('cancel_requested',active)
        self.assertEqual(waiting['state'],'pending');thread.assert_not_called()

    def test_new_request_starts_after_cancel_without_reviving_cancelled_jobs(self):
        previous=self.enqueue()
        preview=self.controls.action(dict(action='clear-queue-preview',include_running=True))
        self.confirm(preview)
        self.assertEqual(self.controls.state.get('pause_origin'),'cancellation')
        draft=self.controls.preview(dict(path='fixture.mkv',mode='encode'))
        result=self.controls.submit(draft['preview_id'])
        self.assertTrue(result['auto_started'])
        self.assertFalse(self.controls.state['paused'])
        self.assertEqual(previous['state'],'cancelled')
        self.assertEqual(self.controls.state['jobs'][-1]['state'],'pending')

    def test_manual_pause_is_not_overridden_by_cancel_then_submit(self):
        self.enqueue();self.controls.action(dict(action='pause'))
        self.confirm(self.controls.action(dict(action='clear-queue-preview',include_running=True)))
        self.enqueue()
        self.assertTrue(self.controls.state['paused'])
        self.assertEqual(self.controls.state['pause_origin'],'manual')

    def test_cancellation_pause_survives_restart_and_new_request_starts(self):
        previous=self.enqueue()
        self.confirm(self.controls.action(dict(action='clear-queue-preview',include_running=True)))
        restored=Controls(self.media,self.output,lambda _:True,['hevc']);restored.ready=True
        draft=restored.preview(dict(path='fixture.mkv',mode='encode'))
        self.assertTrue(restored.submit(draft['preview_id'])['auto_started'])
        self.assertFalse(restored.state['paused'])
        self.assertEqual(restored.state['jobs'][0]['id'],previous['id'])
        self.assertEqual(restored.state['jobs'][0]['state'],'cancelled')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.media=root/'media';self.output=root/'output'
        self.media.mkdir();self.output.mkdir()
        self.source=self.media/'fixture.mkv';self.source.write_bytes(b'original fixture')
        self.controls=Controls(self.media,self.output,lambda _:True,['hevc'])
        self.controls.ready=True

    def test_keep_only_request_does_not_restart_processing(self):
        self.enqueue()
        self.confirm(self.controls.action(dict(action='clear-queue-preview',include_running=True)))
        draft=self.controls.preview(dict(path='fixture.mkv',mode='keep'))
        result=self.controls.submit(draft['preview_id'])
        self.assertFalse(result['auto_started'])
        self.assertTrue(self.controls.state['paused'])

    def test_explicit_pause_after_cancellation_still_requires_resume(self):
        self.enqueue()
        self.confirm(self.controls.action(dict(action='clear-queue-preview',include_running=True)))
        self.controls.action(dict(action='pause'))
        self.enqueue()
        self.assertTrue(self.controls.state['paused'])
        self.assertEqual(self.controls.state['pause_origin'],'manual')

    def enqueue(self):
        preview=self.controls.preview(dict(path='fixture.mkv',mode='encode'))
        self.controls.submit(preview['preview_id'])
        return self.controls.state['jobs'][-1]

    def preview(self):
        return self.controls.action(dict(action='clear-queue-preview'))

    def confirm(self,preview):
        return self.controls.action(dict(action='clear-queue-confirm',confirmation_id=preview['confirmation_id']))

    def test_cancels_waiting_only_and_can_readd_after_restart(self):
        pending=self.enqueue()
        running=dict(copy.deepcopy(pending),id='running-fixture',state='running')
        finished=dict(copy.deepcopy(pending),id='finished-fixture',state='failed')
        self.controls.state['jobs'].extend([running,finished])
        before=copy.deepcopy([running,finished]);paused=self.controls.state['paused']
        preview=self.preview()
        self.assertEqual(preview['count'],1)
        self.assertEqual(pending['state'],'pending')
        result=self.confirm(preview)
        self.assertEqual(result['cancelled'],1)
        self.assertEqual(pending['state'],'cancelled')
        self.assertEqual([running,finished],before)
        self.assertEqual(self.controls.state['paused'],paused)
        self.assertEqual(self.source.read_bytes(),b'original fixture')
        restored=Controls(self.media,self.output,lambda _:True,['hevc'])
        self.assertEqual(restored.state['jobs'][0]['state'],'cancelled')
        # Isolate this file's cancelled record from the synthetic running claim.
        self.assertIsNone(restored.history_match(str(self.source),pending['signature'],pending['settings'],candidates=[pending]))
        with self.assertRaises(ValueError):self.confirm(preview)

    def test_new_jobs_and_jobs_started_after_preview_are_not_cancelled(self):
        job=self.enqueue();preview=self.preview()
        job['state']='running'
        added=dict(copy.deepcopy(job),id='added-after-confirmation',state='pending')
        self.controls.state['jobs'].append(added)
        result=self.confirm(preview)
        self.assertEqual(result['cancelled'],0)
        self.assertEqual(result['remaining'],1)
        self.assertEqual(job['state'],'running')
        self.assertEqual(added['state'],'pending')

    def test_expired_unconfirmed_and_not_ready_requests_change_nothing(self):
        job=self.enqueue();preview=self.preview()
        self.controls.queue_clear_drafts[preview['confirmation_id']]['expires']=0
        with self.assertRaises(ValueError):self.confirm(preview)
        with self.assertRaises(ValueError):self.controls.action(dict(action='clear-queue-confirm'))
        self.controls.ready=False
        with self.assertRaises(ValueError):self.preview()
        self.assertEqual(job['state'],'pending')

    def test_save_failure_rolls_back_and_retains_confirmation(self):
        job=self.enqueue();preview=self.preview();before=copy.deepcopy(job)
        with patch.object(self.controls,'save',side_effect=OSError('test disk failure')):
            with self.assertRaises(OSError):self.confirm(preview)
        self.assertEqual(job,before)
        self.assertEqual(self.confirm(preview)['cancelled'],1)

    def test_empty_queue_and_preview_limit(self):
        preview=self.preview();self.assertEqual(preview['count'],0)
        self.assertEqual(self.confirm(preview)['cancelled'],0)
        for _ in range(20):self.preview()
        with self.assertRaises(ValueError):self.preview()

    def test_ui_confirmation_and_feedback_are_in_overview(self):
        from ui.app import HTML
        self.assertIn('id="clear-waiting-queue"',HTML)
        self.assertIn('<dialog id="queue-clear-dialog"',HTML)
        self.assertIn('id="queue-clear-cancel" type="button" autofocus',HTML)
        self.assertIn('clear-queue-preview',HTML)
        self.assertIn('clear-queue-confirm',HTML)
