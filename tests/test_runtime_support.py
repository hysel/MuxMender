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


class RuntimeTests(unittest.TestCase):
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
