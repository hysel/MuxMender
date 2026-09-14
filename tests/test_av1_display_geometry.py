import unittest
from copy import deepcopy
from mux_integrity import verify_av1_display_geometry


class AV1DisplayGeometryTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(width=720, height=480, sample_aspect_ratio='8:9')
        self.output = dict(width=768, height=480, sample_aspect_ratio='8:9', codec_name='av1',
                           side_data_list=[dict(side_data_type='Frame Cropping', crop_top=0,
                                                crop_bottom=0, crop_left=0, crop_right=48)])

    def test_dvd_padding_requires_decoded_720_picture(self):
        result = verify_av1_display_geometry(self.source, self.output, [(720,480)]*3)
        self.assertEqual(result['displayed'], [720,480])
        self.assertIn('crop-aware', result['playback_caveat'])

    def test_missing_or_uncropped_decoded_evidence_fails(self):
        for frames in ([], [(768,480)], [(720,480),(768,480)]):
            with self.assertRaises(ValueError):
                verify_av1_display_geometry(self.source, self.output, frames)

    def test_bad_crop_fails(self):
        for value in (47,49,-48,True,'48'):
            output=deepcopy(self.output)
            output['side_data_list'][0]['crop_right']=value
            with self.assertRaises(ValueError):
                verify_av1_display_geometry(self.source,output,[(720,480)])

    def test_missing_crop_changed_sar_rotation_or_unknown_padding_fails(self):
        for changes in ({'side_data_list':[]}, {'sample_aspect_ratio':'1:1'},
                        {'side_data_list':[dict(side_data_type='Display Matrix')]}, {'width':800}):
            with self.assertRaises(ValueError):
                verify_av1_display_geometry(self.source,dict(self.output,**changes),[(720,480)])

    def test_exact_dimensions_pass(self):
        output=dict(self.output,width=720,side_data_list=[])
        verify_av1_display_geometry(self.source,output,[(720,480)])

    def test_hd_bottom_padding(self):
        source=dict(width=1920,height=1080,sample_aspect_ratio='1:1')
        output=dict(self.output,width=1920,height=1082,sample_aspect_ratio='1:1',
                    side_data_list=[dict(side_data_type='Frame Cropping',crop_top=0,crop_bottom=2,crop_left=0,crop_right=0)])
        verify_av1_display_geometry(source,output,[(1920,1080)])
