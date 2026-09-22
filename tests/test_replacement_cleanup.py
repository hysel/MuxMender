import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_validated_replace as fixtures
import replacement_cleanup as cleanup


class CleanupTests(unittest.TestCase):
    setUp=fixtures.ReplacementTests.setUp
    save=fixtures.ReplacementTests.save
    run_replace=fixtures.ReplacementTests.run_replace
    def prepare_retained(self):
        with patch('replacement_cleanup.cleanup_replaced',return_value={'state':'held'}):
            self.run_replace()
        (self.run/'reference.mkv').write_bytes(b'reference')
        (self.run/'quality.json').write_text('{}')

    def test_preview_does_not_delete_and_execution_keeps_receipts(self):
        self.prepare_retained()
        self.assertEqual(cleanup.cleanup_replaced(self.run)['files'],2)
        self.assertTrue(self.output.exists())
        result=cleanup.cleanup_replaced(self.run,execute=True)
        self.assertEqual(result['state'],'cleaned')
        self.assertFalse(self.output.exists())
        self.assertTrue((self.run/'quality.json').exists())
        self.assertTrue((self.run/'replacement.json').exists())
        self.assertEqual(cleanup.checksum(self.source),self.status['output_sha256'])
        self.assertEqual(cleanup.cleanup_replaced(self.run,execute=True)['files'],0)

    def test_changed_publication_prevents_cleanup(self):
        self.prepare_retained();self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):cleanup.cleanup_replaced(self.run,execute=True)
        self.assertTrue(self.output.exists())

    def test_cleanup_error_does_not_undo_replaced_status(self):
        with patch('replacement_cleanup.cleanup_replaced',side_effect=OSError('disk error')):
            result=self.run_replace()
        self.assertEqual(result['state'],'replaced')
        self.assertEqual(result['artifact_cleanup']['state'],'needs-attention')

    def test_recovery_marker_prevents_cleanup(self):
        self.prepare_retained()
        record=json.loads((self.run/'replacement.json').read_text())
        Path(record['backup']).write_bytes(b'recovery')
        with self.assertRaises(ValueError):cleanup.cleanup_replaced(self.run,execute=True)
        self.assertTrue(self.output.exists())

    def test_shared_inode_is_retained(self):
        import os
        self.prepare_retained()
        link=self.run/'shared.mkv';os.link(self.source,link)
        cleanup.cleanup_replaced(self.run,execute=True)
        self.assertTrue(link.exists())
        self.assertTrue(self.source.exists())

    def test_source_inside_work_directory_is_rejected(self):
        self.prepare_retained()
        for name in ('status.json','replacement.json'):
            path=self.run/name;record=json.loads(path.read_text())
            record['source']=str(self.run/'reference.mkv');path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):cleanup.cleanup_replaced(self.run,execute=True)
        self.assertTrue((self.run/'reference.mkv').exists())
