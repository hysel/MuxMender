import unittest
from dv_preservation_test import decode_sink_options
from native_pipeline import strict_decode_line


class DecodeSinkClockTests(unittest.TestCase):
    def test_precise_sink_does_not_ignore_decoder_errors(self):
        self.assertEqual(decode_sink_options(),
                         ['-fps_mode:v','passthrough','-enc_time_base:v','1:1000000'])
        for diagnostic in ('corrupt decoded frame', 'non monotonically increasing dts'):
            with self.assertRaises(RuntimeError):strict_decode_line(diagnostic)
