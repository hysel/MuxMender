import unittest
from trial_failures import structural_failure_code, previous_structural_failure


class TrialFailureTests(unittest.TestCase):
    def test_only_proven_setting_invariant_errors_are_deduplicated(self):
        self.assertEqual(structural_failure_code('Frame 0: chroma location changed'),
                         'chroma_siting_preservation')
        for message in ('Frame 0: timestamp changed or non-increasing',
                        'Decoder errors', 'Stage timed out', 'Insufficient free output space',
                        'VMAF below threshold', 'Frame count changed'):
            self.assertIsNone(structural_failure_code(message))

    def test_failure_is_encoder_scoped_and_not_a_global_gate(self):
        trials=[dict(id='av1-balanced',encoder='av1_nvenc',structural_failure='chroma_siting_preservation')]
        self.assertIsNone(previous_structural_failure(trials,'hevc_nvenc'))
        self.assertIsNone(previous_structural_failure(trials,'av1_qsv'))
        self.assertEqual(previous_structural_failure(trials,'av1_nvenc')['id'],'av1-balanced')
