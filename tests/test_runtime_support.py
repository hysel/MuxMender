import io
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import muxmender as mm
from runtime_support import TerminalProgress, check_dependencies
from runtime_support import guard_ordered_mux_memory
from unittest.mock import Mock


class RuntimeTests(unittest.TestCase):
    def test_partial_frame_audit_progress_is_bounded_and_optional(self):
        from runtime_support import frame_evidence_percent
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'frames.json'
            self.assertIsNone(frame_evidence_percent(path, 100))
            path.write_text('x'*70000+'{"best_effort_timestamp_time": "25.000000"},\n{"best_effort_timestamp_time": "26.')
            self.assertEqual(frame_evidence_percent(path,100),25.)
            path.write_text('frame|best_effort_timestamp_time=80.500000|interlaced_frame=0\n')
            self.assertEqual(frame_evidence_percent(path,100),80.5)
            self.assertEqual(frame_evidence_percent(path,10),99.9)
            self.assertIsNone(frame_evidence_percent(path,float('nan')))

    @patch('runtime_support.process_memory_bytes')
    def test_ordered_mux_memory_guard_fails_closed(self, memory):
        process = Mock(); process.poll.return_value = None
        command = ['ffmpeg', '-max_interleave_delta', '0', 'output.mkv']
        memory.return_value = 1024**3+1
        with self.assertRaisesRegex(RuntimeError, 'memory guard'):
            guard_ordered_mux_memory(process, command)
        memory.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            guard_ordered_mux_memory(process, command)
        memory.return_value = 100*1024**2
        guard_ordered_mux_memory(process, command)

    def test_ordered_mux_guard_stops_owned_process(self):
        command = [sys.executable, '-c', 'import time; time.sleep(10)',
                   '-max_interleave_delta', '0', 'unused']
        with patch('runtime_support.process_memory_bytes', return_value=1024**3+1), \
             patch('muxmender.stop_process_tree', wraps=mm.stop_process_tree) as stop:
            with self.assertRaisesRegex(RuntimeError, 'memory guard'):
                mm.run_ffmpeg(command, 10)
            stop.assert_called_once()
            self.assertIsNotNone(stop.call_args.args[0].poll())

    def test_eta_uses_recent_rate_and_resets_on_new_stage(self):
        with patch('runtime_support.time.monotonic') as clock:
            clock.return_value = 0
            bar = TerminalProgress(stream=io.StringIO())
            bar.update(0)
            self.assertIsNone(bar.eta_seconds)
            clock.return_value = 20
            bar.update(10)
            self.assertAlmostEqual(bar.eta_seconds, 180)
            clock.return_value = 150
            bar.update(30)
            clock.return_value = 170
            bar.update(40)
            self.assertAlmostEqual(bar.eta_seconds, 120)
            clock.return_value = 171
            bar.update(0)
            self.assertIsNone(bar.eta_seconds)

    def test_terminal_bar_eta_and_protocol(self):
        stream = io.StringIO()
        bar = TerminalProgress(stream=stream)
        bar.update(25)
        bar.update(25.1)
        bar.update(100)
        self.assertIn('[=====               ]', stream.getvalue())
        self.assertIn('ETA', stream.getvalue())
        self.assertEqual(stream.getvalue().count('MUXMENDER_PROGRESS='), 2)

    def test_never_delete_even_with_old_confirmation(self):
        self.assertEqual(mm.main(['unused.mkv', '--delete-originals', '--confirm-delete', 'DELETE_ORIGINALS']), 2)
        self.assertEqual(mm.main(['unused.mkv', '--overwrite-output']), 2)

    def test_rejects_nonfinite_numbers_before_opening_media(self):
        for args in (['--min-savings', 'nan'], ['--hardware-stall-timeout', 'inf']):
            self.assertEqual(mm.main(['unused.mkv', *args]), 2)

    def test_new_partials_and_atomic_publication(self):
        # Only generated text fixtures; never user media.
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'generated.txt'
            partial = Path(directory) / 'partial.txt'
            partial.write_text('generated fixture', encoding='utf-8')
            mm.publish_output(partial, destination)
            with self.assertRaises(FileExistsError):
                mm.publish_output(partial, destination)
            self.assertTrue(partial.exists())
            self.assertEqual(destination.read_text(), 'generated fixture')
            self.assertNotEqual(mm.fresh_partial(destination), mm.fresh_partial(destination))

    @patch('runtime_support.shutil.which', return_value=None)
    @patch('runtime_support.subprocess.run')
    def test_dependency_check_needs_no_file_and_does_not_install(self, run, _):
        args = mm.parse_args(['--check-dependencies'])
        self.assertEqual(check_dependencies(args), 3)
        run.assert_not_called()

    def test_stall_detected_despite_continuous_status_lines(self):
        command = [sys.executable, '-u', '-c',
                   'import time\nfor i in range(100):\n print("out_time_us=0",flush=True); time.sleep(.02)', 'unused']
        started = time.monotonic()
        code, stalled = mm.run_ffmpeg(command, 10000, stall_timeout=.2)
        self.assertTrue(stalled)
        self.assertNotEqual(code, 0)
        self.assertLess(time.monotonic() - started, 8)

    @patch('muxmender.queue.Queue.get', side_effect=KeyboardInterrupt)
    def test_interrupt_terminates_owned_process(self, _):
        original_popen = subprocess.Popen
        children = []
        def capture(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            return child
        with patch('muxmender.subprocess.Popen', side_effect=capture):
            with self.assertRaises(KeyboardInterrupt):
                mm.run_ffmpeg([sys.executable, '-c', 'import time; time.sleep(30)', 'unused'], 30)
        self.assertIsNotNone(children[0].poll())


if __name__ == '__main__':
    unittest.main()
