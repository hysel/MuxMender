import copy
import unittest
from gpu_reader_receipt import qualified_scope,sdr_comparison_pair


class ReceiptTests(unittest.TestCase):
    def test_sdr_comparison_normalization_cannot_promote_generated_results(self):
        real,controls=self.sdr_evidence()
        report=dict(scope='Read-only complete approved SDR source and generated controls',
            controls_passed=True,source_unchanged=True,binary_sha256=real['binary_sha256'],
            source=real['source'],codec='av1',pixel_format='yuv420p',
            exact_pairwise_proof=dict(frames=240,every_field_exact=True,frame_timestamps_exact=True),
            measurements=[dict(backend=backend,strict_success=True,error=None,stderr_bytes=0,seconds=seconds)
                          for backend,seconds in [('cpu',20),('cuda',5)]],
            raw_healthy=controls['healthy'],corruption=controls['corruption'],false_passes=[])
        pair=sdr_comparison_pair(report,'matroska,webm')
        self.assertEqual(qualified_scope(**pair)['time_reduction_percent'],75)
        for field,value in [('scope','Generated SDR controls only'),('controls_passed',False),
                            ('source_unchanged',False),('measurements',[]),('source_container','mov,mp4'),
                            ('exact_pairwise_proof',{}),('error','incomplete')]:
            altered=copy.deepcopy(report);altered[field]=value
            with self.assertRaises(ValueError):sdr_comparison_pair(altered,'matroska,webm')

    def sdr_evidence(self):
        real,controls=self.evidence()
        real['source'].update(pix_fmt='yuv420p',container='matroska,webm')
        real['full_pairwise_proof'].update(mode='sdr',every_field_exact=True)
        real['full_pairwise_proof'].pop('hdr_metadata_exact')
        controls.update(pixel_format='yuv420p',healthy={key:dict(strict_success=True,frames=50) for key in ('cpu','cuda')},
            corruption=[dict(case=name,cuda=dict(strict_success=False)) for name in
                ('early-header','early-entropy','middle-header','middle-entropy','late-header','late-entropy','truncated')])
        return real,controls

    def test_sdr_scope_needs_exact_full_source_and_distributed_controls(self):
        real,controls=self.sdr_evidence()
        result=qualified_scope(real,controls)
        self.assertEqual(result['hdr_modes'],['sdr'])
        self.assertEqual(result['containers'],['matroska','webm'])
        self.assertEqual(result['pixel_format'],'yuv420p')
        for mutate in (lambda r,c:r['full_pairwise_proof'].pop('every_field_exact'),
                       lambda r,c:r['source'].pop('container'),
                       lambda r,c:r['source'].update(container='hevc'),
                       lambda r,c:c.update(pixel_format='yuv420p10le'),
                       lambda r,c:c['healthy']['cuda'].update(frames=0),
                       lambda r,c:c['healthy']['cuda'].update(frames=49),
                       lambda r,c:c['corruption'].pop(),
                       lambda r,c:r.pop('full_reads')):
            real,controls=self.sdr_evidence();mutate(real,controls)
            with self.assertRaises(ValueError):qualified_scope(real,controls)

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
