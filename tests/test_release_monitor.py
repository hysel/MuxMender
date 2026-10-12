import unittest
from tools.monitor_release_stage import interpret,read_command


class ReleaseMonitorTests(unittest.TestCase):
    def test_revised_materials_observer_tracks_separate_batch(self):
        command=read_command('20261010-v60',public_materials=True,candidate_revision='r3')
        self.assertIn('public-final-checks-20261012-r1',command)
        self.assertIn('source_progress=',command)
        self.assertNotIn('docker ',command)
    def test_cancellation_observer_is_read_only_and_scoped(self):
        command=read_command('20261010-v60',public_cancel=True)
        self.assertIn('public-cancellation-20261012-r1',command)
        self.assertNotIn('docker ',command)
        with self.assertRaises(ValueError):
            read_command('20261010-v60',public_cancel=True,public_copy=True)
    def test_conflicting_tasks_are_rejected(self):
        with self.assertRaises(ValueError):
            read_command('20261010-v60',public_scan=True,public_copy=True)

    def test_unstarted_scan_has_no_build_or_success_claim(self):
        status,terminal=interpret('status=awaiting-admin\nunit=inactive',waiting_phase='Waiting for administrator to start security scan')
        self.assertEqual(status['phase'],'Waiting for administrator to start security scan')
        self.assertFalse(terminal)
        self.assertEqual(status['state'],'pending')

    def test_public_scan_is_read_only_and_scoped(self):
        self.assertIn('public-security-20261012-r1',read_command('20261010-v60',public_scan=True,candidate_revision='r3'))
        command=read_command('20261010-v60',public_scan=True)
        self.assertIn('public-security-20261011-r1',command)
        self.assertNotIn('docker ',command)
    def test_candidate_revision_is_fixed_and_read_only(self):
        self.assertIn('public-image-20261012-r1',read_command('20261010-v60',True,candidate_revision='r3'))
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
