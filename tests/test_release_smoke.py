"""Image launch guards and package smoke coverage; never execute Linux media."""
from pathlib import Path
import unittest
from unittest.mock import patch
from tools import smoke_app_release


class ReleaseSmokeTests(unittest.TestCase):
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
