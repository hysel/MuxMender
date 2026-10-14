import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import build_app_release


class RuntimePackageTests(unittest.TestCase):
    def test_windows_shell_line_endings_are_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'run.sh';path.write_bytes(b'#!/bin/bash\r\nset -e\r\n')
            self.assertEqual(build_app_release.portable_release_content(path),b'#!/bin/bash\nset -e\n')

    def test_previous_build_failure_does_not_mark_revised_package_failed(self):
        from tools.monitor_release_stage import interpret
        status,terminal=interpret('status=failed\nexit_code=1\narchive_sha256=old\n','new')
        self.assertEqual(status['state'],'pending');self.assertFalse(terminal)
        status,terminal=interpret('status=passed\narchive_sha256=new\n','new')
        self.assertEqual(status['state'],'completed');self.assertTrue(terminal)

    def test_version_check_accepts_windows_checkout_and_revision_context_is_separate(self):
        root=Path(__file__).resolve().parents[1]
        script=(root/'deploy/truenas/stage-release.sh').read_text()
        self.assertIn("tr -d '\\r'",script)
        self.assertIn('app-build-$version-${checksum:0:12}',script)
    def test_source_manifest_matches_package_pins(self):
        root=Path(__file__).resolve().parents[1]
        lines=(root/'deploy/truenas/ffmpeg9-source.sha256').read_text().splitlines()
        pins={Path(line.split()[1]).name:line.split()[0] for line in lines}
        self.assertEqual(pins,build_app_release.FFMPEG9_SOURCE_CHECKSUMS)

    def test_source_checksum_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'fixture.tar').write_bytes(b'fixture')
            digest=hashlib.sha256(b'fixture').hexdigest()
            with patch.object(build_app_release,'FFMPEG9_SOURCE_CHECKSUMS',{'fixture.tar':digest}):
                self.assertEqual(len(build_app_release.inspect_ffmpeg9_sources(root)),1)
                (root/'fixture.tar').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                    build_app_release.inspect_ffmpeg9_sources(root)

    def test_runtime_is_default_without_legacy_base(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'deploy/truenas/Dockerfile.app').read_text()
        self.assertIn('AS ffmpeg9-build',text)
        self.assertIn('ENV PATH=/opt/ffmpeg9/bin:',text)
        self.assertIn('COPY --from=ffmpeg9-build /opt/ffmpeg9/',text)
        self.assertNotIn('linuxserver/ffmpeg',text)
        script=(root/'deploy/truenas/build_ffmpeg9.sh').read_text()
        self.assertIn('sha256sum -c source/source.sha256',script)
        self.assertIn('-Dbuilt_in_models=true',script)
        self.assertIn('nv-codec-headers-n13.0.19.0',script)

    def test_no_active_docker_recipe_pins_ffmpeg8(self):
        root=Path(__file__).resolve().parents[1]
        for path in (root/'deploy').rglob('Dockerfile*'):
            with self.subTest(path=str(path)):
                self.assertNotIn('ffmpeg:8.',path.read_text())
                self.assertNotIn('ffmpeg-8.',path.read_text())
        self.assertIn('ffmpeg-9.0.2.tar.xz',build_app_release.GPU_READER_SOURCE_CHECKSUMS)


if __name__=='__main__':unittest.main()
