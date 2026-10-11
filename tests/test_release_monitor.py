import unittest
from tools.monitor_release_stage import interpret,read_command


class ReleaseMonitorTests(unittest.TestCase):
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
