import unittest
from tools.recover_crate_notices import github_repository,selected_notice


class NoticeRecovery(unittest.TestCase):
    def test_repository_is_fixed_read_only_identity(self):
        self.assertEqual(github_repository('https://github.com/example/demo/tree/main/crates/x'),'example/demo')
        self.assertEqual(github_repository('https://github.com/example/demo.git'),'example/demo')
        for url in ('file:///repo','https://evil.invalid/demo','https://github.com/../demo'):
            with self.assertRaises(ValueError):github_repository(url)

    def test_only_root_or_crate_ancestor_notices_selected(self):
        self.assertTrue(selected_notice('LICENSE-MIT','crates/demo'))
        self.assertTrue(selected_notice('crates/LICENSE','crates/demo'))
        self.assertTrue(selected_notice('LICENSES/MIT.txt','crates/demo'))
        self.assertTrue(selected_notice('AUTHORS','crates/demo'))
        self.assertFalse(selected_notice('unrelated/LICENSE','crates/demo'))
        with self.assertRaises(ValueError):selected_notice('../LICENSE')
