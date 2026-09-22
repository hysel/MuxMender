import copy
import unittest

import auto_optimize as ao
from media_metadata import equivalent_stream_language, compatible_measured_rate
from tests.test_auto_optimize import source_data


class ResearchMetadataTests(unittest.TestCase):
    def test_rate_rounding_requires_independent_full_frame_evidence(self):
        a, b = '89071/3715', '27021/1127'
        for count in (None, 0, 1, True):
            self.assertFalse(compatible_measured_rate(a, b, count))
        self.assertTrue(compatible_measured_rate(a, b, 112000))
        self.assertFalse(compatible_measured_rate('24/1', '25/1', 112000))
        self.assertFalse(compatible_measured_rate('24000/1001', '24/1', 112000))
        self.assertFalse(compatible_measured_rate(a, b, 10**9))
        self.assertFalse(compatible_measured_rate('0/0', b, 112000))
        before=source_data();after=copy.deepcopy(before)
        before['streams'][0]['avg_frame_rate']=a
        after['streams'][0].update(codec_name='hevc',avg_frame_rate=b)
        with self.assertRaisesRegex(ValueError, 'avg_frame_rate'):
            ao.metadata_check(before, after, 'hevc')
        ao.metadata_check(before, after, 'hevc', verified_frame_count=112000)
        after['streams'][0]['sample_aspect_ratio']='2:1'
        with self.assertRaisesRegex(ValueError, 'sample_aspect_ratio'):
            ao.metadata_check(before, after, 'hevc', verified_frame_count=112000)

    def test_undefined_stream_language_container_representation(self):
        for left, right in [(None, 'und'), ('und', None), ('eng', 'eng')]:
            self.assertTrue(equivalent_stream_language(left, right))
        for left, right in [('eng', None), ('und', 'eng'), ('eng', 'fra'),
                            ('zxx', None), ('', None), ('UND', None)]:
            self.assertFalse(equivalent_stream_language(left, right))

    def test_metadata_accepts_und_but_rejects_lost_known_language(self):
        before = source_data()
        before['streams'][0]['tags'] = {'language': 'und', 'title': 'Movie'}
        after = copy.deepcopy(before)
        after['streams'][0]['codec_name'] = 'hevc'
        del after['streams'][0]['tags']['language']
        ao.metadata_check(before, after, 'hevc')
        before['streams'][0]['tags']['language'] = 'eng'
        with self.assertRaisesRegex(ValueError, 'language'):
            ao.metadata_check(before, after, 'hevc')
        before['streams'][0]['tags']['language'] = 'und'
        del after['streams'][0]['tags']['title']
        with self.assertRaisesRegex(ValueError, 'title'):
            ao.metadata_check(before, after, 'hevc')
