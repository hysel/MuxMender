import copy
import unittest
import auto_optimize as ao
from media_metadata import display_matrix,mp4_clock_options
from test_auto_optimize import source_data


def rotation():
    return dict(side_data_type='Display Matrix',rotation=90,
                displaymatrix='00000000: 0 -65536 0\n00000001: 65536 0 0\n00000002: 0 0 1073741824')


class RotationTests(unittest.TestCase):
    def test_other_stream_side_data_is_tested_not_blanket_rejected(self):
        before=source_data();before['streams'][0]['side_data_list']=[dict(side_data_type='Stereo 3D',type='side by side',inverted=0)]
        ao.eligibility(before)
        after=copy.deepcopy(before);after['streams'][0]['codec_name']='hevc'
        ao.metadata_check(before,after,'hevc')
        after['streams'][0]['side_data_list']=[]
        with self.assertRaisesRegex(ValueError,'side data changed'):ao.metadata_check(before,after,'hevc')

    def test_mp4_movie_clock_represents_each_source_tick_exactly(self):
        self.assertEqual(mp4_clock_options([dict(time_base='1/12288'),dict(time_base='1/48000')]),
                         ['-movie_timescale','1536000'])
        for bases in [('0/1',),('1/2147483647','1/2147483629')]:
            with self.assertRaises(ValueError):mp4_clock_options([dict(time_base=b) for b in bases])

    def test_rotation_admitted_and_full_matrix_required_in_output(self):
        before=source_data();before['streams'][0]['side_data_list']=[rotation()]
        ao.eligibility(before)
        after=copy.deepcopy(before);after['streams'][0]['codec_name']='hevc'
        ao.metadata_check(before,after,'hevc')
        after['streams'][0]['side_data_list']=[]
        with self.assertRaisesRegex(ValueError,'display matrix'):ao.metadata_check(before,after,'hevc')
        altered=rotation();altered['displaymatrix']=altered['displaymatrix'].replace('-65536','65536')
        after['streams'][0]['side_data_list']=[altered]
        with self.assertRaisesRegex(ValueError,'display matrix'):ao.metadata_check(before,after,'hevc')

    def test_incomplete_or_ambiguous_matrix_rejected(self):
        for rows in [[dict(side_data_type='Display Matrix',rotation=90)],[rotation(),rotation()]]:
            with self.assertRaises(ValueError):display_matrix(dict(side_data_list=rows))

    def test_quality_compares_native_pixel_orientation(self):
        command=ao.quality_command('ffmpeg','out','ref','graph')
        self.assertEqual(command.count('-noautorotate'),2)
