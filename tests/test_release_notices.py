import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('release_notices', Path(__file__).resolve().parents[1] / 'tools/prepare_release_notices.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NoticePreparation(unittest.TestCase):
    def fixture(self, root, name='ubuntu-notices/package/copyright'):
        data = b'Original notice text\n'
        archive = root / 'sources.tar'
        with tarfile.open(archive, 'w') as tar:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))
        (root / 'LICENSE').write_text('MIT fixture')
        (root / 'bundle-receipt.json').write_text(json.dumps(dict(bundle=archive.name,
            sha256=module.digest(archive), size=archive.stat().st_size, revision='a'*40)))
        (root / 'source-file-catalog.json').write_text(json.dumps([
            dict(path=name, size=len(data), sha256=hashlib.sha256(data).hexdigest())]))

    def test_draft_retains_notices_without_approving_or_copying_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            result = module.prepare(root, root/'output', root)
            self.assertEqual(result['notices'], 1)
            self.assertFalse(result['reviewed'])
            self.assertFalse((root/'output/public-release.json').exists())
            self.assertFalse((root/'output/sources.tar').exists())
            self.assertEqual((root/'output/public-materials/notices/ubuntu-notices/package/copyright').read_bytes(), b'Original notice text\n')
            with self.assertRaises(FileExistsError):
                module.prepare(root, root/'output', root)

    def test_rejects_changed_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            with (root/'sources.tar').open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                module.prepare(root, root/'output', root)

    def test_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, '../escape')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                module.prepare(root, root/'output', root)
