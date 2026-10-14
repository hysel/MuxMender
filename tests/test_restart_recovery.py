import json
import unittest
from unittest.mock import Mock
from restart_recovery import mark_shutdown,recover


class RestartTests(unittest.TestCase):
    def state(self):
        return dict(paused=False,jobs=[dict(id='a'*32,state='running',source='/media/example.mkv',
                    signature=[100,1],source_identity=[1,2,100,4,5],settings=dict(mode='encode',quality_profile='balanced'))])

    def test_persisted_shutdown_requeues_once_with_unchanged_settings(self):
        state=self.state();mark_shutdown(state)
        state=json.loads(json.dumps(state));old=state['jobs'][0]
        ids=recover(state,Mock(),'new-version')
        self.assertEqual(len(ids),1);self.assertFalse(state['paused'])
        new=state['jobs'][1]
        self.assertEqual(new['settings'],old['settings']);self.assertNotEqual(new['id'],old['id'])
        self.assertNotIn('output',new);self.assertEqual(new['state'],'pending')
        self.assertEqual(recover(state,Mock(),'new-version'),[])

    def test_completed_jobs_and_cancellation_never_retry(self):
        for outcome in ('replaced','awaiting-playback','skipped','failed','cancelled'):
            state=self.state();mark_shutdown(state);state['jobs'][0]['state']=outcome
            self.assertEqual(recover(state,Mock(),'v'),[])
        state=self.state();mark_shutdown(state);state['jobs'][0]['cancel_requested']=True
        self.assertEqual(recover(state,Mock(),'v'),[])

    def test_unplanned_crash_is_not_confused_with_graceful_upgrade(self):
        self.assertEqual(recover(self.state(),Mock(),'v'),[])

    def test_changed_source_and_publication_block_auto_retry(self):
        for field in ('publishing','publication_only',None):
            state=self.state();mark_shutdown(state)
            if field:state['jobs'][0][field]=True
            check=Mock(side_effect=ValueError('Source changed')) if field is None else Mock()
            self.assertEqual(recover(state,check,'v'),[])
            self.assertTrue(state['paused']);self.assertEqual(state['jobs'][0]['service_restart']['state'],'blocked')

    def test_manual_pause_survives_restart(self):
        state=self.state();state.update(paused=True,pause_origin='manual');mark_shutdown(state)
        recover(state,Mock(),'v');self.assertTrue(state['paused'])
        self.assertEqual(state['pause_origin'],'manual')

    def test_existing_request_blocks_duplicate(self):
        state=self.state();mark_shutdown(state)
        state['jobs'].append(dict(id='b'*32,state='pending',source='/media/example.mkv'))
        self.assertEqual(recover(state,Mock(),'v'),[])
