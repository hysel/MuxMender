import copy
import unittest
import auto_optimize as ao
from test_auto_optimize import source_data


class DataTrackTests(unittest.TestCase):
    def test_data_tracks_are_admitted_but_must_retain_identity_and_clock(self):
        before=source_data()
        data=dict(index=10,codec_type='data',codec_tag_string='tmcd',time_base='1/12288',
                  extradata_hash='SHA256:fixture',disposition={},tags={'timecode':'01:00:00:00'})
        before['streams'].append(data)
        ao.eligibility(before)
        self.assertIn(10,ao.copied_track_indices(before))
        after=copy.deepcopy(before);after['streams'][0]['codec_name']='hevc'
        ao.metadata_check(before,after,'hevc')
        for key,value in [('codec_tag_string','other'),('time_base','1/1000'),('extradata_hash','changed')]:
            original=after['streams'][-1][key];after['streams'][-1][key]=value
            with self.assertRaises(ValueError):ao.metadata_check(before,after,'hevc')
            after['streams'][-1][key]=original
        after['streams'][-1]['tags']['timecode']='00:00:00:00'
        with self.assertRaises(ValueError):ao.metadata_check(before,after,'hevc')
