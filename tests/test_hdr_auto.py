import copy
import unittest
from pathlib import Path
from unittest.mock import patch
import auto_optimize as ao
import hdr_auto
from hdr10plus_validation import validate_frames
from test_auto_optimize import source_data
from test_codec_selection import evidence
from codec_selection import select_candidate


class AutomaticHDRTests(unittest.TestCase):
    def test_prefix_quality_reports_named_frame_progress_for_both_passes(self):
        with patch('native_pipeline.stage') as stage, \
             patch('job_tracking.progress') as progress, \
             patch('auto_optimize.quality_summary',return_value={'passed':True}), \
             patch('pathlib.Path.read_text',return_value='{}'):
            hdr_auto.measure_prefix_quality('ffmpeg',Path('source.mkv'),Path('copy.mkv'),
                                            Path('.'),279,'24000/1001',lambda:None)
        self.assertEqual(stage.call_count,2)
        for call in stage.call_args_list:
            command=call.args[0]
            self.assertIn('-xerror',command)
            self.assertNotIn('-filter_complex_threads',command)
            self.assertEqual(command.count('-threads'),2)
            for i,value in enumerate(command):
                if value=='-i':self.assertEqual(command[i-2:i],['-threads','2'])
        self.assertEqual([c.kwargs['expected_frames'] for c in stage.call_args_list],[279,279])
        self.assertEqual([c.args[0] for c in progress.call_args_list],
                         ['HDR quality self-check','Checking HDR candidate quality'])

    def video(self):
        video=source_data()['streams'][0]
        video.update(width=3840,height=2076,pix_fmt='yuv420p10le',color_transfer='smpte2084',
                     color_primaries='bt2020',color_space='bt2020nc')
        return video

    def test_source_geometry_and_formats_not_fixed(self):
        for pixel in ao.PLANAR_FORMATS:
            video=self.video();video['pix_fmt']=pixel
            self.assertEqual(hdr_auto.admit(video,{'kind':'HDR10+'}),'pq')
            video['color_transfer']='arib-std-b67'
            self.assertEqual(hdr_auto.admit(video,{'kind':'HLG'}),'hlg')

    def test_dolby_not_silently_treated_as_pq(self):
        with self.assertRaisesRegex(ValueError,'Dolby Vision'):
            hdr_auto.admit(self.video(),{'kind':'Dolby Vision'})

    def test_identical_fixed_render_and_no_scaling(self):
        graph=hdr_auto.quality_graph('quality.json','24000/1001')
        self.assertEqual(graph.count('tonemap=tonemap=hable:desat=0:peak=100'),2)
        self.assertEqual(graph.count('format=yuv420p10le'),2)
        self.assertNotIn('scale=w',graph)
        with self.assertRaises(ValueError):hdr_auto.quality_graph('../out.json','24')

    def test_hdr_selection_requires_both_evidence_domains(self):
        report=evidence();report['color_mode']='pq'
        self.assertEqual(select_candidate(report)['action'],'keep_original')
        for trial in report['trials']:
            for sample in trial['samples']:
                sample.update(hdr_preservation_pass=True,quality={'domain':'hdr-common-render-v1'})
        self.assertEqual(select_candidate(report)['action'],'encode_copy')
        report['trials'][1]['samples'][0]['hdr_preservation_pass']=False
        self.assertEqual(select_candidate(report)['selected']['codec'],'hevc')

    def test_encoder_uses_demux_timebase_not_frame_rate_quantization(self):
        with patch.object(ao.mm,'encoder_options',return_value=['-c:v','hevc_nvenc']):
            command=ao.encode_command('ffmpeg',Path('in.mp4'),Path('out.mkv'),
                {'codec':'hevc','encoder':'hevc_nvenc','quality':'balanced'},None,source_data()['streams'])
        self.assertEqual(command[command.index('-enc_time_base:v:0')+1],'demux')
        self.assertIn('-copyts',command)

    def test_hdr_timing_rounding_not_real_offset(self):
        frame=self.video();frame.update(best_effort_timestamp_time='0.094',interlaced_frame=0,repeat_pict=0)
        output=copy.deepcopy(frame);output['best_effort_timestamp_time']='0.092'
        self.assertTrue(validate_frames([frame],[output],mode='pq')['frame_timing_preserved'])
        output['best_effort_timestamp_time']='0.083'
        with self.assertRaises(ValueError):validate_frames([frame],[output],mode='pq')

    def test_hdr_metadata_loss_never_approved(self):
        frame=self.video();frame.update(best_effort_timestamp_time='0',interlaced_frame=0,repeat_pict=0,
            side_data_list=[{'side_data_type':'HDR Dynamic Metadata SMPTE2094-40 (HDR10+)','value':42}])
        output=copy.deepcopy(frame);output['side_data_list']=[]
        with self.assertRaisesRegex(ValueError,'HDR metadata changed'):validate_frames([frame],[output],mode='pq')
