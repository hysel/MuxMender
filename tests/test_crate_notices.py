import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from tools.audit_crate_notices import inspect,licensing_header


class CrateNotices(unittest.TestCase):
    def test_introductory_license_header_is_not_invented_or_executed(self):
        data=b'// Copyright fixture\n// Licensed under the MIT license.\n\nfn main() { panic!("not executed"); }'
        header=licensing_header(data)
        self.assertIn(b'Copyright fixture',header)
        self.assertNotIn(b'fn main',header)
        self.assertIsNone(licensing_header(b'// unrelated docs\nfn main() {}'))
    def test_pinned_source_notices_are_retained_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);sources=root/'sources';sources.mkdir()
            path=sources/'demo-1.0.0.crate'
            with tarfile.open(path,'w:gz') as archive:
                for name,content in [('demo-1.0.0/Cargo.toml',b'[package]\nname="demo"\nversion="1.0.0"\nlicense="MIT"'),
                                     ('demo-1.0.0/LICENSE',b'fixture notice'),
                                     ('demo-1.0.0/build.rs',b'not executed')]:
                    member=tarfile.TarInfo(name);member.size=len(content)
                    archive.addfile(member,io.BytesIO(content))
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            (sources/'download-receipts.json').write_text(json.dumps([dict(name=path.name,sha256=digest)]))
            rows=inspect(sources,root/'notices')
            self.assertFalse(rows[0]['needs_notice_review'])
            self.assertFalse(any((root/'notices').rglob('build.rs')))
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):inspect(sources,root/'invalid')
