import unittest
from hdr_auto import av1_chroma_options


class AV1ChromaOptionsTests(unittest.TestCase):
    def test_only_source_declared_representable_420_positions(self):
        for source,encoded in [('left','vertical'),('topleft','colocated')]:
            options=av1_chroma_options(dict(pix_fmt='yuv420p10le',chroma_location=source))
            self.assertEqual(options[-1],'av1_metadata=chroma_sample_position='+encoded)
            self.assertNotIn('-vf',options)
        for source in (None,'unknown','center','top','bottomleft'):
            self.assertEqual(av1_chroma_options(dict(pix_fmt='yuv420p10le',chroma_location=source)),[])
        self.assertEqual(av1_chroma_options(dict(pix_fmt='yuv444p10le',chroma_location='topleft')),[])
