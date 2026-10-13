import json
from pathlib import Path
import tempfile
import unittest
import sys
import subprocess
import time
from unittest.mock import patch
from resource_yield import CPUYieldPolicy
from gpu_activity import YieldController
from resource_governor import parallel_sdr_profile,parallel_sdr_quality_profile


class ResourceYieldTests(unittest.TestCase):
    def sample(self,host=95,own=50):
        return dict(app_cpu_scope=True,host_cpus=12,cpus=8,cpu_percent=host,container_cpu_percent=own)

    def test_does_not_pause_its_own_work(self):
        policy=CPUYieldPolicy()
        data=dict(self.sample(95,95),cpus=12)
        for now in range(0,30,5):self.assertFalse(policy.decide(data,now)['block_admission'])

    def test_sustained_load_and_quiet_hysteresis(self):
        policy=CPUYieldPolicy()
        self.assertFalse(policy.decide(self.sample(),0)['pause'])
        self.assertFalse(policy.decide(self.sample(),5)['pause'])
        self.assertTrue(policy.decide(self.sample(),10)['pause'])
        for now in range(15,75,5):self.assertTrue(policy.decide(self.sample(40,0),now)['pause'])
        self.assertFalse(policy.decide(self.sample(40,0),75)['pause'])

    def test_unknown_or_stale_samples_release_pause(self):
        for bad in ({},dict(self.sample(),app_cpu_scope=False),dict(self.sample(),cpu_percent=float('nan'))):
            policy=CPUYieldPolicy();policy.decide(self.sample(),0);policy.decide(self.sample(),10)
            self.assertFalse(policy.decide(bad,15)['pause'])
        policy=CPUYieldPolicy();policy.decide(self.sample(),0)
        self.assertFalse(policy.decide(self.sample(),100)['pause'])

    def test_combined_lease_releases_when_cpu_pressure_clears(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lease.json';controller=YieldController(path)
            state=controller.tick(False,resource=dict(pause=True,block_admission=True,reason='CPU contention'))
            self.assertTrue(state['pause']);self.assertTrue(json.loads(path.read_text())['pause'])
            controller.tick(False,resource=dict(pause=False,block_admission=False,reason='Available'))
            self.assertFalse(json.loads(path.read_text())['pause'])

    def test_clearing_cpu_cannot_override_gpu_pause(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lease.json';controller=YieldController(path)
            controller.gpus=['GPU-fixture'];controller.last_gpu_query=time.monotonic()
            gpu=dict(state='yielding',pause=True,block_admission=True,reason='Competing GPU work')
            with patch.object(controller.policy,'decide',return_value=gpu),patch('gpu_activity.os.readlink',return_value='fixture'):
                state=controller.tick(True,resource=dict(pause=False,block_admission=False,reason='CPU available'))
            self.assertTrue(state['pause']);self.assertEqual(state['reason'],'Competing GPU work')
            self.assertTrue(json.loads(path.read_text())['pause'])

    def test_av1_scoring_does_not_expand_decoder_or_hdr_scope(self):
        video=dict(codec_name='av1',pix_fmt='yuv420p',field_order='progressive')
        self.assertTrue(parallel_sdr_quality_profile(video))
        self.assertFalse(parallel_sdr_profile(video))
        for changes in (dict(pix_fmt='yuv420p10le'),dict(field_order='tt'),dict(color_transfer='smpte2084')):
            self.assertFalse(parallel_sdr_quality_profile(dict(video,**changes)))


@unittest.skipUnless(sys.platform=='linux','Native process signals run only on Linux')
class LinuxResourceYieldTests(unittest.TestCase):
    def test_cpu_pause_preserves_generated_video(self):
        from cooperative_pause import launch_owned,OwnedStagePause
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);lease=root/'lease.json'
            baseline=root/'baseline.md5';output=root/'paused.md5'
            source=['-f','lavfi','-i','testsrc2=size=64x64:rate=24:duration=2']
            prefix=['ffmpeg','-nostdin','-v','error']
            subprocess.run([*prefix,*source,'-f','framemd5',str(baseline)],check=True,timeout=10)
            child=launch_owned([*prefix,'-re',*source,'-f','framemd5',str(output)])
            pause=OwnedStagePause(child,lease);controller=YieldController(lease)
            try:
                time.sleep(.25)
                policy=CPUYieldPolicy()
                sample=dict(app_cpu_scope=True,host_cpus=12,cpus=8,cpu_percent=95,container_cpu_percent=50)
                policy.decide(sample,0)
                controller.tick(False,resource=policy.decide(sample,10))
                self.assertTrue(pause.update())
                time.sleep(.15)
                self.assertEqual(Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split()[0],'T')
                for now in range(15,76,5):state=policy.decide(dict(sample,cpu_percent=40,container_cpu_percent=0),now)
                controller.tick(False,resource=state)
                self.assertFalse(pause.update())
                self.assertEqual(child.wait(timeout=10),0)
                self.assertEqual(baseline.read_text(),output.read_text())
            finally:
                pause.resume()
                if child.poll() is None:child.kill()
                child.wait(timeout=5)
