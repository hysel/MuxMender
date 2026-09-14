import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import amd_av1_revalidate as rv


class RevalidationTests(unittest.TestCase):
    def test_existing_media_and_previous_failure_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'source.mkv'; source.write_bytes(b'original')
            run = root/'old'; run.mkdir()
            output = run/'output.mkv'; output.write_bytes(b'copy')
            previous = dict(source=str(source), output=str(output), status='failed',
                            source_sha256_before=hashlib.sha256(b'original').hexdigest())
            report = run/'validation.json'; report.write_text(json.dumps(previous))
            args = SimpleNamespace(run_dir=run, report_dir=root/'new', ffmpeg='ffmpeg', ffprobe='ffprobe')
            with patch.object(rv.av, 'validate_output') as validate:
                self.assertEqual(rv.run(args), 0)
                validate.assert_called_once()
            self.assertEqual(source.read_bytes(), b'original')
            self.assertEqual(output.read_bytes(), b'copy')
            self.assertEqual(json.loads(report.read_text()), previous)
            result = json.loads(next((root/'new').glob('*/validation.json')).read_text())
            self.assertEqual(result['status'], 'verified-full-file-awaiting-playback')
            self.assertEqual(result['output_sha256_before'], result['output_sha256_after'])
