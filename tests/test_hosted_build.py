import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_hosted_build as build


class HostedBuild(unittest.TestCase):
    def test_source_pins_complete(self):
        self.assertEqual(set(build.SOURCES), set(build.FFMPEG9_SOURCE_CHECKSUMS))

    def test_bad_hash_not_written(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(build.urllib.request, 'urlopen', return_value=io.BytesIO(b'bad')):
            target = Path(folder) / 'source'
            with self.assertRaises(ValueError):
                build.fetch('https://example.invalid/input', target, '0' * 64)
            self.assertFalse(target.exists())

    def test_verified_download(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(build.urllib.request, 'urlopen', return_value=io.BytesIO(b'ok')):
            target = Path(folder) / 'source'
            build.fetch('https://example.invalid/input', target, hashlib.sha256(b'ok').hexdigest())
            self.assertEqual(target.read_bytes(), b'ok')

    def test_workflow_cannot_publish(self):
        text = (build.ROOT / '.github/workflows/build-candidate.yml').read_text()
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('environment: container-release', text)
        self.assertNotIn('docker push', text)
        self.assertNotIn('packages: write', text)
        self.assertNotIn('--gpus', text)


if __name__ == '__main__':
    unittest.main()
