import tempfile
import unittest
from pathlib import Path
from auto_optimize import compare_packets, check_reference_window


class SamplingTimingEdges(unittest.TestCase):
    def window(self,duration,rate='24000/1001'):
        return dict(format={'duration':str(duration)},streams=[dict(codec_type='video',
                    avg_frame_rate=rate,time_base='1/1000')])

    def test_unexplained_timing_case_a_sample_remains_rejected(self):
        result=check_reference_window(self.window(20),10)
        self.assertEqual(result['maximum_seconds'],20)
        self.assertEqual(result['boundary_allowance_seconds'],0)
        for value in (20.019,20.1,25,float('nan'),float('inf'),0,-1):
            with self.assertRaises(ValueError):check_reference_window(self.window(value),10)
        with self.assertRaises(ValueError):check_reference_window(self.window(20.3,'1/10'),10)
        with self.assertRaises(ValueError):check_reference_window(self.window(20.019,'0/0'),10)

    def compare(self,left,right,**kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a',Path(tmp)/'b'
            a.write_text(left);b.write_text(right)
            return compare_packets(a,b,**kwargs)

    def rows(self,times,duration='.010'):
        return ''.join(f'data_hash=SHA256:{i:064x}|pts_time={t}|dts_time={t}|duration_time={duration}\n'
                       for i,t in enumerate(times))

    def test_actual_timing_case_c_tail_pattern(self):
        a=self.rows(['11.569','11.580','11.592','11.602'])
        b=self.rows(['11.568','11.579','11.589','11.600'])
        with self.assertRaisesRegex(ValueError,'Copied packet timing changed'):self.compare(a,b)

    def test_no_drift_payload_loss_reorder_or_large_offsets(self):
        a=self.rows(['1','2','3'])
        for b in (self.rows(['1.006','2','3']),self.rows(['.996','2','3.004']),
                  self.rows(['1','2']),self.rows(['1','2','3'],'.013'),
                  a.replace('SHA256:','SHA256:changed')):
            with self.assertRaises(ValueError):self.compare(a,b)

    def test_short_packets_and_missing_duration_keep_strict_checks(self):
        for duration in ('.004','N/A'):
            with self.assertRaises(ValueError):
                self.compare(self.rows(['1'],duration),self.rows(['1.003'],duration))
