import tempfile
import unittest
from job_tracking import Job


class JobTrackingTests(unittest.TestCase):
    def test_new_phase_clears_previous_stage_telemetry(self):
        with tempfile.TemporaryDirectory() as folder:
            job=Job(folder,'fixture')
            job.save(phase='Encode',stage_percent=100,stage_eta=0,detail='Encoding complete')
            job.save(phase='Validate')
            self.assertIsNone(job.data['stage_percent'])
            self.assertIsNone(job.data['stage_eta'])
            self.assertIsNone(job.data['detail'])

    def test_same_phase_heartbeat_keeps_progress_and_explicit_new_progress_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            job=Job(folder,'fixture')
            job.save(phase='Encode',stage_percent=25,stage_eta=60,detail='25 frames')
            job.save(phase='Encode')
            self.assertEqual(job.data['stage_percent'],25)
            self.assertEqual(job.data['detail'],'25 frames')
            job.save(phase='Validate',stage_percent=5,detail='Checking frames')
            self.assertEqual(job.data['stage_percent'],5)
            self.assertEqual(job.data['detail'],'Checking frames')


if __name__=='__main__':unittest.main()
