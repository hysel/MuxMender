import unittest
import sys
from encoder_progress import EncoderActivity, timestamp_percent


class EncoderProgressTests(unittest.TestCase):
    def test_cli_encoder_survives_missing_timestamps(self):
        from muxmender import run_ffmpeg
        code='import time\nfor i in range(1,9):\n print("frame="+str(i),flush=True)\n print("out_time_us=N/A",flush=True)\n time.sleep(.1)'
        code,stalled=run_ffmpeg([sys.executable,'-u','-c',code,'ignored-output'],10,stall_timeout=.5)
        self.assertEqual(code,0)
        self.assertFalse(stalled)

    def test_missing_timestamps_use_only_advancing_frames(self):
        a=EncoderActivity()
        self.assertFalse(a.update('out_time_us=N/A'))
        self.assertTrue(a.update('frame=10'))
        for line in ('frame=10','frame=9','frame=-1','progress=continue','frame=N/A'):
            self.assertFalse(a.update(line))
        self.assertTrue(a.update('frame=11'))

    def test_activity_continues_after_percentage_saturates(self):
        a=EncoderActivity()
        self.assertEqual(timestamp_percent('out_time_us=2000000',1),100)
        self.assertTrue(a.update('out_time_us=2000000'))
        self.assertTrue(a.update('out_time_us=3000000'))
        self.assertFalse(a.update('out_time_ms=3000000'))

    def test_invalid_values_are_not_progress(self):
        for value in ('N/A','nan','inf','-1',str(2**63-1)):
            self.assertFalse(EncoderActivity().update('out_time_us='+value))
            self.assertIsNone(timestamp_percent('out_time_us='+value,10))
        for duration in (0,-1,float('nan'),float('inf')):
            self.assertIsNone(timestamp_percent('out_time_us=123',duration))
