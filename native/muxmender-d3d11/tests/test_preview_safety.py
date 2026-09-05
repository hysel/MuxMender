"""Offline guard tests. No media inputs or GPU use; only generated text fixtures."""
import pathlib
import subprocess
import tempfile
import unittest

EXE = pathlib.Path(__file__).resolve().parents[1] / 'build/preview/muxmender-dv-preview.exe'


class PreviewSafety(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([str(EXE), *map(str, args)], capture_output=True, text=True, timeout=10)

    def test_help(self):
        result = self.run_cli('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('no audio/subtitles', result.stdout)

    def test_requires_explicit_sdr(self):
        result = self.run_cli('--input', 'absent.mkv', '--output', 'unused.mkv')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Explicit --sdr-preview', result.stderr)

    def test_duration_is_bounded(self):
        for value in ['0', '-1', '11', 'nan', 'inf', '3seconds']:
            with self.subTest(value=value):
                result = self.run_cli('--input', 'absent.mkv', '--output', 'unused.mkv', '--sdr-preview', '--seconds', value)
                self.assertNotEqual(result.returncode, 0)

    def test_existing_output_unchanged(self):
        # Only this generated text fixture is cleaned up, never user media.
        with tempfile.TemporaryDirectory(prefix='muxmender-safety-') as directory:
            sentinel = pathlib.Path(directory) / 'original-fixture.txt'
            data = b'ORIGINAL SENTINEL - MUST REMAIN UNCHANGED'
            sentinel.write_bytes(data)
            before = sentinel.stat().st_mtime_ns
            for source in ['absent.mkv', sentinel]:
                result = self.run_cli('--input', source, '--output', sentinel, '--sdr-preview')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Output already exists', result.stderr)
                self.assertEqual(sentinel.read_bytes(), data)
                self.assertEqual(sentinel.stat().st_mtime_ns, before)

    def test_streaming_rejects_file_output_and_excess_duration(self):
        for flags in (['--output', 'unused.mkv'], ['--seconds', '61'], ['--sdr-preview']):
            result = self.run_cli('--input', 'absent.mkv', '--stream-output', '--hdr-preview', *flags)
            self.assertNotEqual(result.returncode, 0)

    def test_full_file_requires_pipe_and_no_range(self):
        for flags in (['--output', 'unused.mkv'], ['--stream-output', '--seconds', '60'], ['--stream-output', '--start', '0']):
            result = self.run_cli('--input', 'absent.mkv', '--full-file', '--hdr-preview', *flags)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Full-file mode requires', result.stderr)

    def test_missing_source_never_creates_output(self):
        with tempfile.TemporaryDirectory(prefix='muxmender-safety-') as directory:
            output = pathlib.Path(directory) / 'must-not-exist.mkv'
            result = self.run_cli('--input', str(output) + '.missing', '--output', output, '--sdr-preview', '--dry-run')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
