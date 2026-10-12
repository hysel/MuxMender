import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
spec = importlib.util.spec_from_file_location('rpm_sources', ROOT/'tools/verify_wheel_rpm_sources.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RpmSourceDownload(unittest.TestCase):
    def test_valid_checksum_download(self):
        with tempfile.TemporaryDirectory() as directory:
            response = io.BytesIO(b'fixture')
            response.url = module.BASE+'Packages/fixture.rpm'
            with patch.object(module.urllib.request, 'urlopen', return_value=response):
                data, sha = module.download('Packages/fixture.rpm', Path(directory)/'fixture', hashlib.sha256(b'fixture').hexdigest())
            self.assertEqual(data, b'fixture')
            self.assertEqual(sha, hashlib.sha256(b'fixture').hexdigest())

    def test_reject_external_url_without_request(self):
        with patch.object(module.urllib.request, 'urlopen') as request:
            with self.assertRaises(ValueError): module.download('https://invalid.example/a', 'unused')
            request.assert_not_called()

    def test_reject_checksum_and_http_redirect(self):
        with tempfile.TemporaryDirectory() as directory:
            for url, expected in ((module.BASE+'a', '0'*64), ('http://invalid.example/a', None)):
                response = io.BytesIO(b'fixture')
                response.url = url
                with patch.object(module.urllib.request, 'urlopen', return_value=response):
                    with self.assertRaises(ValueError): module.download('a', Path(directory)/'unused', expected)
                self.assertFalse((Path(directory)/'unused').exists())
