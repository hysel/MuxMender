import copy
import json
import unittest
from hdr10plus_validation import preserve_json_pairs, validate_frames


def frame():
    return dict(width=3840, height=2160, pix_fmt='yuv420p10le', color_range='tv',
                color_space='bt2020nc', color_transfer='smpte2084', color_primaries='bt2020',
                sample_aspect_ratio='1:1', best_effort_timestamp_time='0.042',interlaced_frame=0,repeat_pict=0,
                side_data_list=[{'side_data_type':'HDR Dynamic Metadata SMPTE2094-40 (HDR10+)',
                                 'bezier_curve_anchors':['102/1023','205/1023']}])


class HDR10PlusValidationTests(unittest.TestCase):
    def test_static_hdr_route_preserves_metadata(self):
        a=frame();a['side_data_list']=[{'side_data_type':'Mastering display metadata','max_luminance':'10000000/10000'}]
        result=validate_frames([a],[copy.deepcopy(a)],mode='hdr10')
        self.assertEqual(result['static_hdr_frames'],1)
        self.assertFalse(result['replacement_authorized'])

    def test_static_route_rejects_dynamic_hdr_and_missing_mastering(self):
        with self.assertRaises(ValueError):validate_frames([frame()],[frame()],mode='hdr10')
        a=frame();a['side_data_list']=[]
        with self.assertRaises(ValueError):validate_frames([a],[copy.deepcopy(a)],mode='hdr10')

    def test_chroma_location_change_is_not_ignored(self):
        a=frame();a['chroma_location']='topleft';b=copy.deepcopy(a);b['chroma_location']='left'
        with self.assertRaises(ValueError):validate_frames([a],[b])

    def test_exact_match_not_quality_or_replacement_approval(self):
        result=validate_frames(iter([frame()]),iter([frame()]))
        self.assertEqual(result['hdr10plus_frames'],1)
        self.assertFalse(result['quality_approved'])
        self.assertFalse(result['replacement_authorized'])

    def test_repeated_keys_preserved(self):
        data=json.loads('{"anchor":1,"anchor":2}',object_pairs_hook=preserve_json_pairs)
        self.assertEqual(data['anchor'],[1,2])

    def test_interlace_repeat_and_rotation_rejected(self):
        for key,value in [('interlaced_frame',1),('repeat_pict',1),('interlaced_frame',None)]:
            a=frame();a[key]=value
            with self.assertRaises(ValueError):validate_frames([a],[copy.deepcopy(a)])
        a=frame();a['side_data_list'].append({'side_data_type':'Display Matrix'})
        with self.assertRaises(ValueError):validate_frames([a],[copy.deepcopy(a)])

    def test_rejects_missing_or_changed_metadata_and_timing(self):
        for key,value in [('side_data_list',[]),('best_effort_timestamp_time','0'),
                          ('width',1920),('pix_fmt','yuv420p'),('color_primaries',None)]:
            a=frame();b=copy.deepcopy(a);b[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):validate_frames([a],[b])

    def test_rejects_changed_repeated_curve_values(self):
        a=frame();b=copy.deepcopy(a)
        b['side_data_list'][0]['bezier_curve_anchors'][0]='103/1023'
        with self.assertRaises(ValueError):validate_frames([a],[b])

    def test_missing_frames_and_no_evidence(self):
        for a,b in [([],[]),([frame()],[]),([],[frame()])]:
            with self.assertRaises(ValueError):validate_frames(a,b)

    def test_duplicate_timestamps_and_dolby_are_rejected(self):
        with self.assertRaises(ValueError):validate_frames([frame(),frame()],[frame(),frame()])
        a=frame();a['side_data_list'].append({'side_data_type':'DOVI configuration record'})
        with self.assertRaises(ValueError):validate_frames([a],[copy.deepcopy(a)])
