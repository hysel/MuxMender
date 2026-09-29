import unittest
from unittest.mock import patch
import dv_preservation_test as dv


class PeakRateTests(unittest.TestCase):
    def test_explicit_ceiling_does_not_change_cq_or_frame_order(self):
        with patch.object(dv,'require_candidate'), patch.object(dv.mm,'encoder_options',return_value=['-cq','18']):
            options=dv.sample_encoder_options(object(),True,False,24,40)
        self.assertEqual(options,['-cq','24','-bf','0','-maxrate:v','40000000'])

    def test_invalid_or_wrong_vendor_ceiling_rejected(self):
        for vendor,value in [(False,20),(True,True),(True,0),(True,1001),(True,1.5)]:
            with self.subTest(vendor=vendor,value=value), self.assertRaises(ValueError):
                dv.sample_encoder_options(object(),vendor,False,None,value)

    def test_default_does_not_add_a_ceiling(self):
        with patch.object(dv,'require_candidate'), patch.object(dv.mm,'encoder_options',return_value=['-cq','18']):
            self.assertNotIn('-maxrate:v',dv.sample_encoder_options(object(),True))
