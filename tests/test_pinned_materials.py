import unittest
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from tools.fetch_pinned_materials import checked_row, fetch


class PinnedMaterials(unittest.TestCase):
    def test_resume_revalidates_cache_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); destination=root/'inputs'; destination.mkdir()
            (destination/'source.tar.gz').write_bytes(b'fixture')
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps([dict(url='https://github.com/a/source.tar.gz',sha256=hashlib.sha256(b'fixture').hexdigest())]))
            with patch('tools.fetch_pinned_materials.urllib.request.urlopen') as network:
                self.assertTrue(fetch(manifest,destination,root/'reports',resume=True)[0]['cached'])
                network.assert_not_called()
            (destination/'source.tar.gz').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                fetch(manifest,destination,root/'reports',resume=True)
            self.assertEqual((destination/'source.tar.gz').read_bytes(),b'changed')

    def test_rejects_local_insecure_and_unpinned_inputs(self):
        for url in ('http://github.com/a/source.tar.gz', 'https://127.0.0.1/source',
                    'file:///etc/passwd', 'https://github.com/a/..', 'https://user:pass@github.com/a/source'):
            with self.assertRaises(ValueError):
                checked_row(dict(url=url, sha256='a'*64))
        with self.assertRaises(ValueError):
            checked_row(dict(url='https://github.com/a/source.tar.gz', sha256='bad'))

    def test_safe_archive_name(self):
        self.assertEqual(checked_row(dict(url='https://github.com/a/source.tar.gz', sha256='a'*64)), 'source.tar.gz')
        with self.assertRaises(ValueError):
            checked_row(dict(url='https://github.com/a/source.tar.gz', name='../escape', sha256='a'*64))
