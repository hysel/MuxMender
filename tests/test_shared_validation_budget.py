import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation_resources import bounded_reader,reader_threads,validation_rank,validation_slot,validation_limited


class SharedBudgetTests(unittest.TestCase):
    def test_budget_changes_threads_not_checks_or_source_paths(self):
        command=['ffmpeg','-threads','4','-i','n_threads=4.mkv','-filter_complex',
                 'libvmaf=n_threads=4:model=x:log_fmt=json','-xerror','-f','null','-']
        actual=bounded_reader(command,2)
        self.assertEqual(actual[actual.index('-i')+1],'n_threads=4.mkv')
        self.assertIn('libvmaf=n_threads=2:model=x:log_fmt=json',actual)
        self.assertIn('-xerror',actual)
        self.assertEqual(reader_threads(command),4)
        self.assertEqual(command[2],'4','Caller command must not be mutated')

    def test_final_priority_has_age_bound_and_unknown_tickets_keep_fifo(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial=Path(tmp)/'wait-00000000000000000001-trial.lock'
            final=Path(tmp)/'wait-00000000000000000002-final.lock'
            trial.write_text(json.dumps(dict(started=0,final=False)))
            final.write_text(json.dumps(dict(started=1,final=True)))
            self.assertLess(validation_rank(final,10),validation_rank(trial,10))
            self.assertLess(validation_rank(trial,31),validation_rank(final,31))
            trial.write_text('')
            self.assertLess(validation_rank(trial,10),validation_rank(final,10))

    def test_decorator_executes_adjusted_command_not_original(self):
        from contextlib import contextmanager
        @contextmanager
        def allocation(*args,**kwargs):yield 2
        @validation_limited
        def reader(command,timeout=7):return command,timeout
        with patch('validation_resources.validation_slot',allocation):
            actual,timeout=reader(['ffprobe','-threads','4','-show_frames'])
        self.assertEqual(actual,['ffprobe','-threads','2','-show_frames'])
        self.assertEqual(timeout,7)

    @unittest.skipUnless(os.name=='posix','OS leases require Linux')
    def test_healthy_budget_fits_two_four_thread_readers_not_three(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.AdmissionBudget.sample',return_value=2):
            with validation_slot(['ffprobe','-threads','4','-show_frames']) as limit:
                self.assertEqual(limit,4)
                with validation_slot(['ffprobe','-threads','4','-show_frames'],timeout=0) as second:
                    self.assertEqual(second,4)
                    with self.assertRaises(TimeoutError):
                        with validation_slot(['ffprobe','-threads','2','-show_frames'],timeout=0):pass
            with validation_slot(['ffprobe','-threads','2','-show_frames']) as first:
                with validation_slot(['ffprobe','-threads','4','-show_frames'],timeout=0) as second:
                    self.assertEqual((first,second),(2,4))

    @unittest.skipUnless(os.name=='posix','OS leases require Linux')
    def test_single_capacity_reservation_is_not_mistaken_for_legacy_worker(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.AdmissionBudget.sample',return_value=1):
            with validation_slot(['ffprobe','-threads','4','-show_frames'],timeout=0) as limit:
                self.assertEqual(limit,4)

    @unittest.skipUnless(os.name=='posix','OS leases require Linux')
    def test_legacy_slot_counts_as_unknown_full_budget(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.AdmissionBudget.sample',return_value=2):
            with (Path(tmp)/'heavy-reader.lock').open('w') as held:
                fcntl.flock(held,fcntl.LOCK_EX)
                with self.assertRaises(TimeoutError):
                    with validation_slot(['ffprobe','-threads','2','-show_frames'],timeout=0):pass

    @unittest.skipUnless(os.name=='posix','OS leases require Linux')
    def test_final_gpu_validation_does_not_yield_to_trial_backlog(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.live_waiters',return_value=2),patch('job_tracking.current_workflow_stage',return_value='validate'):
            with validation_slot(['ffmpeg','-filter_complex','libplacebo'],pool='gpu',estimated_duration=30,timeout=0):pass

    @unittest.skipUnless(os.name=='posix','OS leases require Linux')
    def test_bad_token_path_releases_partial_allocations(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.AdmissionBudget.sample',return_value=1):
            target=Path(tmp)/'untouched';target.write_text('fixture')
            linked=Path(tmp)/'cpu-token-1.lock';linked.symlink_to(target)
            with self.assertRaises(OSError):
                with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
            linked.unlink()
            with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
            self.assertEqual(target.read_text(),'fixture')

    @unittest.skipUnless(os.name=='posix','OS leases require Linux')
    def test_trial_gpu_backlog_wait_is_cancellable_and_age_bounded(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.live_waiters',return_value=2):
            with self.assertRaises(TimeoutError):
                with validation_slot(['ffmpeg','-c:v','av1_nvenc'],pool='gpu',estimated_duration=30,timeout=0):pass
            with patch('validation_resources.time.monotonic',side_effect=[0]+[31]*100):
                with validation_slot(['ffmpeg','-c:v','av1_nvenc'],pool='gpu',estimated_duration=30,timeout=0):pass
