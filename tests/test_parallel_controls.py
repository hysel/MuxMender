from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
import control_service as cs


class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);media=root/'media';media.mkdir();output=root/'output';output.mkdir()
        self.c=cs.Controls(media,output,lambda _:True,['hevc']);self.c.ready=True

    def queue(self,names):
        for name in names:(self.c.media/name).write_bytes(b'video')
        draft=self.c.preview(dict(path='.',mode='analyze'));self.c.submit(draft['preview_id'])

    def test_two_workers_claim_distinct_files(self):
        self.queue(['one.mkv','two.mkv'])
        barrier=threading.Barrier(2);commands=[]
        def start(command,**kwargs):
            commands.append(command)
            return Mock(wait=lambda:barrier.wait(timeout=5) and 0)
        with patch.object(cs.subprocess,'Popen',side_effect=start):
            workers=[threading.Thread(target=self.c.worker_step) for _ in range(2)]
            for worker in workers:worker.start()
            for worker in workers:worker.join(7)
        self.assertTrue(all(not w.is_alive() for w in workers))
        self.assertEqual(len(commands),2)
        self.assertEqual([j['state'] for j in self.c.state['jobs']],['analyzed','analyzed'])
        self.assertFalse(self.c.children)

    def test_destination_claim_is_exclusive(self):
        self.queue(['same.avi','same.mkv'])
        self.c.state['jobs'][0]['state']='running'
        with patch.object(cs.subprocess,'Popen') as process:self.c.step();process.assert_not_called()
        self.assertEqual(self.c.state['jobs'][1]['state'],'pending')

    def test_scratch_reservations_cover_other_jobs(self):
        self.queue(['one.mkv','two.mkv'])
        self.c.state['jobs'][0].update(state='running',signature=[10*1024**3,1])
        with patch.object(cs.shutil,'disk_usage',return_value=Mock(free=20*1024**3)),patch.object(cs.subprocess,'Popen') as process:
            self.c.step();process.assert_not_called()
        self.assertIn('space',self.c.error)

    def test_profile_persisted_and_validated(self):
        self.c.action(dict(action='resource-profile',profile='quiet'))
        self.assertEqual(cs.read(self.c.file)['resource_profile'],'quiet')
        with self.assertRaises(ValueError):self.c.action(dict(action='resource-profile',profile='unlimited'))

    def test_shutdown_signals_every_child(self):
        first=Mock(pid=101,poll=lambda:None);second=Mock(pid=102,poll=lambda:None)
        self.c.children={'a':first,'b':second}
        with patch.object(cs.os,'killpg',create=True) as kill:self.c.stop()
        self.assertEqual(kill.call_count,2)


if __name__=='__main__':unittest.main()
