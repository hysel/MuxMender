import unittest
from trial_failures import structural_failure_code, previous_structural_failure


class TrialFailureTests(unittest.TestCase):
    def test_only_exact_av1_duplicate_mux_error_is_deduplicated(self):
        message='Stage failed: [vost#0:0/av1_nvenc @ 0x123] Non-monotonic DTS; previous: 42, current: 42; Error submitting a packet to the muxer: Invalid argument'
        self.assertEqual(structural_failure_code(message),'av1_duplicate_decode_timestamp')
        for altered in (message.replace('current: 42','current: 41'),
                        message.replace('av1_nvenc','hevc_nvenc'),
                        'Non-monotonic DTS', 'Stage timed out'):
            self.assertIsNone(structural_failure_code(altered))
        trials=[dict(id='failed-av1',encoder='av1_nvenc',structural_failure=structural_failure_code(message))]
        self.assertIsNone(previous_structural_failure(trials,'hevc_nvenc'))

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
