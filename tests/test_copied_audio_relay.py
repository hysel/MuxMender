import unittest
from copied_audio_relay import decode_clock_plan


class AudioRelayClockTests(unittest.TestCase):
    def test_regular_clock_has_only_internal_delay(self):
        self.assertEqual(decode_clock_plan([(0,0),(10,10),(20,20)]),(1,3))

    def test_backwards_clock_preserves_original_presentation(self):
        rows=[(0,0),(10,10),(5,5),(20,20)]
        self.assertEqual(decode_clock_plan(rows),(7,4))
        self.assertEqual(rows,[(0,0),(10,10),(5,5),(20,20)])

    def test_no_fabricated_missing_timestamps(self):
        for rows in ([],[(None,0)],[(0,None)],[(0,False)],[(0,1.2)]):
            with self.assertRaises(ValueError):decode_clock_plan(rows)

    def test_packet_activity_cannot_fake_frame_counts_or_completion(self):
        from encoder_progress import EncoderActivity,timestamp_percent
        activity=EncoderActivity()
        self.assertTrue(activity.update('MUXMENDER_ACTIVITY=4096'))
        self.assertFalse(activity.update('MUXMENDER_ACTIVITY=4096'))
        self.assertFalse(activity.update('MUXMENDER_ACTIVITY=-1'))
        self.assertEqual(activity.frames,0)
        self.assertIsNone(timestamp_percent('MUXMENDER_ACTIVITY=4096',100))


if __name__=='__main__':unittest.main()
