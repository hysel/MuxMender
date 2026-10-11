import unittest
from tools.monitor_release_stage import interpret,read_command


class ReleaseMonitorTests(unittest.TestCase):
    def test_candidate_revision_is_fixed_and_read_only(self):
        self.assertIn('public-image-20261011-r2',read_command('20261010-v60',True,candidate_revision='r2'))
        with self.assertRaises(ValueError):read_command('20261010-v60',True,candidate_revision='r2;whoami')
    def test_source_count_is_stage_progress_not_release_completion(self):
        status,terminal=interpret('status=running\nphase=Collecting exact Ubuntu sources and license notices\nunit=active\nsource_progress={"completed": 12, "total": 24, "updated": 100}')
        self.assertEqual(status['stage_percent'],50)
        self.assertEqual(status['state'],'running');self.assertFalse(terminal)
        status,terminal=interpret('status=running\nunit=active\nsource_progress=broken')
        self.assertEqual(status['state'],'running');self.assertFalse(terminal)

    def test_unstarted_and_active_build_are_distinct(self):
        self.assertEqual(interpret('status=awaiting-admin\nunit=inactive')[0]['state'],'pending')
        status,terminal=interpret('status=running\nphase=GPU tests\nunit=active')
        self.assertEqual(status['state'],'running');self.assertFalse(terminal)

    def test_stale_worker_does_not_imply_success(self):
        status,terminal=interpret('status=running\nunit=inactive')
        self.assertEqual(status['state'],'failed');self.assertTrue(terminal)
        self.assertEqual(interpret('status=passed\nunit=inactive')[0]['state'],'completed')
        self.assertEqual(interpret('status=failed\nexit_code=1')[0]['state'],'failed')
        with self.assertRaises(ValueError):interpret('')

    def test_remote_command_uses_only_validated_version_and_read_only_checks(self):
        command=read_command('20261007-v56')
        self.assertNotIn('docker ',command);self.assertNotIn('sudo ',command)
        for value in ('../../tmp','v56;whoami','20261007-v56\nrm'):
            with self.assertRaises(ValueError):read_command(value)
