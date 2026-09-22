import unittest
from hdr10_trial import chroma_options
from media_metadata import canonical_chapters


class ChromaTests(unittest.TestCase):
    def test_remux_chapter_uid_change_is_not_content_change(self):
        a=dict(id=1,time_base='1/1000',start=0,end=10000,tags={'title':'Chapter 06'})
        b=dict(id=2,time_base='1/1000000000',start=0,end=10000000000,tags={'TITLE':'Chapter 06'})
        self.assertEqual(canonical_chapters([a]),canonical_chapters([b]))
    def test_metadata_from_source_not_fixed_target(self):
        for location,value in [('left',0),('center',1),('topleft',2),('top',3),('bottomleft',4),('bottom',5)]:
            options=chroma_options({'chroma_location':location})
            self.assertEqual(options[-1],'hevc_metadata=chroma_sample_loc_type='+str(value))
            self.assertNotIn('-vf',options)
        self.assertEqual(chroma_options({}),[])
        with self.assertRaises(ValueError):chroma_options({'chroma_location':'bad'})
