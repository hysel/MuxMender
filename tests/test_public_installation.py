import importlib.util
from pathlib import Path
import tempfile
import hashlib
import json
import unittest
from unittest.mock import patch


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / ('tools/' + name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class PublicInstallation(unittest.TestCase):
    def test_retained_copy_hash_is_checked_independently(self):
        target=module('check_public_installation')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);copy=root/'output.mkv';copy.write_bytes(b'fixture')
            record=dict(state='validated-copy-awaiting-playback',output=str(copy),
                        output_sha256=hashlib.sha256(b'fixture').hexdigest())
            (root/'status.json').write_text(json.dumps(record))
            self.assertEqual(target.validated_copy(root)['path'],'output.mkv')
            copy.write_bytes(b'changed')
            with self.assertRaisesRegex(AssertionError,'checksum changed'):target.validated_copy(root)
    def test_copy_launcher_never_mounts_library_or_restarts_production(self):
        text=(Path(__file__).resolve().parents[1]/'deploy/truenas/check-public-copy-lifecycle.sh').read_text()
        self.assertIn('initialize-copy',text)
        self.assertIn('upgrade-copy',text)
        for value in ('dst=/media','docker start','docker stop','docker.sock'):
            self.assertNotIn(value,text)
        self.assertIn("assert running=='false'",text)
    def test_full_copy_uses_existing_ui_settings_and_quality_profile(self):
        target=module('check_public_installation')
        settings=target.copy_preview()['settings']
        self.assertEqual(settings['mode'],'encode')
        self.assertEqual(settings['quality_profile'],'balanced')
        self.assertEqual(settings['minimum_savings'],25)
        self.assertNotIn('skip_validation',settings)
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
