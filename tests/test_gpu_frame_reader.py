"""Backend policy/dispatch tests; no native reader or GPU execution on Windows."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gpu_frame_reader import select_reader,load_qualification,hdr_reader_request,visibility_matches


class ReaderTests(unittest.TestCase):
    def test_only_the_attested_sole_uuid_and_all_are_equivalent_selectors(self):
        expected=dict(CUDA_VISIBLE_DEVICES=None,NVIDIA_VISIBLE_DEVICES='all',CUDA_DEVICE_ORDER=None)
        current=dict(expected,NVIDIA_VISIBLE_DEVICES='GPU-neutral')
        self.assertTrue(visibility_matches(expected,current,'GPU-neutral'))
        self.assertTrue(visibility_matches(current,expected,'GPU-neutral'))
        self.assertTrue(visibility_matches(expected,dict(current,NVIDIA_VISIBLE_DEVICES='void'),'GPU-neutral'))
        for value in ('0','none','',None,'GPU-other','GPU-neutral,GPU-other'):
            self.assertFalse(visibility_matches(expected,dict(current,NVIDIA_VISIBLE_DEVICES=value),'GPU-neutral'))
        self.assertFalse(visibility_matches(expected,dict(current,CUDA_VISIBLE_DEVICES='0'),'GPU-neutral'))
        self.assertFalse(visibility_matches(expected,dict(current,CUDA_DEVICE_ORDER='PCI_BUS_ID'),'GPU-neutral'))
        self.assertFalse(visibility_matches({},current,'GPU-neutral'))

    def qualification(self):
        return dict(binary='/opt/muxmender-readers/ffprobe-cuda',scopes=[dict(codec='av1',
            pixel_format='yuv420p10le',hdr_modes=['hdr10','pq'],full_eof=True,
            every_frame_cpu_gpu_equal=True,corrupt_controls_rejected=True,time_reduction_percent=50)])

    def video(self):return dict(codec_name='av1',pix_fmt='yuv420p10le',width=3840,height=2160)

    def test_no_filename_card_or_container_shortcut(self):
        self.assertEqual(select_reader(self.video(),600,'hdr10',None)['backend'],'cpu')
        for codec,pixel,mode,duration in [('hevc','yuv420p10le','hdr10',600),
                ('av1','yuv444p10le','hdr10',600),('av1','yuv420p10le','hdr10plus',600),
                ('av1','yuv420p10le','hdr10',10)]:
            self.assertEqual(select_reader(dict(codec_name=codec,pix_fmt=pixel),duration,mode,self.qualification())['backend'],'cpu')
        self.assertEqual(select_reader(self.video(),600,'hdr10',self.qualification())['backend'],'cuda')

    def test_every_proof_is_required_and_cost_must_improve(self):
        for key in ('full_eof','every_frame_cpu_gpu_equal','corrupt_controls_rejected','time_reduction_percent'):
            receipt=self.qualification();receipt['scopes'][0][key]=False
            self.assertEqual(select_reader(self.video(),600,'hdr10',receipt)['backend'],'cpu')

    def test_static_hdr_proof_does_not_claim_dolby_frame_reader_coverage(self):
        video=dict(self.video(),side_data_list=[dict(side_data_type='DOVI configuration record')])
        command,options,plan=hdr_reader_request('ffprobe',Path('input.mkv'),video,600,
            'hdr10',self.qualification(),container='matroska,webm')
        self.assertEqual(plan['backend'],'cpu')
        self.assertIn('-show_frames',command)
        self.assertNotIn('-read_intervals',command)

    def test_missing_native_container_is_cpu_routing_not_video_rejection(self):
        for container in ('avi','asf',None):
            command,options,plan=hdr_reader_request('ffprobe',Path('input.mkv'),self.video(),600,
                'hdr10',self.qualification(),container=container)
            self.assertEqual(command[0],'ffprobe')
            self.assertIn('-show_frames',command)
            self.assertEqual(plan['backend'],'cpu')
        command,options,plan=hdr_reader_request('ffprobe',Path('input.avi'),self.video(),600,
            'hdr10',self.qualification(),container='matroska,webm')
        self.assertEqual(plan['backend'],'cuda')  # Header evidence, not filename.

    def test_windows_never_tries_package_or_gpu(self):
        with patch('gpu_frame_reader.sys.platform','win32'),patch('gpu_frame_reader.trusted_file') as read:
            self.assertIsNone(load_qualification());read.assert_not_called()

    def test_receipt_binds_binary_driver_and_exact_visible_device(self):
        binary=b'neutral executable evidence'
        receipt=dict(schema=1,binary_sha256=hashlib.sha256(binary).hexdigest(),
                     adapter=dict(uuid='GPU-neutral',driver='test-driver'),
                     visibility={k:None for k in ('CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER')})
        adapters=[dict(uuid='GPU-neutral',driver='test-driver')]
        def read(path,limit):return binary if path.name=='ffprobe-cuda' else json.dumps(receipt).encode()
        with patch('gpu_frame_reader.sys.platform','linux'),patch('gpu_frame_reader.trusted_file',side_effect=read), \
             patch('gpu_frame_reader.os.access',return_value=True),patch.dict('gpu_frame_reader.os.environ',{},clear=True), \
             patch('encoder_capabilities.nvidia_adapters',return_value=adapters) as devices:
            self.assertIsNotNone(load_qualification())
            devices.return_value=[dict(uuid='GPU-other',driver='test-driver')]
            self.assertIsNone(load_qualification())
            devices.return_value=[dict(uuid='GPU-neutral',driver='new-driver')]
            self.assertIsNone(load_qualification())
            devices.return_value=adapters*2
            self.assertIsNone(load_qualification())
            for invalid in (None,[None],{},'unknown'):
                devices.return_value=invalid
                self.assertIsNone(load_qualification())
            devices.return_value=adapters
            receipt['visibility']['NVIDIA_VISIBLE_DEVICES']='all'
            with patch.dict('gpu_frame_reader.os.environ',{'NVIDIA_VISIBLE_DEVICES':'GPU-neutral'}):
                self.assertIsNotNone(load_qualification())
                devices.return_value=adapters*2
                self.assertIsNone(load_qualification())
            with patch.dict('gpu_frame_reader.os.environ',{'NVIDIA_VISIBLE_DEVICES':'void'}):
                for visible, accepted in [(adapters, True), ([], False),
                        (adapters*2, False), ([dict(uuid='GPU-other',driver='test-driver')], False),
                        ([dict(uuid='GPU-neutral',driver='new-driver')], False)]:
                    devices.return_value=visible
                    self.assertEqual(load_qualification() is not None, accepted)
            devices.return_value=adapters
            receipt['visibility']['NVIDIA_VISIBLE_DEVICES']=None
            receipt['binary_sha256']='0'*64
            self.assertIsNone(load_qualification())

    def test_shared_workflow_dispatches_all_frames_and_never_hides_failure(self):
        from auto_optimize import Workflow
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'neutral.mkv';source.touch()
            args=SimpleNamespace(hdr_mode='hdr10',ffprobe='ffprobe',timeout=120)
            workflow=Workflow(args,root,lambda:None)
            data=dict(streams=[dict(self.video(),codec_type='video',index=0)],format=dict(duration='600',format_name='matroska,webm'))
            with patch('gpu_frame_reader.load_qualification',return_value=self.qualification()), \
                 patch.object(workflow,'probe',return_value=data),patch.object(workflow,'decoder_options',return_value=[]), \
                 patch('auto_optimize.run_probe',side_effect=subprocess.CalledProcessError(1,['reader'])) as run:
                from gpu_admission import family
                def fail(command,*args,**kwargs):
                    self.assertIsNotNone(family(command,600))
                    raise subprocess.CalledProcessError(1,command)
                run.side_effect=fail
                with self.assertRaises(subprocess.CalledProcessError):workflow.frame_file(source,'test',data['format'])
                run.assert_called_once()
                command=run.call_args.args[0]
                self.assertIn('-show_frames',command)
                self.assertNotIn('-read_intervals',command)
                self.assertIn('-err_detect',command)
                self.assertEqual(command[0],'/opt/muxmender-readers/ffprobe-cuda')
                self.assertEqual(run.call_args.kwargs['env']['MUXMENDER_RESEARCH_CUDA_READER'],'1')
            self.assertEqual(workflow.frame_cache,{})
