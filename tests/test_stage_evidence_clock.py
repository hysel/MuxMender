import unittest

from tools.monitor_remote_research import StageEvidenceClock


class StageEvidenceClockTests(unittest.TestCase):
    def test_legacy_first_snapshot_and_heartbeats_are_not_progress(self):
        clock=StageEvidenceClock()
        state=dict(started=1,phase='Read',stage_percent=10,updated=100)
        self.assertIsNone(clock.timestamp(state,100))
        self.assertIsNone(clock.timestamp(dict(state,updated=110),110))
        state.update(stage_percent=11)
        self.assertEqual(clock.timestamp(state,120),120)
        self.assertEqual(clock.timestamp(dict(state,updated=140),140),120)
        self.assertIsNone(clock.timestamp(dict(state,updated=181),181))

    def test_new_phase_or_worker_requires_new_evidence(self):
        clock=StageEvidenceClock()
        state=dict(stage_identity=[1,1,'Read',1],stage_percent=10)
        clock.timestamp(state,100)
        self.assertEqual(clock.timestamp(dict(state,stage_percent=11),110),110)
        self.assertIsNone(clock.timestamp(dict(state,stage_identity=[2,2,'Read',2]),120))
        self.assertIsNone(clock.timestamp(None,130))
        self.assertIsNone(clock.timestamp(state,140))

    def test_explicit_timestamp_is_authoritative_not_refreshed_by_movement(self):
        clock=StageEvidenceClock()
        state=dict(phase='Read',stage_percent=10,stage_updated=99)
        self.assertEqual(clock.timestamp(state,100),99)
        self.assertIsNone(clock.timestamp(dict(state,stage_percent=20),170))
        self.assertIsNone(clock.timestamp(dict(state,stage_updated=200),180))

    def test_waiting_and_invalid_percent_clear_evidence(self):
        for value in (None,float('nan'),float('inf'),-1,101,True,'50'):
            clock=StageEvidenceClock()
            self.assertIsNone(clock.timestamp(dict(stage_percent=value,stage_updated=100),100))


if __name__ == '__main__':
    unittest.main()
