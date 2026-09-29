import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from control_service import Controls


class QueueCancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.media=root/'media';self.output=root/'output'
        self.media.mkdir();self.output.mkdir()
        self.source=self.media/'fixture.mkv';self.source.write_bytes(b'original fixture')
        self.controls=Controls(self.media,self.output,lambda _:True,['hevc'])
        self.controls.ready=True

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
