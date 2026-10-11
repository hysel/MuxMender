import importlib.util
import io
import json
from pathlib import Path
import hashlib
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('public_audit', Path(__file__).resolve().parents[1] / 'tools/audit_public_release.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
runtime_spec = importlib.util.spec_from_file_location('runtime_audit', Path(__file__).resolve().parents[1] / 'tools/audit_image_runtime.py')
runtime = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime)


class PublicReleaseAudit(unittest.TestCase):
    def test_nonfree_build_rejected(self):
        self.assertTrue(runtime.nonredistributable('configuration: --enable-gpl --enable-nonfree --enable-libfdk_aac'))
        self.assertTrue(runtime.nonredistributable('License: nonfree and unredistributable'))
        self.assertFalse(runtime.nonredistributable('configuration: --enable-gpl --enable-version3'))
        self.assertFalse(runtime.nonredistributable('configuration: --disable-nonfree'))

    def test_valid_materials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'notice').write_bytes(b'fixture')
            materials = [{'role': role, 'path': 'notice', 'sha256': hashlib.sha256(b'fixture').hexdigest()}
                         for role in ('app-license', 'third-party-notices', 'corresponding-source', 'build-instructions')]
            manifest = dict(schema=1, version='20261010-v60', revision='a'*40,
                            redistribution_reviewed=True, privacy_reviewed=True, materials=materials)
            (root / 'public-release.json').write_text(json.dumps(manifest))
            self.assertEqual(audit.audit(root, '20261010-v60', 'a'*40), manifest)
            manifest['privacy_reviewed'] = False
            (root / 'public-release.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                audit.audit(root, '20261010-v60', 'a'*40)

    def test_unsafe_archives(self):
        for name, linked in [('../outside', False), ('/absolute', False), ('C:/outside', False), ('link', True)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with tarfile.open(root / 'input.tar', 'w') as bundle:
                    member = tarfile.TarInfo(name)
                    if linked:
                        member.type = tarfile.SYMTYPE
                        member.linkname = '/outside'
                        bundle.addfile(member)
                    else:
                        member.size = 1
                        bundle.addfile(member, io.BytesIO(b'x'))
                with self.assertRaises(ValueError):
                    audit.extract_context(root / 'input.tar', root / 'context')

    def test_version_and_materials_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'public-release.json').write_text('{}')
            with self.assertRaises(ValueError):
                audit.audit(root, 'latest', 'a'*40)
            with self.assertRaises(ValueError):
                audit.audit(root, '20261010-v60', 'a'*40)
