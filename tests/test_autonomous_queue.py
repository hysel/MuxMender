import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import autonomous_queue as aq


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root/'media'
        self.scope = self.media/aq.SCOPE
        self.scope.mkdir(parents=True)
        self.output = self.root/'output'; self.output.mkdir()
        self.source = self.scope/'episode.mkv'; self.source.write_bytes(b'original media')
        self.queue = aq.Queue(self.media, self.output, ['hevc','av1'], lambda p:True)

    def worker(self, cmd, **kwargs):
        folder = Path(cmd[cmd.index('--output-dir')+1])/'auto-fixture'
        folder.mkdir()
        aq.write(folder/'status.json', dict(state='trials-completed', decision=dict(action='keep_original',reason='Quality failed')))
        return Mock(wait=lambda:0)

    def test_source_protection_dedup_and_restart(self):
        with patch.object(aq.subprocess,'Popen',side_effect=self.worker) as process:
            self.queue.step(); self.queue.step()
            self.assertEqual(process.call_count,1)
            resumed = aq.Queue(self.media,self.output,['hevc'],lambda p:True)
            resumed.state = aq.read(resumed.file)
            resumed.step()
            self.assertEqual(process.call_count,1)
        self.assertEqual(self.source.read_bytes(),b'original media')
        entry = next(iter(self.queue.snapshot()['entries'].values()))
        self.assertEqual(entry['state'],'skipped')
        cmd = aq.command(self.source,self.output,['av1'])
        self.assertIn('--encode-best',cmd)
        self.assertNotIn('--adaptive',cmd)
        self.assertEqual(cmd[cmd.index('--hardware')+1],'auto')

    def test_changed_source_can_be_evaluated_again(self):
        with patch.object(aq.subprocess,'Popen',side_effect=self.worker) as process:
            self.queue.step()
            self.source.write_bytes(b'changed media content')
            self.queue.step()
            self.assertEqual(process.call_count,2)

    def test_import_terminal_history_by_hash_not_name(self):
        folder=self.output/'old';folder.mkdir()
        sha=hashlib.sha256(self.source.read_bytes()).hexdigest()
        aq.write(folder/'status.json',dict(source=str(self.source),state='validated-copy-awaiting-playback',source_sha256=sha,output_sha256='different'))
        with patch.object(aq.subprocess,'Popen') as process:
            self.queue.step();process.assert_not_called()
        self.assertEqual(self.queue.state['entries']['episode.mkv']['state'],'previously-processed')

    def test_readonly_scope_and_codec_guards(self):
        with self.assertRaises(ValueError):aq.Queue(self.media,self.output,['av1'],lambda p:False)
        with self.assertRaises(ValueError):aq.Queue(self.media,self.output,[],lambda p:True)
        with self.assertRaises(ValueError):aq.Queue(self.media,self.media,['av1'],lambda p:True)
        outside=self.media/'outside.mkv';outside.write_bytes(b'outside')
        self.assertEqual(list(self.queue.files()),[self.source])

    def test_pause_low_space_and_other_job_block_start(self):
        with patch.object(aq.subprocess,'Popen') as process:
            self.queue.pause.touch();self.queue.step()
            self.assertEqual(self.queue.state['state'],'paused')
            self.queue.pause.unlink()
            with patch.object(aq.shutil,'disk_usage',return_value=Mock(free=1)):
                self.queue.step()
            self.assertEqual(self.queue.state['state'],'paused-low-space')
            self.queue.busy=lambda:True;self.queue.step()
            self.assertEqual(self.queue.state['state'],'waiting')
            process.assert_not_called()

    def test_two_failures_pause_without_retry(self):
        (self.scope/'second.mkv').write_bytes(b'second source')
        with patch.object(aq.subprocess,'Popen',return_value=Mock(wait=lambda:1)) as process:
            self.queue.step();self.queue.step();self.queue.step()
            self.assertEqual(process.call_count,2)
        self.assertTrue(self.queue.pause.exists())

    def test_outcome_requires_validated_result_not_zero_exit(self):
        self.assertEqual(aq.outcome(self.output,0)[0],'failed')
        folder=self.output/'auto-fixture';folder.mkdir()
        aq.write(folder/'status.json',dict(state='validated-copy-awaiting-playback'))
        self.assertEqual(aq.outcome(self.output,0)[0],'awaiting-playback')
        self.assertEqual(aq.outcome(self.output,1)[0],'failed')

    @unittest.skipUnless(os.name == 'posix', 'Linux service lock')
    def test_restart_marks_interrupted_and_pauses(self):
        self.queue.state['entries']['episode.mkv'] = dict(state='running',signature=aq.signature(self.source))
        self.queue.save()
        self.queue.stop_event.set()
        self.queue.loop()
        self.assertTrue(self.queue.pause.exists())
        self.assertEqual(self.queue.snapshot()['entries']['episode.mkv']['state'],'interrupted')

    @unittest.skipUnless(os.name == 'posix', 'Linux service lock')
    def test_second_queue_cannot_overwrite_owner_state(self):
        import fcntl
        self.queue.save('processing','Owner running')
        with (self.queue.root/'queue.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.queue.loop()
        self.assertEqual(self.queue.snapshot()['detail'],'Owner running')


if __name__=='__main__':unittest.main()
