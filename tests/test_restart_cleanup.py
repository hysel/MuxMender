import json
import os
from pathlib import Path
import tempfile
import unittest
from control_service import Controls


@unittest.skipUnless(os.name=='posix','Worker ownership lock requires Linux')
class RestartCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);media=root/'media';media.mkdir();out=root/'out';out.mkdir()
        self.source=media/'source.mkv';self.source.write_bytes(b'original')
        self.c=Controls(media,out,lambda _:True,['hevc'])
        folder=self.c.root/'request-test';folder.mkdir();self.run=folder/'auto-test';self.run.mkdir()
        self.generated=self.run/'audio.thd';self.generated.write_bytes(b'temporary')
        self.job=dict(id='test',source=str(self.source),state='failed',output=str(folder))
        self.c.state['jobs']=[self.job]
        (self.run/'status.json').write_text(json.dumps(dict(state='stopped-original-retained',original_retained=True,source=str(self.source))))
        self.c.stop_event.set()

    def test_known_terminal_work_is_reconciled(self):
        self.c.loop()
        self.assertFalse(self.generated.exists())
        self.assertEqual(self.source.read_bytes(),b'original')
        self.assertEqual(self.job['artifact_cleanup']['state'],'cleaned')

    def test_killed_active_work_is_not_automatically_deleted(self):
        self.job['state']='running';self.c.loop()
        self.assertTrue(self.generated.exists())
        self.assertEqual(self.job['state'],'interrupted')
        self.assertEqual(self.job['artifact_cleanup']['state'],'needs-attention')

    def test_recovery_journal_protects_outputs(self):
        (self.run/'replacement.json').write_text('{}');self.c.loop()
        self.assertTrue(self.generated.exists())
        self.assertEqual(self.job['artifact_cleanup']['state'],'needs-attention')

    def test_invalid_old_status_does_not_disable_worker_initialization(self):
        (self.run/'status.json').write_text('{bad');self.c.loop()
        self.assertIsNone(self.c.error)
        self.assertTrue(self.generated.exists())
        self.assertEqual(self.job['artifact_cleanup']['state'],'needs-attention')
