import unittest
from pathlib import Path
from types import SimpleNamespace
from decoder_context import X264_UUID,x264_build_from_annexb
from auto_optimize import Workflow


def sei(build,uuid=X264_UUID):
    data=uuid+b'x264 - core '+str(build).encode()+b' r1234\x00'
    return b'\x00\x00\x01\x06\x05'+bytes([len(data)])+data+b'\x80'


class DecoderContextTests(unittest.TestCase):
    def test_original_encoder_sei_only(self):
        self.assertEqual(x264_build_from_annexb(sei(146)),146)
        self.assertIsNone(x264_build_from_annexb(b'x264 - core 146'))
        self.assertIsNone(x264_build_from_annexb(sei(146,b'wrong-uuid-value!')))
        self.assertIsNone(x264_build_from_annexb(sei(146)+sei(147)))
        self.assertIsNone(x264_build_from_annexb(sei(146)[:-5]))
        self.assertEqual(x264_build_from_annexb(sei(146)+sei(146)),146)

    def test_context_never_applies_to_outputs_or_unrelated_files(self):
        w=Workflow(SimpleNamespace(source=Path('original.mkv'),h264_build=146),Path('job'),lambda:None)
        self.assertEqual(w.decoder_options('original.mkv'),['-x264_build','146'])
        self.assertEqual(w.decoder_options('job/reference-0.mkv'),['-x264_build','146'])
        for path in ('job/full-hevc.mkv','other/reference-0.mkv','unrelated.mkv'):
            self.assertEqual(w.decoder_options(path),[])

    def test_absent_evidence_does_not_invent_a_build(self):
        w=Workflow(SimpleNamespace(source=Path('original.mkv')),Path('job'),lambda:None)
        self.assertEqual(w.decoder_options('original.mkv'),[])
