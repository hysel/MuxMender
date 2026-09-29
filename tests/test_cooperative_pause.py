import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from cooperative_pause import lease_reason, configured_lease, OwnedStagePause


class LeaseTests(unittest.TestCase):
    def test_expired_invalid_and_overlong_requests_release(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'lease.json'
            for value in ({'pause': True, 'expires_at': 99},
                          {'pause': True, 'expires_at': 161},
                          {'pause': True, 'expires_at': float('nan')}, [], {}):
                path.write_text(json.dumps(value))
                self.assertIsNone(lease_reason(path, 100))
            path.write_text('{')
            self.assertIsNone(lease_reason(path, 100))
            path.write_text(json.dumps({'pause': True, 'expires_at': 120, 'reason': 'Other GPU work'}))
            self.assertEqual(lease_reason(path, 100), 'Other GPU work')

    def test_no_implicit_enable_or_nested_orchestrator_suspension(self):
        self.assertIsNone(configured_lease(['ffmpeg'], {}))
        with patch('cooperative_pause.sys.platform', 'linux'):
            self.assertIsNone(configured_lease(['python3'], {'MUXMENDER_PAUSE_LEASE': '/work/pause'}))
            self.assertEqual(configured_lease(['ffmpeg'], {'MUXMENDER_PAUSE_LEASE': '/work/pause'}), '/work/pause')
        with patch('cooperative_pause.sys.platform', 'win32'):
            with self.assertRaises(RuntimeError):
                configured_lease(['ffmpeg'], {'MUXMENDER_PAUSE_LEASE': '/work/pause'})


@unittest.skipUnless(sys.platform.startswith('linux'), 'Signals are tested on Linux only')
class LinuxPauseTests(unittest.TestCase):
    def test_suspended_worker_dies_with_supervisor(self):
        import signal
        code = ('import sys,time,signal\nfrom cooperative_pause import launch_owned\n'
                'p=launch_owned([sys.executable,"-c","import time;time.sleep(60)"])\n'
                'p.send_signal(signal.SIGSTOP)\nprint(p.pid,flush=True)\ntime.sleep(60)')
        parent = subprocess.Popen([sys.executable, '-B', '-c', code], stdout=subprocess.PIPE, text=True)
        try:
            pid = int(parent.stdout.readline())
            parent.kill()
            parent.wait(timeout=5)
            deadline = time.monotonic()+3
            while time.monotonic()<deadline:
                try:
                    state = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]
                except FileNotFoundError:
                    break
                if state == 'Z':break
                time.sleep(.05)
            else:self.fail('Suspended worker survived supervisor death')
        finally:
            if parent.poll() is None:parent.kill()
            parent.wait()
            parent.stdout.close()

    def test_stage_excludes_paused_time_and_reports_resume(self):
        from native_pipeline import stage
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            lease = root/'lease'
            command = [sys.executable, '-c', 'import time\nfor i in range(1,7):\n print("frame="+str(i),flush=True);time.sleep(.1)\n']
            lease.write_text(json.dumps({'pause': True, 'expires_at': time.time()+1.5}))
            with patch('job_tracking.stage_progress') as report, patch('cooperative_pause.configured_lease', return_value=str(lease)):
                stage(command, 1, timeout=1.2, stall=.8)
            details = [c.kwargs.get('detail', '') for c in report.call_args_list]
            self.assertTrue(any(s.startswith('Paused:') for s in details))
            self.assertTrue(any(s.startswith('Resumed;') for s in details))

    def test_guard_can_cancel_suspended_stage(self):
        from native_pipeline import stage
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            lease = root/'lease'
            command = [sys.executable, '-c', 'import time;time.sleep(60)']
            lease.write_text(json.dumps({'pause': True, 'expires_at': time.time()+30}))
            started = time.monotonic()
            def cancel():
                if time.monotonic()-started > .4:
                    raise RuntimeError('Cancelled by test')
            with self.assertRaisesRegex(RuntimeError, 'Cancelled by test'), patch('cooperative_pause.configured_lease', return_value=str(lease)):
                stage(command, 1, timeout=5, stall=1, guard=cancel)
            self.assertLess(time.monotonic()-started, 3)

    def test_pause_freezes_owned_worker_and_expiry_resumes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            output, lease = root/'ticks', root/'lease'
            child = subprocess.Popen([sys.executable, '-c',
                'import time,sys\nf=open(sys.argv[1],"w")\nwhile True:\n f.write("x");f.flush();time.sleep(.02)', str(output)],
                start_new_session=True)
            pause = OwnedStagePause(child, lease)
            try:
                deadline = time.monotonic()+5
                while not output.exists() and time.monotonic()<deadline:
                    time.sleep(.02)
                lease.write_text(json.dumps({'pause': True, 'expires_at': time.time()+1}))
                self.assertTrue(pause.update())
                time.sleep(.1)
                size = output.stat().st_size
                time.sleep(.2)
                self.assertEqual(size, output.stat().st_size)
                time.sleep(.8)
                self.assertFalse(pause.update())
                time.sleep(.1)
                self.assertGreater(output.stat().st_size, size)
                self.assertGreater(pause.elapsed(), 1)
            finally:
                pause.resume()
                child.kill()
                child.wait()

    def test_refuses_nonisolated_child(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(5)'])
        try:
            import signal
            with self.assertRaisesRegex(RuntimeError, 'non-isolated'):
                OwnedStagePause(child, None)._signal(signal.SIGSTOP)
        finally:
            child.kill()
            child.wait()
