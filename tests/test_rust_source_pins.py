import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from tools.prepare_rust_source_pins import pins


class RustPins(unittest.TestCase):
    def archive(self, root, source):
        path = root/'source.tar'
        content = ('[[package]]\nname="demo"\nversion="1.0.0"\nsource="'+source+'"\nchecksum="'+'a'*64+'"\n').encode()
        with tarfile.open(path, 'w') as archive:
            member=tarfile.TarInfo('demo/Cargo.lock');member.size=len(content)
            archive.addfile(member, io.BytesIO(content))
        return path

    def test_deduplicates_pinned_crates_without_running_cargo(self):
        with tempfile.TemporaryDirectory() as folder:
            path=self.archive(Path(folder),'registry+https://github.com/rust-lang/crates.io-index')
            self.assertEqual(len(pins([path,path])),1)
            self.assertEqual(pins([path])[0]['name'],'demo-1.0.0.crate')

    def test_unknown_git_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=self.archive(Path(folder),'git+https://example.invalid/repo')
            with self.assertRaises(ValueError):pins([path])
