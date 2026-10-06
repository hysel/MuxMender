"""Settings and evidence formatting tests; never launch media tools."""
import json
import subprocess
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from media_workflow import processing_timeout_minutes, automatic_arguments, main
from control_service import Controls
from decoder_context import hdr_reader_options
from hdr10plus_preserve import frame_records
from task_progress import probe_status, run_probe


class ProcessingTimeoutTests(unittest.TestCase):
    def test_settings_validate_and_old_jobs_keep_default(self):
        for bad in (0,-1,1441,True,2.5,'120',None):
            with self.assertRaises(ValueError):processing_timeout_minutes(bad)
        controls=SimpleNamespace(codecs=['hevc','av1'])
        settings=Controls.settings(controls,dict(mode='encode',timeout_minutes=360))
        command=automatic_arguments('input.mkv','output',settings)
        self.assertEqual(command[command.index('--timeout')+1],'21600')
        del settings['timeout_minutes']
        command=automatic_arguments('input.mkv','output',settings)
        self.assertEqual(command[command.index('--timeout')+1],'7200')

    def test_cli_budget_reaches_same_engine(self):
        with patch('auto_optimize.main',return_value=0) as engine:
            main(['input.mkv','--output-dir','output','--timeout-minutes','360'])
        command=engine.call_args.args[0]
        self.assertEqual(command[command.index('--timeout')+1],'21600')

    def test_reader_keeps_slice_context_and_all_metadata(self):
        with patch('resource_governor.hdr_validation_threads',return_value=4) as budget:
            self.assertEqual(hdr_reader_options(600),
                             ['-threads','4','-thread_type','slice','-show_frames','-of','json=compact=1'])
            budget.assert_called_once()
        with patch('resource_governor.hdr_validation_threads') as budget:
            self.assertIn('2',hdr_reader_options(10));budget.assert_not_called()

    def test_compact_evidence_preserves_duplicate_keys_and_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'frames.json'
            path.write_text('{"frames":[\n{"best_effort_timestamp_time":"30.0","side_data_list":[{"x":1,"x":2}]}\n]}')
            self.assertEqual(list(frame_records(path))[0]['side_data_list'][0]['x'],[1,2])
            percent,detail=probe_status(path,60)
            self.assertEqual(percent,50)
            self.assertIn('30.0 seconds',detail)

    def test_timeout_is_explained_and_reader_is_reaped(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('task_progress.subprocess.Popen') as launch, \
             patch('task_progress.time.monotonic',side_effect=[0,61,61]), \
             patch('task_progress.progress'),patch('task_progress.probe_status',return_value=(50,'30 seconds inspected')):
            with self.assertRaisesRegex(subprocess.TimeoutExpired,'configured 1-minute'):
                run_probe.__wrapped__(['ffprobe'],Path(directory)/'frames.json','HDR inspection',60,lambda:None)
            launch.return_value.kill.assert_called_once()
            launch.return_value.wait.assert_called_once()

    def test_reader_can_be_cancelled_while_yielding_without_signaling_host(self):
        # Entire owned-process interface is mocked: never send Linux signals here.
        with tempfile.TemporaryDirectory() as directory, \
             patch('cooperative_pause.configured_lease',return_value='/work/pause.json'), \
             patch('cooperative_pause.launch_owned') as launch, \
             patch('cooperative_pause.OwnedStagePause') as paused, \
             patch('task_progress.time.sleep'),patch('task_progress.progress') as report:
            paused.return_value.update.return_value=True
            paused.return_value.elapsed.return_value=0
            guard=unittest.mock.Mock(side_effect=[None,InterruptedError('Cancelled')])
            with self.assertRaisesRegex(InterruptedError,'Cancelled'):
                run_probe.__wrapped__(['ffprobe-cuda','-show_frames'],Path(directory)/'frames.json',
                                      'GPU inspection',60,guard,env={'reader':'enabled'})
            self.assertEqual(launch.call_args.kwargs['env'],{'reader':'enabled'})
            launch.return_value.kill.assert_called_once()
            launch.return_value.wait.assert_called_once()
            self.assertTrue(any('Paused:' in str(call) for call in report.call_args_list))

    def test_ui_exposes_and_invalidates_budget(self):
        from ui.app import HTML
        from ui.controls import SCRIPT
        self.assertIn('id="timeout-minutes"',HTML)
        self.assertIn('timeout_minutes:timeoutMinutes',SCRIPT)
        self.assertIn("controlElement('timeout-minutes').addEventListener('input',invalidatePreview)",SCRIPT)
