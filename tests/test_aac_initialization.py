from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from packet_validation import aac_initialization_timestamp_case, compare_decoded_audio
from auto_optimize import compare_packets


class AACInitializationTests(unittest.TestCase):
    def test_missing_duration_only_on_first_packet_with_pcm_proof_required(self):
        with TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b'
            a.write_text('pts_time=0|dts_time=0|duration_time=0.02|data_hash=SHA256:a\n'
                         'pts_time=0.02|dts_time=0.02|duration_time=0.02|data_hash=SHA256:b\n')
            b.write_text(a.read_text().replace('duration_time=0.02','duration_time=N/A',1))
            self.assertFalse(aac_initialization_timestamp_case(a,b))
            self.assertTrue(aac_initialization_timestamp_case(a,b,missing_initial_duration=True))
            with self.assertRaises(ValueError):compare_packets(a,b)
            compare_packets(a,b,aac_initialization_verified=True)
            b.write_text(b.read_text().replace('duration_time=0.02','duration_time=N/A'))
            self.assertFalse(aac_initialization_timestamp_case(a,b,missing_initial_duration=True))

    def test_only_initial_pts_can_differ_and_payloads_are_always_checked(self):
        with TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b'
            a.write_text('pts_time=0.02|dts_time=0|duration_time=0.02|data_hash=SHA256:a\n'
                         'pts_time=0.02|dts_time=0.02|duration_time=0.02|data_hash=SHA256:b\n')
            b.write_text(a.read_text().replace('pts_time=0.02|dts_time=0|','pts_time=0|dts_time=0|'))
            self.assertTrue(aac_initialization_timestamp_case(a,b))
            with self.assertRaises(ValueError):compare_packets(a,b)
            compare_packets(a,b,aac_initialization_verified=True)
            b.write_text(b.read_text().replace('SHA256:b','SHA256:c'))
            self.assertFalse(aac_initialization_timestamp_case(a,b))
            with self.assertRaises(ValueError):compare_packets(a,b,aac_initialization_verified=True)

    def test_full_pcm_proof_checks_samples_timing_and_non_output_prefix(self):
        with TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b'
            value='#tb 0: 1/48000\n0, 1024, 1024, 1024, 8192, '+'a'*64+'\n'
            a.write_text(value);b.write_text(value.replace('1024, 1024, 1024','1008, 1008, 1024'))
            result=compare_decoded_audio(a,b,'0.021333','0.021')
            self.assertTrue(result['pcm_identical'])
            self.assertTrue(result['non_output_initial_packet_verified'])
            self.assertFalse(compare_decoded_audio(a,b)['non_output_initial_packet_verified'])
            with self.assertRaisesRegex(ValueError,'non-output'):
                compare_decoded_audio(a,b,'0','0')
            b.write_text(value.replace('1024, 1024, 1024','2048, 2048, 1024'))
            with self.assertRaisesRegex(ValueError,'timing'):
                compare_decoded_audio(a,b,'0.021333','0.021')
            b.write_text(value.replace('a'*64,'b'*64))
            with self.assertRaisesRegex(ValueError,'payload'):
                compare_decoded_audio(a,b,'0.021333','0.021')
