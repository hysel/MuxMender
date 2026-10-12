import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[1]/'tools/benchmark_sdr_gpu_reader.py'
spec=importlib.util.spec_from_file_location('sdr_benchmark',PATH)
benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)


class SDRBenchmarkTests(unittest.TestCase):
    def test_silent_terminal_drop_is_not_a_complete_control(self):
        result=benchmark.complete_control(dict(strict_success=True),49,50)
        self.assertTrue(result['decoder_clean'])
        self.assertFalse(result['strict_success'])
        self.assertFalse(result['complete_frame_count'])
        self.assertFalse(benchmark.complete_control(dict(strict_success=False),50,50)['strict_success'])
        self.assertTrue(benchmark.complete_control(dict(strict_success=True),50,50)['strict_success'])
        with self.assertRaises(ValueError):benchmark.complete_control(dict(strict_success=True),0,0)

    def test_source_digest_is_read_only(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'fixture';source.write_bytes(b'unchanged source')
            self.assertEqual(benchmark.file_digest(source),hashlib.sha256(b'unchanged source').hexdigest())
            self.assertEqual(source.read_bytes(),b'unchanged source')

    def test_exact_parity_rejects_differences_allowed_by_normal_mux_tolerance(self):
        line='best_effort_timestamp_time=0.000|width=1920|height=1080|pix_fmt=yuv420p|sample_aspect_ratio=1:1|interlaced_frame=0|top_field_first=0|repeat_pict=0|color_primaries=bt709|color_transfer=bt709|color_space=bt709|color_range=tv\n'
        with tempfile.TemporaryDirectory() as directory:
            left=Path(directory)/'cpu';right=Path(directory)/'gpu';left.write_text(line)
            right.write_text(line);self.assertEqual(benchmark.exact_pair(left,right)['frames'],1)
            for changed in (line.replace('0.000','0.001'),line.replace('top_field_first=0','top_field_first=1'),
                            line.replace('color_range=tv','color_range=pc'),line+line,'',line.replace('repeat_pict=0|','')):
                right.write_text(changed)
                with self.assertRaises(ValueError):benchmark.exact_pair(left,right)

    def test_windows_cannot_execute_native_benchmark(self):
        with patch.object(benchmark.sys,'platform','win32'),patch.object(benchmark.subprocess,'run') as run:
            with self.assertRaises(RuntimeError):benchmark.main()
            with self.assertRaises(RuntimeError):benchmark.read([],{},Path('unused'),None,1)
            run.assert_not_called()
