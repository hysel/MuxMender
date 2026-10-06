"""Each research supervisor must decide yielding using its own ownership root."""
import unittest
from gpu_activity import YieldPolicy


class ResearchOwnershipTests(unittest.TestCase):
    def snapshot(self, external=False):
        rows=[dict(gpu='gpu-test',pid=12,start_ticks=120,namespace='research',
                   name='ffmpeg',usage={'enc':40})]
        if external:
            rows.append(dict(gpu='gpu-test',pid=99,start_ticks=990,namespace='other-app',
                             name='player',usage={'dec':20}))
        return dict(schema=1,updated=100,complete=True,gpus=['gpu-test'],processes=rows)

    def identity(self,pid):
        return {12:dict(start_ticks=120,parent=11),11:dict(start_ticks=110,parent=10),
                10:dict(start_ticks=100,parent=1)}[pid]

    def test_production_lease_is_not_a_research_pause_decision(self):
        production=YieldPolicy(sustained=0)
        research=YieldPolicy(sustained=0)
        self.assertTrue(production.decide(self.snapshot(),['gpu-test'],20,'production',
                                         now=100,identity=self.identity)['pause'])
        result=research.decide(self.snapshot(),['gpu-test'],10,'research',now=100,identity=self.identity)
        self.assertFalse(result['pause'])
        self.assertFalse(result['block_admission'])

    def test_research_still_yields_to_real_external_work(self):
        result=YieldPolicy(sustained=0).decide(self.snapshot(True),['gpu-test'],10,'research',
                                              now=100,identity=self.identity)
        self.assertTrue(result['pause'])
        self.assertTrue(result['block_admission'])

    def test_stale_telemetry_never_authorizes_new_work(self):
        result=YieldPolicy().decide(self.snapshot(),['gpu-test'],10,'research',
                                   now=120,identity=self.identity)
        self.assertEqual(result['state'],'unavailable')
        self.assertTrue(result['block_admission'])
