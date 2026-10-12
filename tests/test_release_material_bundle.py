import hashlib
import io
import tarfile
from pathlib import Path
import tempfile
import unittest
from tools.assemble_release_materials import checked_file,descriptor_sources,code_only_archive


class MaterialBundle(unittest.TestCase):
    def test_code_only_archive_preserves_code_not_media_fixtures(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.tar.gz'
            with tarfile.open(source,'w:gz') as archive:
                for name,data in [('demo/src/main.cpp',b'unchanged code'),('demo/LICENSE',b'notice'),('demo/test/fixture.hevc',b'fixture')]:
                    member=tarfile.TarInfo(name);member.size=len(data);archive.addfile(member,io.BytesIO(data))
            original=source.read_bytes()
            result,count=code_only_archive(source,root/'public.tar.gz')
            self.assertEqual(count,1)
            with tarfile.open(result) as archive:
                self.assertEqual(archive.extractfile('demo/src/main.cpp').read(),b'unchanged code')
                self.assertNotIn('demo/test/fixture.hevc',archive.getnames())
            self.assertEqual(source.read_bytes(),original)
    def test_checksummed_material_never_accepts_traversal_or_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'source').write_bytes(b'fixture')
            self.assertEqual(checked_file(root,'source',hashlib.sha256(b'fixture').hexdigest()),root/'source')
            for name in ('../source','/source','C:/source'):
                with self.assertRaises(ValueError):checked_file(root,name,'a'*64)
            with self.assertRaises(ValueError):checked_file(root,'source','a'*64)

    def test_supplement_preserves_exact_source_version(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'demo.tar.gz').write_bytes(b'fixture')
            digest=hashlib.sha256(b'fixture').hexdigest()
            (root/'demo_1.0.dsc').write_text('Source: demo\nVersion: 1:1.0\nChecksums-Sha256:\n '+digest+' 7 demo.tar.gz\nFiles:\n')
            self.assertEqual(len(descriptor_sources(root,'demo','1:1.0')),1)
            with self.assertRaises(ValueError):descriptor_sources(root,'demo','1.0')
