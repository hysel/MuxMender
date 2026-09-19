from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import run_truenas_sample_batch as batch


class TrueNASBatchTests(unittest.TestCase):
    def test_bounded_commands_and_read_only_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media, output = root/'media', root/'output'
            location = media/'TV/Series/Season 1'
            location.mkdir(parents=True); output.mkdir()
            for name in batch.EPISODES:
                (location/name).write_bytes(b'test fixture')
            folder, commands = batch.plans(media, output)
            self.assertEqual(len(commands), 3)
            self.assertFalse(folder.exists())
            self.assertTrue(all('--execute' not in c for c in commands))
            for name in batch.ROUND2:
                (location/name).write_bytes(b'test fixture')
            second, second_commands = batch.plans(media, output, round2=True)
            self.assertNotEqual(second, folder)
            self.assertEqual([Path(c[4]).name for c in second_commands], list(batch.ROUND2))
            self.assertTrue(all('--execute' not in c for c in second_commands))
            with patch.object(batch, 'is_read_only', return_value=False):
                with self.assertRaises(ValueError):
                    batch.plans(media, output, True)
            with patch.object(batch, 'is_read_only', return_value=True):
                _, commands = batch.plans(media, output, True)
            for command in commands:
                self.assertIn('--execute', command)
                self.assertIn('--encode-best', command)
                self.assertNotIn('--vmaf-mean', command)
                self.assertNotIn('--minimum-savings-percent', command)
            with self.assertRaises(ValueError):
                batch.plans(media, media)

    def test_failure_stops_batch_and_duplicate_start_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); folder=root/'batch'
            commands=[['python','-B','-m','auto_optimize','fixture']]*3
            with patch.object(batch, 'plans', return_value=(folder, commands)), \
                 patch.object(batch.shutil, 'disk_usage') as disk, \
                 patch.object(batch.subprocess, 'run') as process:
                disk.return_value.free=20*1024**3
                process.return_value.returncode=1
                with self.assertRaises(RuntimeError):
                    batch.run(root, root, True)
                self.assertEqual(process.call_count,1)
                with self.assertRaises(FileExistsError):
                    batch.run(root, root, True)
