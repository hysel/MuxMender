import tempfile
import unittest
from unittest.mock import patch
import job_tracking as tracking


class WorkflowStageTests(unittest.TestCase):
    def test_subcheck_progress_does_not_change_workflow_step(self):
        with tempfile.TemporaryDirectory() as folder:
            job=tracking.Job(folder,'test')
            with patch.object(tracking,'_active',job):
                tracking.workflow_stage('encode')
                tracking.progress('full-encode')
                tracking.stage_progress(100,0)
                self.assertEqual(job.data['workflow_stage'],'encode')
                tracking.workflow_stage('validate')
                self.assertIsNone(job.data['stage_percent'])
                self.assertEqual(job.data['workflow_stage'],'validate')
                tracking.progress('Checking copied tracks')
                self.assertEqual(job.data['workflow_stage'],'validate')

    def test_unknown_workflow_stage_is_rejected(self):
        with self.assertRaises(ValueError):tracking.workflow_stage('made-up-stage')
