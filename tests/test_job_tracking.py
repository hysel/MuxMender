import tempfile
import unittest
from unittest.mock import patch
from job_tracking import Job
import job_tracking


class JobTrackingTests(unittest.TestCase):
    def test_reader_progress_has_its_own_freshness_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            job=Job(folder,'fixture')
            with patch.object(job_tracking,'_active',job):
                with patch('job_tracking.time.time',return_value=123):
                    job_tracking.progress('Reading frames',stage_percent=0,stage_eta=None)
                self.assertEqual(job.data['stage_updated'],123)
                self.assertEqual(job.data['stage_percent'],0)
                with patch('job_tracking.time.time',return_value=124):
                    job_tracking.progress('Reading frames',stage_percent=25,stage_eta=30)
                self.assertEqual(job.data['stage_updated'],124)
                with patch('job_tracking.time.time',return_value=130):job.save()
                self.assertEqual(job.data['stage_updated'],124)  # Heartbeat is not evidence progress.
                job_tracking.progress('Waiting for validation resources',detail='No work started')
                self.assertIsNone(job.data['stage_updated'])
                self.assertIsNone(job.data['stage_percent'])

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
