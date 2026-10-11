import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / ('tools/' + name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class PublicInstallation(unittest.TestCase):
    def test_preview_uses_api_settings_envelope(self):
        target = module('check_public_installation')
        self.assertEqual(target.history_preview(), dict(action='preview',
            settings=dict(path='Example.mkv', mode='keep')))

    def test_installation_never_executes_on_windows(self):
        target = module('check_public_installation')
        with tempfile.TemporaryDirectory() as work, patch.object(target.sys, 'platform', 'win32'), patch.object(target.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(RuntimeError, 'Linux-only'):
                target.check('initialize', work)
            launch.assert_not_called()

    def test_source_collection_never_executes_on_windows(self):
        target = module('collect_release_sources')
        with patch.object(target.sys, 'platform', 'win32'), patch.object(target.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Linux-only'):
                target.collect('unused')
            run.assert_not_called()

    def test_launcher_uses_generated_work_and_no_gpu(self):
        text = (Path(__file__).resolve().parents[1] / 'deploy/truenas/check-public-installation.sh').read_text()
        self.assertIn('mktemp -d', text)
        self.assertIn('--network none', text)
        self.assertEqual(text.count('--memory 12g'), 2)
        self.assertEqual(text.count('--memory 2g'), 1)
        self.assertNotIn('--gpus', text)
        self.assertNotIn('docker stop', text)
        self.assertNotIn('docker rm', text)
