import unittest
from gpu_activity import parse_pmon, YieldPolicy, belongs_to_owner


class ActivityTests(unittest.TestCase):
    def sample(self, usage=10, namespace='outside', gpu='GPU-a', now=100):
        return dict(schema=1, complete=True, updated=now, gpus=['GPU-a','GPU-b'], processes=[
            dict(gpu=gpu, namespace=namespace, pid=10, start_ticks=50, name='other-app',
                 usage=dict(sm=usage,enc=None,dec=None))])

    def test_sustained_activity_cooldown_and_resume(self):
        policy=YieldPolicy()
        self.assertFalse(policy.decide(self.sample(),['GPU-a'],1,'self',now=100)['pause'])
        self.assertTrue(policy.decide(self.sample(now=106),['GPU-a'],1,'self',now=106)['pause'])
        self.assertTrue(policy.decide(self.sample(usage=0,now=120),['GPU-a'],1,'self',now=120)['pause'])
        self.assertFalse(policy.decide(self.sample(usage=0,now=167),['GPU-a'],1,'self',now=167)['pause'])

    def test_other_gpu_and_idle_memory_do_not_pause(self):
        for sample in (self.sample(usage=0),self.sample(gpu='GPU-b')):
            self.assertEqual(YieldPolicy().decide(sample,['GPU-a'],1,'self',now=100)['state'],'available')

    def test_missing_stale_unsupported_are_not_idle(self):
        for sample in ({}, [], self.sample(now=50),self.sample(usage=None)):
            result=YieldPolicy().decide(sample,['GPU-a'],1,'self',now=100)
            self.assertEqual(result['state'],'unavailable')
            self.assertTrue(result['block_admission'])
            self.assertFalse(result['pause'])

    def test_ownership_and_pid_reuse(self):
        row=self.sample(namespace='self')['processes'][0]
        identities={10:dict(start_ticks=50,parent=1),1:dict(start_ticks=1,parent=0)}
        self.assertTrue(belongs_to_owner(row,1,'self',identities.__getitem__))
        result=YieldPolicy().decide(self.sample(namespace='self'),['GPU-a'],1,'self',now=100,identity=identities.__getitem__)
        self.assertEqual(result['state'],'available')
        identities[10]['start_ticks']=60
        self.assertIsNone(belongs_to_owner(row,1,'self',identities.__getitem__))

    def test_pmon_header_and_unknown_engines(self):
        text='# gpu pid type sm mem enc dec jpg ofa fb ccpm command\n0 25 C 0 0 35 - - - 303 0 ffmpeg\n'
        row=parse_pmon(text,{0:'GPU-a'})[0]
        self.assertEqual(row['usage'],dict(sm=0,enc=35,dec=None))
        self.assertEqual(row['gpu'],'GPU-a')
        with self.assertRaises(ValueError):parse_pmon('unavailable',{})
