import tempfile
import unittest
from pathlib import Path
from packet_validation import duration_header_evidence
from unittest.mock import patch
from auto_optimize import metadata_check


class DurationHeaderTests(unittest.TestCase):
    def test_header_representation_not_a_timing_tolerance(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a.txt',Path(tmp)/'b.txt'
            rows='stream_index=0|pts_time=3|duration_time=1\nstream_index=0|pts_time=4|duration_time=1\n'
            a.write_text(rows);b.write_text(rows)
            stream=dict(index=0,codec_type='video',codec_name='hevc',disposition={})
            before=dict(streams=[stream],format=dict(start_time='3',duration='2'))
            after=dict(streams=[stream],format=dict(start_time='3',duration='5'))
            proof=duration_header_evidence(before,after,a,b)
            self.assertTrue(proof['complete_packet_spans_equal'])
            with patch('auto_optimize.stream_metadata_check'):
                metadata_check(before,after,'hevc',duration_evidence=proof)
                with self.assertRaisesRegex(ValueError,'Duration changed'):
                    metadata_check(before,after,'hevc')
                with self.assertRaisesRegex(ValueError,'Duration changed'):
                    metadata_check(before,after,'hevc',duration_evidence=dict(proof,headers=['2','6']))
            def cancel():raise RuntimeError('cancelled')
            with self.assertRaisesRegex(RuntimeError,'cancelled'):
                duration_header_evidence(before,after,a,b,guard=cancel)
            # Decode order may change, presentation extent must not.
            b.write_text('\n'.join(rows.strip().splitlines()[::-1])+'\n')
            self.assertEqual(duration_header_evidence(before,after,a,b),proof)
            for changed in (rows.replace('pts_time=4','pts_time=4.001'),
                            rows.replace('duration_time=1','duration_time=0.9'),
                            rows.splitlines()[0]+'\n',rows.replace('pts_time=4','pts_time=NaN')):
                b.write_text(changed)
                with self.assertRaises(ValueError):duration_header_evidence(before,after,a,b)
            b.write_text(rows)
            for duration in ('4.9','5.01','NaN'):
                after['format']['duration']=duration
                with self.assertRaises(ValueError):duration_header_evidence(before,after,a,b)
