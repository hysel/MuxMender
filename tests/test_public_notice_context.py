import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('candidate', ROOT/'tools/prepare_public_candidate.py')
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class NoticeContext(unittest.TestCase):
    def test_replaces_old_notices_without_changing_app_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            original = work/'old.tar'
            with tarfile.open(original, 'w') as archive:
                for name in ('public-materials/REVIEW-PENDING.md', 'python/app.py'):
                    entry = tarfile.TarInfo(name)
                    entry.size = 3
                    archive.addfile(entry, io.BytesIO(b'old'))
            materials = work/'materials'
            materials.mkdir()
            (materials/'LICENSE').write_bytes(b'new')
            expected = hashlib.sha256(original.read_bytes()).hexdigest()
            candidate.prepare(ROOT, original, expected, work/'new.tar', materials)
            with tarfile.open(work/'new.tar') as archive:
                self.assertNotIn('public-materials/REVIEW-PENDING.md', archive.getnames())
                self.assertEqual(archive.extractfile('python/app.py').read(), b'old')
                self.assertEqual(archive.extractfile('public-materials/LICENSE').read(), b'new')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                candidate.prepare(ROOT, original, '0'*64, work/'bad.tar', materials)
