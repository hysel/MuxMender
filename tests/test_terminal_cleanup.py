import json
import os
from pathlib import Path
import tempfile
import unittest
from replacement_cleanup import cleanup_terminal


class TerminalCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.source=root/'source.mkv';self.source.write_bytes(b'original')
        self.run=root/'run';self.run.mkdir()
        self.status=dict(state='full-output-rejected-insufficient-savings',source=str(self.source),original_retained=True)
        self.save()
        (self.run/'full.mkv').write_bytes(b'generated')
        for name in ['full-frames.jsonl','full-stream-1.txt','full-all-packets.txt','audio.framehash']:
            (self.run/name).write_text('large evidence')
        (self.run/'trials.json').write_text('{}')
        (self.run/'error.log').write_text('reason')

    def save(self):(self.run/'status.json').write_text(json.dumps(self.status))

    def test_terminal_cleanup_keeps_source_and_compact_history(self):
        self.assertEqual(cleanup_terminal(self.run)['files'],5)
        cleanup_terminal(self.run,execute=True)
        self.assertEqual(self.source.read_bytes(),b'original')
        for name in ['status.json','trials.json','error.log','artifact-cleanup.jsonl']:
            self.assertTrue((self.run/name).exists())
        self.assertEqual(cleanup_terminal(self.run)['files'],0)

    def test_active_review_and_sample_success_are_protected(self):
        for state in ['running','validated-copy-awaiting-playback','trials-completed']:
            self.status.update(state=state,decision={'action':'encode_copy'});self.save()
            with self.assertRaises(ValueError):cleanup_terminal(self.run,execute=True)
        self.assertTrue((self.run/'full.mkv').exists())

    def test_internal_hardlinks_removed_external_links_retained(self):
        os.link(self.run/'full.mkv',self.run/'intermediate.mkv')
        os.link(self.source,self.run/'shared.mkv')
        cleanup_terminal(self.run,execute=True)
        self.assertFalse((self.run/'full.mkv').exists())
        self.assertFalse((self.run/'intermediate.mkv').exists())
        self.assertTrue((self.run/'shared.mkv').exists())
        self.assertEqual(self.source.read_bytes(),b'original')

    def test_recovery_evidence_and_missing_source_prevent_deletion(self):
        (self.run/'replacement.json').write_text('{}')
        with self.assertRaises(ValueError):cleanup_terminal(self.run,execute=True)
        (self.run/'replacement.json').unlink();self.source.unlink()
        with self.assertRaises(FileNotFoundError):cleanup_terminal(self.run,execute=True)
        self.assertTrue((self.run/'full.mkv').exists())

    def test_status_change_in_guard_stops_cleanup(self):
        def change():self.status['state']='running';self.save()
        with self.assertRaises(ValueError):cleanup_terminal(self.run,execute=True,guard=change)
        self.assertTrue((self.run/'full.mkv').exists())

    def test_source_inside_cleanup_root_rejected(self):
        self.status['source']=str(self.run/'full.mkv');self.save()
        with self.assertRaises(ValueError):cleanup_terminal(self.run,execute=True)


if __name__=='__main__':unittest.main()
