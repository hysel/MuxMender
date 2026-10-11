import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


class ApprovedCopyPublicationTests(unittest.TestCase):
    def test_windows_cannot_publish(self):
        path=Path(__file__).resolve().parents[1]/'tools'/'publish_approved_copies.py'
        spec=importlib.util.spec_from_file_location('approved_copies',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module.sys,'platform','win32'):
            with self.assertRaisesRegex(RuntimeError,'Linux app only'):module.main()

    def test_uses_shared_publication_and_receipts_not_queue_rewrites(self):
        text=(Path(__file__).resolve().parents[1]/'tools'/'publish_approved_copies.py').read_text()
        self.assertIn('record=replace_validated(',text)
        self.assertIn("'approved-replacement.json'",text)
        self.assertIn('tracked_call(run',text)
        self.assertNotIn('write(root/',text)


if __name__=='__main__':unittest.main()
