import json
import tempfile
import unittest
from pathlib import Path
from batch_dashboard import batches,read,save_review
from ui.batch import HTML,STYLE
from ui import HTML as ORIGINAL

class BatchDashboardTests(unittest.TestCase):
    def test_review_persists_and_unknown_target_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run=root/'run';run.mkdir()
            (run/'status.json').write_text(json.dumps([dict(source='movie.mkv',state='verified_pending_playback')]))
            batch=batches([root])[0];row=batch['episodes'][0]
            request=dict(batch=batch['id'],episode=row['review_id'],client='Chrome',status='Passed',note='Looks good')
            save_review([root],request)
            self.assertEqual(batches([root])[0]['episodes'][0]['reviews']['Chrome']['status'],'Passed')
            with self.assertRaises(ValueError):save_review([root],dict(request,batch='../elsewhere'))
            with self.assertRaises(ValueError):save_review([root],dict(request,status='Invented'))
    def test_uses_original_styles(self):
        self.assertIn(STYLE,ORIGINAL)
        self.assertIn('setTimeout(refresh,3000)',HTML)
        self.assertNotIn('innerHTML',HTML)
    def test_historical_batch_is_not_automatic_playback_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run=root/'run';run.mkdir()
            (run/'status.json').write_text(json.dumps([dict(source='source.mkv',episode='S01E01',state='verified_pending_playback',output_bytes=50,saved_percent=50)]))
            data=batches([root])
            row=data[0]['episodes'][0]
            self.assertEqual(row['verification'],'Passed')
            self.assertEqual(row['playback'],'Not recorded')
            self.assertEqual(row['output_bytes'],50)
    def test_external_report_is_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inside=root/'inside';inside.mkdir()
            outside=root/'secret.json';outside.write_text('{"secret":true}')
            self.assertIsNone(read(outside,inside))
    def test_malformed_and_unrelated_records_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run=root/'run';run.mkdir()
            (run/'status.json').write_text('not json')
            self.assertEqual(batches([root]),[])
