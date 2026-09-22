import ast
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from job_tracking import Job
from performance import category
from resource_governor import Governor,validation_thread_budget


class PerformanceTests(unittest.TestCase):
    def test_hdr_reader_thread_budget_respects_shared_host_limits(self):
        good=dict(cpus=12,cpu_percent=35,available_gib=16,host_available_gib=32,io_pressure=0,memory_pressure=0)
        self.assertEqual(validation_thread_budget(good),4)
        self.assertEqual(validation_thread_budget({}),2)
        for key,value in [('cpus',4),('cpus',float('nan')),('cpu_percent',65),('container_cpu_percent',80),
                          ('available_gib',4),('host_available_gib',8),('io_pressure',6),('memory_pressure',1)]:
            self.assertEqual(validation_thread_budget(dict(good,**{key:value})),2)
        self.assertEqual(validation_thread_budget(dict(good,cpus=8,cpu_percent=35)),2)

    def test_categories_are_bounded_and_not_filename_keys(self):
        for phase,expected in [('Checking frame timing: full','frame_validation'),
            ('Checking HDR frame timing: full','frame_validation'),
            ('hevc_nvenc-balanced-0','encoding'),('hevc_nvenc-balanced-0-quality','quality_measurement'),
            ('full-decode','full_decode'),('Verifying file checksum: movie.mkv','checksums'),
            ('Checking all copied tracks: full','track_validation'),('Reading media metadata: movie','metadata'),
            ('reference-0','sample_extraction'),('random movie name','other')]:
            self.assertEqual(category(phase),expected)

    def test_timings_are_monotonic_not_double_counted_and_stop_on_finish(self):
        with tempfile.TemporaryDirectory() as folder,patch('job_tracking.time.monotonic',return_value=0) as clock:
            job=Job(folder,'Timing')
            job.save(phase='full-encode')
            clock.return_value=10;job.save()
            clock.return_value=12;job.save(phase='full-decode')
            clock.return_value=15;job.save(state='completed')
            clock.return_value=50;job.save()
            totals=json.loads((job.directory/'job.json').read_text())['performance_seconds']
            self.assertEqual(totals['encoding'],12)
            self.assertEqual(totals['full_decode'],3)
            self.assertEqual(sum(totals.values()),15)

    def test_gpu_decoder_load_is_observed_and_can_block_admission(self):
        governor=Governor()
        with patch('resource_governor.subprocess.check_output',return_value='5, 10, 95, 4096, 50\n'):
            metrics=governor.sample()
        self.assertEqual(metrics['gpu_percent'],95)
        self.assertEqual(metrics['gpu_encode_percent'],10)
        self.assertEqual(metrics['gpu_decode_percent'],95)
        self.assertEqual(metrics['vram_free_gib'],4)
        governor.sample=lambda:dict(metrics,cpu_percent=10,cpus=8,available_gib=24,io_pressure=0,memory_pressure=0)
        self.assertFalse(governor.admit('shared',1,100))

    def test_unknown_gpu_telemetry_is_not_zero_load(self):
        for text in ['5,10,N/A,4096,50\n','5,10,nan,4096,50\n','5,10\n']:
            with patch('resource_governor.subprocess.check_output',return_value=text):
                self.assertNotIn('gpu_percent',Governor().sample())

    def test_package_contains_all_runtime_modules(self):
        root=Path(__file__).resolve().parents[1]
        config=(root/'pyproject.toml').read_text() if (root/'pyproject.toml').exists() else None
        if config is None:self.skipTest('Docker context does not install a wheel')
        modules=set(ast.literal_eval(re.search(r'py-modules\s*=\s*(\[[^\]]+\])',config).group(1)))
        expected={p.stem for p in (root/'python').glob('*.py') if p.name!='__init__.py'}
        self.assertEqual(modules,expected)


if __name__=='__main__':unittest.main()
