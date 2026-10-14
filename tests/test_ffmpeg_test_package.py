import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('package',ROOT/'tools/build_ffmpeg_test_package.py')
package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)


class TestPackageTests(unittest.TestCase):
    def test_inventory_includes_linked_and_unlinked_regressions(self):
        ledger={'schema':1,'fixes':[{'id':'FF-001','tests':['test_ffmpeg_test_package.py']}]}
        index=package.regression_index(ROOT,ledger)
        self.assertEqual(len(index),len(list((ROOT/'tests').glob('test_*.py'))))
        self.assertTrue(any(not e['fix_ids'] for e in index))
        self.assertTrue(any('FF-001' in e['fix_ids'] for e in index))
        self.assertGreater(sum(len(e['tests']) for e in index),1000)

    def test_archive_manifest_matches_contents_and_never_bundles_runtime_media(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination=Path(temporary)/'package'
            ledger=Path(temporary)/'ledger.json'
            ledger.write_text(json.dumps({'schema':1,'fixes':[]}))
            result=package.build(destination,ledger_path=ledger)
            archive=Path(result['archive'])
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),result['sha256'])
            with tarfile.open(archive) as source:
                manifest=json.loads(source.extractfile('package-manifest.json').read())
                for name,digest in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(source.extractfile(name).read()).hexdigest(),digest,name)
                self.assertFalse(any(Path(m.name).suffix in ('.mkv','.mp4','.m4a','.avi','.exe') for m in source.getmembers()))
            with self.assertRaises(FileExistsError):package.build(destination,ledger_path=ledger)
