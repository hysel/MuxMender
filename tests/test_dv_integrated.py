import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import muxmender as mm
import dv_full_file as full


class IntegratedDVTests(unittest.TestCase):
    def test_default_remains_skip(self):
        args = mm.parse_args(['example.mkv'])
        self.assertFalse(args.preserve_dolby_vision)
        self.assertEqual(args.dolby_vision_policy, 'skip')

    def test_dry_run_dispatch_and_execution_options(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'fixture.mkv'; source.touch()
            for execute in (False, True):
                args = [str(source), '--preserve-dolby-vision'] + (['--execute'] if execute else [])
                with patch('dv_full_file.shutil.which', return_value='tool'), patch.object(mm,'gpu_vendors',return_value=['amd']) as gpu, patch.object(full,'run',return_value=0) as run:
                    self.assertEqual(mm.main(args),0)
                    options=run.call_args.args[0]
                    self.assertEqual(options.execute,execute)
                    self.assertEqual((options.qp_i,options.qp_p),(21,23))
                    self.assertEqual(options.min_savings,5)
                    self.assertEqual(gpu.call_count, int(execute))

    def test_conflicts_do_not_start_pipeline(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'fixture.mkv'; source.touch()
            for flags in (['--resolution','1080p'],['--codec','av1'],['--hardware','nvidia'],
                          ['--hardware','intel'],['--hardware','cpu'],['--hardware-fallback','cpu'],
                          ['--full-file-streaming'],['--preview-seconds','30'],['--quality','compact'],
                          ['--dolby-vision-policy','copy'],['--dv-qp-i','52'],['--execute','--dry-run'],
                          ['--delete-originals'],['--overwrite-output']):
                with self.subTest(flags=flags), patch.object(full,'run') as run:
                    self.assertEqual(mm.main([str(source),'--preserve-dolby-vision',*flags]),2)
                    run.assert_not_called()
            with patch.object(full,'run') as run:
                self.assertEqual(mm.main([folder,'--preserve-dolby-vision']),2)
                run.assert_not_called()

    def test_unvalidated_hardware_and_missing_tool_block(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'fixture.mkv'; source.touch()
            args=mm.parse_args([str(source),'--preserve-dolby-vision','--execute'])
            with patch('dv_full_file.shutil.which',return_value='tool'), patch.object(mm,'gpu_vendors',return_value=['nvidia']), patch.object(full,'run') as run:
                self.assertEqual(full.run_integrated(args,source),3)
                run.assert_not_called()
            with patch('dv_full_file.shutil.which',return_value=None), patch.object(mm,'offer_requirement') as offer, patch.object(full,'run') as run:
                self.assertEqual(full.run_integrated(args,source),3)
                self.assertFalse(offer.call_args.kwargs['allow_cpu'])
                run.assert_not_called()
