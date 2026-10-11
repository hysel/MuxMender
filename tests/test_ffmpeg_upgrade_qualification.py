import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('upgrade',Path(__file__).resolve().parents[1]/'tools/qualify_ffmpeg_upgrade.py')
upgrade=importlib.util.module_from_spec(spec);spec.loader.exec_module(upgrade)


class UpgradeQualificationTests(unittest.TestCase):
    def test_native_build_keeps_driver_and_production_isolated(self):
        root=Path(__file__).resolve().parents[1]
        dockerfile=(root/'deploy/truenas/Dockerfile.ffmpeg-qualification').read_text()
        launcher=(root/'deploy/truenas/launch-ffmpeg-qualification.sh').read_text()
        self.assertIn('nv-codec-headers-n13.0.19.0',dockerfile)
        self.assertIn('ffmpeg-9.0.2.tar.xz',dockerfile)
        self.assertIn('dst=/media,readonly',launcher)
        self.assertIn('dst=/output,readonly',launcher)
        self.assertIn('--cap-drop ALL',launcher)
        self.assertNotIn('docker stop',launcher)
        self.assertNotIn('--privileged',launcher)
        self.assertNotIn('nvidia-driver',dockerfile)

    def test_linux_guard_precedes_runtime_execution(self):
        with patch.object(upgrade.sys,'platform','win32'),patch.object(upgrade.subprocess,'check_output') as execute:
            with self.assertRaisesRegex(RuntimeError,'Linux-only'):upgrade.main()
            execute.assert_not_called()

    def test_download_requires_exact_pinned_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);payload=b'fixture'
            with patch.object(upgrade.urllib.request,'urlopen',return_value=io.BytesIO(payload)):
                upgrade.fetch_verified('fixture',root/'valid',hashlib.sha256(payload).hexdigest())
            with patch.object(upgrade.urllib.request,'urlopen',return_value=io.BytesIO(payload)):
                with self.assertRaisesRegex(ValueError,'checksum'):
                    upgrade.fetch_verified('fixture',root/'changed','0'*64)

    def test_archive_does_not_accept_symlinks_or_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for index,kind in enumerate(('symlink','traversal')):
                archive=root/(str(index)+'.tar')
                with tarfile.open(archive,'w') as target:
                    info=tarfile.TarInfo('runtime/bin/ffmpeg' if kind=='symlink' else '../../outside')
                    if kind=='symlink':info.type=tarfile.SYMTYPE;info.linkname='/usr/bin/ffmpeg'
                    target.addfile(info)
                with self.assertRaisesRegex(ValueError,'Unsafe'):
                    upgrade.unpack_verified(archive,root/'unpacked')
