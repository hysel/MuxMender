import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import auto_optimize as ao


class SDRWorkerIntegrationTests(unittest.TestCase):
    def test_hdr_scoring_uses_separate_measured_budget_without_decoder_changes(self):
        video=dict(self.profile,codec_name='hevc',pix_fmt='yuv420p10le',width=3840,height=2160)
        self.workflow.hdr_mode='pq'
        self.workflow.probe=Mock(return_value={'streams':[video]})
        self.workflow.hdr_quality_budget=Mock()
        self.workflow.hdr_quality_budget.threads.return_value=4
        def execute(command,*args,**kwargs):
            (self.root/'check-vmaf.json').write_text(json.dumps({'frames':[{'metrics':{'vmaf':95}}]}))
        self.workflow.execute=Mock(side_effect=execute)
        result=self.workflow.quality(self.root/'reference.mkv',self.root/'output.mkv','check',1,10)
        command=self.workflow.execute.call_args.args[0]
        self.assertIn('libvmaf=n_threads=4:',command[command.index('-filter_complex')+1])
        self.assertEqual([command[i+1] for i,v in enumerate(command[:-1]) if v=='-threads'],['2','2'])
        self.assertTrue(result['passed'])
        self.workflow.worker_budget.threads.assert_not_called()
        self.workflow.hdr_mode='hlg'
        self.workflow.hdr_quality_budget.threads.reset_mock()
        self.workflow.quality(self.root/'reference.mkv',self.root/'output.mkv','check',1,10)
        fallback=self.workflow.execute.call_args.args[0]
        self.assertIn('libvmaf=n_threads=2:',fallback[fallback.index('-filter_complex')+1])
        self.workflow.hdr_quality_budget.threads.assert_not_called()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.args=SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=120,
                                  source=self.root/'source.mkv',h264_build=146,
                                  vmaf_mean=90,vmaf_p5=90)
        self.workflow=ao.Workflow(self.args,self.root,lambda:None)
        self.profile=dict(codec_name='h264',pix_fmt='yuv420p',field_order='progressive',
                          codec_type='video',avg_frame_rate='24/1')
        self.workflow.performance_video=self.profile
        self.workflow.worker_budget=Mock()
        self.workflow.worker_budget.threads.return_value=4

    def test_encode_uses_selected_budget_and_preserves_decoder_context(self):
        command=['ffmpeg','-i',str(self.args.source),'-c:v:0','hevc_nvenc','-cq','24',str(self.root/'output.mkv')]
        with patch.object(ao,'stage') as stage:
            self.workflow.execute(command,'encode',10)
        actual=stage.call_args.args[0]
        self.assertEqual(actual[actual.index('-threads')+1],'4')
        self.assertEqual(actual[actual.index('-x264_build')+1],'146')
        self.assertEqual(actual[actual.index('-threads:v')+1],'2')
        self.assertEqual(actual[actual.index('-cq')+1],'24')
        logged=json.loads((self.root/'001-encode.log').read_text().splitlines()[0])
        self.assertEqual(actual,logged)

    def test_full_sdr_reader_keeps_all_fields_and_compatibility(self):
        def fake_reader(command,path,*args):
            path.write_text('best_effort_timestamp_time=0|width=1920\n')
            path.with_suffix(path.suffix+'.stderr').write_text('')
        with patch.object(ao,'run_probe',side_effect=fake_reader) as run:
            self.workflow.frame_file(self.args.source,'full-source',{'duration':'10'})
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('-threads')+1],'4')
        self.assertIn('-show_frames',command)
        self.assertIn('color_primaries,color_transfer,color_space,color_range',command[command.index('-show_entries')+1])
        self.assertEqual(command[command.index('-x264_build')+1],'146')

    def test_hdr_reader_does_not_use_sdr_budget(self):
        self.workflow.hdr_mode='hdr10'
        self.workflow.worker_budget.threads.side_effect=AssertionError('SDR budget used for HDR')
        def fake_reader(command,path,*args):
            path.write_text('{}')
            path.with_suffix(path.suffix+'.stderr').write_text('')
        with patch('decoder_context.hdr_reader_options',return_value=['-threads','2','-thread_type','slice']),\
             patch.object(ao,'run_probe',side_effect=fake_reader) as run:
            self.workflow.frame_file(self.args.source,'hdr-source',{'duration':'10'})
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('-thread_type')+1],'slice')
        self.assertEqual(command[command.index('-threads')+1],'2')

    def test_quality_changes_workers_not_thresholds_or_input_decoder_options(self):
        self.workflow.probe=Mock(return_value={'streams':[self.profile]})
        def execute(command,*args,**kwargs):
            (self.root/'check-vmaf.json').write_text(json.dumps({'frames':[{'metrics':{'vmaf':95}}]}))
        self.workflow.execute=Mock(side_effect=execute)
        result=self.workflow.quality(self.root/'reference-0.mkv',self.root/'output.mkv','check',1,10)
        command=self.workflow.execute.call_args.args[0]
        self.assertIn('libvmaf=n_threads=4:',command[command.index('-filter_complex')+1])
        self.assertEqual([command[i+1] for i,v in enumerate(command[:-1]) if v=='-threads'],['2','2'])
        self.assertTrue(result['passed'])
        self.assertEqual(result['mean'],95)

    def test_unqualified_profile_keeps_two_without_resource_sampling(self):
        self.workflow.performance_video=dict(self.profile,pix_fmt='yuv420p10le')
        self.assertEqual(self.workflow.performance_threads(),2)
        self.workflow.worker_budget.threads.assert_not_called()


if __name__ == '__main__':
    unittest.main()
