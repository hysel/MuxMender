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
    def test_nested_upstream_notices_only(self):
        content = io.BytesIO()
        with tarfile.open(fileobj=content, mode='w:gz') as archive:
            for name in ('package/LICENSE', 'package/NOTICE.txt', 'package/main.c'):
                member = tarfile.TarInfo(name)
                member.size = 4
                archive.addfile(member, io.BytesIO(b'text'))
        content.seek(0)
        with tempfile.TemporaryDirectory() as temp:
            rows = module.copy_upstream_notices(content, Path(temp), 'fixture.tar.gz')
            self.assertEqual(len(rows), 2)
            self.assertTrue(all('main.c' not in row['path'] for row in rows))

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

    def test_separately_collected_wheel_notices_are_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            name='wheel-notices/public-materials/notices/pyav-wheel/LICENSE'
            self.fixture(root,name)
            result=module.prepare(root,root/'output',root)
            self.assertEqual(result['notices'],1)
            self.assertEqual((root/'output/public-materials/notices'/name).read_bytes(),b'Original notice text\n')

    def test_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, '../escape')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                module.prepare(root, root/'output', root)
