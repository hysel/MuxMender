import io
from pathlib import Path
import hashlib
import tarfile
import tempfile
import unittest
from tools.prepare_v61_candidate import prepare

ROOT=Path(__file__).resolve().parents[1]


class CandidateTests(unittest.TestCase):
    def test_resume_is_bound_to_built_image_and_allowed_api_host(self):
        script=(ROOT/'deploy/truenas/check-v61.sh').read_text()
        self.assertIn('http://192.168.1.232:8767/api/controls',script)
        self.assertNotIn('http://127.0.0.1:8767',script)
        self.assertIn('--run-finish',script)
        self.assertIn('sha256:a2cd06a2d83e3a32ed0557edcb3b787cde832c4d8e0dc4e360df69ed848c255c',script)

    def test_private_inputs_excluded_and_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.tar';dest=Path(directory)/'candidate.tar'
            with tarfile.open(source,'w') as out:
                for name in ('python/app_version.py','vendor/gpu-reader/qualification.json','vendor/gpu-reader/evidence.json'):
                    item=tarfile.TarInfo(name);item.size=1;out.addfile(item,io.BytesIO(b'x'))
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):prepare(ROOT,source,dest,'0'*64)
            prepare(ROOT,source,dest,digest)
            with tarfile.open(dest) as package:
                self.assertFalse(any(n.startswith('vendor/') for n in package.getnames()))
                self.assertIn('python/app_version.py',package.getnames())
            with self.assertRaises(FileExistsError):prepare(ROOT,source,dest,digest)

    def test_final_reader_check_cannot_shadow_packaged_code(self):
        script=(ROOT/'deploy/truenas/check-v61.sh').read_text()
        final=script.split("phase 'Exact image host-receipt dispatch and shared workflow'",1)[1]
        self.assertNotIn('dst=/qualification',final)
        self.assertNotIn('dst=/opt/muxmender,',final)
        self.assertIn('dst=/release-tools,readonly',final)
        self.assertIn('--installed-profile',final)
        self.assertNotIn('docker stop',script)
        self.assertNotIn('docker start',script)
