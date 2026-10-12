"""Image launch guards and package smoke coverage; never execute Linux media."""
from pathlib import Path
import unittest
from unittest.mock import patch
from tools import smoke_app_release


class ReleaseSmokeTests(unittest.TestCase):
    def test_public_context_excludes_private_reader_receipts(self):
        from tools.prepare_public_candidate import public_reader_member
        for name in ('qualification.json','evidence.json','README.md'):
            self.assertFalse(public_reader_member('vendor/gpu-reader/'+name))
        self.assertTrue(public_reader_member('vendor/gpu-reader/ffprobe-cuda'))
        self.assertTrue(public_reader_member('vendor/gpu-reader/source/LICENSE.md'))
        text=(Path(__file__).resolve().parents[1]/'deploy/truenas/Dockerfile.public').read_text()
        self.assertNotIn('COPY vendor/gpu-reader/ /opt/',text)

    def test_missing_api_requires_explicit_stopped_container(self):
        text=(Path(__file__).resolve().parents[1]/'deploy/truenas/launch-public-candidate.sh').read_text()
        self.assertIn("assert state=='false'",text)
        self.assertIn('{{.State.Running}}',text)
        self.assertNotIn('docker start',text)
        self.assertNotIn('docker stop',text)

    def test_public_gpu_option_reaches_shared_smoke(self):
        with patch.object(smoke_app_release.sys,'platform','linux'),patch.object(
                smoke_app_release.sys,'argv',['smoke','gpu','--version','20261010-v60','--public-runtime']),patch.object(
                smoke_app_release,'gpu') as gpu:
            smoke_app_release.main()
            gpu.assert_called_once_with(public_runtime=True)

    def test_public_runtime_option_reaches_shared_smoke(self):
        with patch.object(smoke_app_release.sys,'platform','linux'), patch.object(
                smoke_app_release.sys,'argv',['smoke','runtime','--version','20261010-v60','--public-runtime']), patch.object(
                smoke_app_release,'runtime') as runtime:
            smoke_app_release.main()
            runtime.assert_called_once_with('20261010-v60', public_runtime=True)

    def test_public_base_does_not_inherit_nonfree_image(self):
        text=(Path(__file__).resolve().parents[1]/'deploy/truenas/Dockerfile.public').read_text()
        bases=[line for line in text.splitlines() if line.startswith('FROM ')]
        self.assertEqual(len(bases),3)
        self.assertTrue(all('ubuntu:24.04@sha256:' in line for line in bases))
        self.assertNotIn('linuxserver/ffmpeg',text)
        self.assertIn('COPY LICENSE',text)
        self.assertIn('COPY public-materials/',text)

    def test_windows_guard_precedes_any_launch(self):
        with patch.object(smoke_app_release.sys,'platform','win32'),patch.object(smoke_app_release.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'Linux-only'):smoke_app_release.main()
            run.assert_not_called()

    def test_stage_does_not_bind_production_media_or_resume_queue(self):
        text=(Path(__file__).resolve().parents[1]/'deploy/truenas/stage-release.sh').read_text()
        self.assertIn('systemd-run',text)
        self.assertIn('--network none',text)
        self.assertIn('$smoke_root/media,dst=/media,readonly',text)
        self.assertNotIn('docker compose',text)
        self.assertNotIn('ix-muxmender-muxmender-1',text)
        self.assertNotIn('image prune',text)
        self.assertIn('.source-sha256',text)
