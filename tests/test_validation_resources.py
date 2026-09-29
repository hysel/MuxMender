import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
from validation_resources import heavy_reader,validation_slot,validation_limited


class ResourceTests(unittest.TestCase):
    def test_execution_timeout_not_used_for_admission(self):
        @validation_limited
        def reader(command,timeout,guard):return timeout
        guard=lambda:None
        with patch('validation_resources.validation_slot') as slot:
            self.assertEqual(reader(['ffprobe','-show_frames'],7,guard),7)
        slot.assert_called_once_with(['ffprobe','-show_frames'],guard)

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_unbounded_wait_remains_cancellable(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            with validation_slot(['ffprobe','-show_frames']):
                calls=[]
                def cancel():
                    calls.append(1)
                    if len(calls)==3:raise InterruptedError('cancelled')
                with patch('validation_resources.time.sleep'),patch('job_tracking.progress') as progress:
                    with self.assertRaises(InterruptedError):
                        with validation_slot(['ffprobe','-show_frames'],guard=cancel):
                            self.fail('Contended slot was admitted')
                    self.assertEqual(progress.call_count,2)
                    self.assertIsNone(progress.call_args.kwargs['stage_percent'])
            with validation_slot(['ffprobe','-show_frames'],timeout=0):pass

    def test_classification(self):
        self.assertTrue(heavy_reader(['ffprobe','-show_frames']))
        self.assertTrue(heavy_reader(['ffmpeg','-lavfi','libvmaf=model=x']))
        self.assertFalse(heavy_reader(['ffmpeg','-c:v','hevc_nvenc']))
        self.assertFalse(heavy_reader(['ffprobe','-show_packets']))

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_exclusive_and_released_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            with validation_slot(['ffprobe','-show_frames']):
                with self.assertRaises(TimeoutError):
                    with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
            with self.assertRaises(ValueError):
                with validation_slot(['ffprobe','-show_frames']):raise ValueError('test')
            with validation_slot(['ffprobe','-show_frames'],timeout=0):pass

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_linked_lock_refused(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            target=Path(tmp)/'keep';target.write_text('original')
            (Path(tmp)/'heavy-reader.lock').symlink_to(target)
            with self.assertRaises(OSError):
                with validation_slot(['ffprobe','-show_frames']):pass
            self.assertEqual(target.read_text(),'original')

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_process_death_releases_slot(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            code="from validation_resources import validation_slot\nimport sys\nwith validation_slot(['ffprobe','-show_frames']):\n print('ready',flush=True)\n sys.stdin.read()"
            child=subprocess.Popen([sys.executable,'-B','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'ready')
                child.kill();child.wait(timeout=5)
                with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
            finally:
                if child.poll() is None:child.kill();child.wait()
                child.stdin.close();child.stdout.close()
