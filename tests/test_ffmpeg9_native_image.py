from pathlib import Path
import unittest


class NativeImageTests(unittest.TestCase):
    def test_source_collection_is_exact_image_and_disposable(self):
        root=Path(__file__).resolve().parents[1]
        script=(root/'deploy/truenas/collect-ffmpeg9-native-materials.sh').read_text()
        self.assertIn('image=sha256:067a847ceba0',script)
        self.assertIn('docker run --rm --user 0:0',script)
        self.assertIn('reader-export/source/',script)
        self.assertIn('chmod -R a+rX "$work"',script)
        self.assertNotIn('dst=/media',script)
        self.assertNotIn('docker push',script)
        material=(root/'tools/assemble_release_materials.py').read_text()
        self.assertIn('pyav-19.0.0.tar.gz',material)
        self.assertNotIn('pyav-ffmpeg-8.1.2-1.tar.gz',material)

    def test_isolated_full_checks_and_no_production_writes(self):
        script=(Path(__file__).resolve().parents[1]/'deploy/truenas/qualify-ffmpeg9-native.sh').read_text()
        for check in ('--require-ffmpeg9','--require-redistributable','runtime reaper','copy cancel','initialize upgrade','systemd-run','sha256sum -c'):
            self.assertIn(check,script)
        for forbidden in ('docker stop','docker restart','docker push','dst=/media','docker.sock'):
            self.assertNotIn(forbidden,script)
        self.assertIn('Production queue is not idle',script)
        self.assertIn('http://truenas:8767/api/controls',script)
        self.assertNotIn('http://127.0.0.1:8767',script)
        self.assertEqual(script.count('--tmpfs /work:rw,uid=568,gid=568,mode=700'),2)
        self.assertIn('REVIEW', (Path(__file__).resolve().parents[1]/'tools/prepare_public_candidate.py').read_text())
