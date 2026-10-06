import copy
import unittest
from gpu_reader_receipt import qualified_scope


class ReceiptTests(unittest.TestCase):
    def evidence(self):
        read=dict(strict_success=True,returncode=0,error='',seconds=20)
        real=dict(binary_sha256='a'*64,source_changed=False,
            source=dict(codec_name='av1',pix_fmt='yuv420p10le'),
            full_reads=dict(cpu=read,cuda=dict(read,seconds=5)),
            full_pairwise_proof=dict(frames=240,static_hdr_frames=240,hdr10plus_frames=0,hdr_metadata_exact=True,frame_timestamps_exact=True,
                frame_timing_preserved=True,geometry_color_exact=True,max_timestamp_delta_seconds=0,mode='hdr10'))
        controls=dict(binary_sha256='a'*64,codec_name='av1',control_passed=True,false_passes=[],
            corruption=[dict(case=case,cuda=dict(strict_success=False)) for case in ('early','middle','late')])
        return real,controls

    def test_receipt_is_reader_only_and_does_not_infer_dynamic_hdr(self):
        result=qualified_scope(*self.evidence())
        self.assertEqual(result['time_reduction_percent'],75)
        self.assertEqual(result['hdr_modes'],['hdr10','pq'])
        self.assertNotIn('replacement_authorized',result)

    def test_incomplete_or_different_build_cannot_be_attested(self):
        for mutate in (lambda r,c:r.pop('full_reads'),lambda r,c:r.update(source_changed=True),
            lambda r,c:c.update(binary_sha256='b'*64),lambda r,c:r['full_reads']['cuda'].update(strict_success=False),
            lambda r,c:r['full_pairwise_proof'].update(frame_timestamps_exact=False),
            lambda r,c:r['full_pairwise_proof'].update(max_timestamp_delta_seconds=.001),
            lambda r,c:r['full_pairwise_proof'].update(mode='hdr10plus'),
            lambda r,c:r['full_pairwise_proof'].update(static_hdr_frames=0),
            lambda r,c:c['corruption'][1]['cuda'].update(strict_success=True),
            lambda r,c:r['full_reads']['cuda'].update(seconds=30)):
            real,controls=self.evidence();mutate(real,controls)
            with self.assertRaises(ValueError):qualified_scope(real,controls)
