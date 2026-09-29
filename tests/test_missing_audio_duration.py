import tempfile
import unittest
from pathlib import Path
from packet_validation import missing_audio_duration_case
from auto_optimize import compare_packets


class MissingAudioDurationTests(unittest.TestCase):
    def test_only_missing_output_duration_with_identical_packets_and_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b'
            a.write_text('pts_time=0|dts_time=0|duration_time=0.085333|data_hash=abc\n')
            b.write_text('pts_time=0|dts_time=0|duration_time=N/A|data_hash=abc\n')
            self.assertEqual(missing_audio_duration_case(a,b),1)
            with self.assertRaises(ValueError):compare_packets(a,b)
            compare_packets(a,b,audio_duration_verified=1)
            with self.assertRaises(ValueError):compare_packets(a,b,audio_duration_verified=2)
            for changed in ('pts_time=1|dts_time=0|duration_time=N/A|data_hash=abc',
                            'pts_time=0|dts_time=0|duration_time=N/A|data_hash=changed',
                            'pts_time=0|dts_time=0|duration_time=0.2|data_hash=abc'):
                b.write_text(changed+'\n');self.assertIsNone(missing_audio_duration_case(a,b))
