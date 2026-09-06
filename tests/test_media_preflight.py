import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
from mux_integrity import conversion_preflight, inspect_packets, verified_reorder_prefix


class PreflightTests(unittest.TestCase):
    def test_reorder_prefix_requires_matching_decoded_pts(self):
        data = dict(streams=[dict(codec_name='h264',has_b_frames=2)], packets=[
            dict(pts_time=0),dict(pts_time=2),dict(pts_time=1,dts_time=0),dict(pts_time=3,dts_time=1)])
        frames = [dict(pts_time=x) for x in range(4)]
        self.assertEqual(verified_reorder_prefix(data,frames),2)
        for bad in (frames[:-1],frames[::-1],[{}]*4,[dict(pts_time='nan')]*4):
            self.assertEqual(verified_reorder_prefix(data,bad),0)
        data['packets'][3].pop('dts_time')
        self.assertEqual(verified_reorder_prefix(data,frames),0)

    def test_reorder_prefix_does_not_relax_other_failures(self):
        for packets in ([dict(pts_time='nan')], [dict(pts_time=0,dts_time='nan')],
                        [dict(pts_time=0,dts_time=0),dict(pts_time=1)]):
            self.assertTrue(inspect_packets(packets,2))

    def test_seek_preroll_requires_key_picture_and_only_earlier_pts(self):
        data = dict(streams=[dict(codec_name='h264',has_b_frames=2)], packets=[
            dict(pts_time=2,flags='K_'),dict(pts_time=1),dict(pts_time=3,dts_time=1)])
        frames = [dict(pts_time=2),dict(pts_time=3)]
        self.assertEqual(verified_reorder_prefix(data,frames),0)
        self.assertEqual(verified_reorder_prefix(data,frames,True),2)
        self.assertEqual(verified_reorder_prefix(data,frames[:1],True),0)
        data['packets'][0]['flags']='__'
        self.assertEqual(verified_reorder_prefix(data,frames,True),0)

    def info(self, **values):
        return SimpleNamespace(**(dict(path='source.mkv',duration_seconds=120,
            color_primaries='bt709',color_transfer='bt709',color_space='bt709',color_range='tv') | values))

    def test_unknown_color_blocks_without_more_reads(self):
        reader=Mock()
        for field in ('color_primaries','color_transfer','color_space','color_range'):
            result=conversion_preflight(self.info(**{field:'unknown'}),'ffprobe',reader)
            self.assertEqual(result['status'],'needs-review')
        reader.assert_not_called()

    def test_b_frames_allow_reordered_pts_but_not_dts(self):
        self.assertEqual(inspect_packets([dict(pts_time=1,dts_time=0),dict(pts_time=0,dts_time=1)]),[])
        self.assertTrue(inspect_packets([dict(pts_time=1,dts_time=1),dict(pts_time=2,dts_time=1)]))

    def test_missing_nonfinite_and_empty_block(self):
        for packets in ([],[{}],[dict(pts_time='nan',dts_time=0)],[dict(pts_time=0,dts_time='inf')]):
            self.assertTrue(inspect_packets(packets))

    def test_three_read_only_windows(self):
        reader=Mock(return_value={'packets':[dict(pts_time=0,dts_time=0)]})
        result=conversion_preflight(self.info(),'ffprobe',reader)
        self.assertEqual(result['status'],'passed-sampled-checks')
        self.assertEqual(reader.call_count,3)
        for call in reader.call_args_list:
            command=call.args[0]
            self.assertEqual(command[0],'ffprobe')
            self.assertIn('-show_packets',command)
            self.assertNotIn('-y',command)

    def test_errors_do_not_become_pass(self):
        reader=Mock(side_effect=RuntimeError('Cannot inspect'))
        with self.assertRaises(RuntimeError): conversion_preflight(self.info(),'ffprobe',reader)

    def test_cli_blocks_before_output_creation_or_encoder(self):
        import muxmender as mm
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'fixture.mkv'; source.touch()
            output=Path(directory)/'must-not-be-created'
            info=mm.MediaInfo(path=str(source),size_bytes=0,duration_seconds=120,container='matroska',
                video_codec='h264',width=1920,height=1080,pixel_format='yuv420p',bit_depth=8,
                color_primaries='bt709',color_transfer='bt709',color_space='bt709',color_range='unknown',
                hdr=False,dolby_vision=False,audio_codecs=[],subtitle_codecs=[],recommendation='transcode')
            with patch.object(mm,'probe',return_value=info), patch.object(mm,'recommend',return_value=info), \
                 patch.object(mm.shutil,'which',return_value='tool'), patch.object(mm,'ffmpeg_encoder_names',return_value={'hevc_amf'}), \
                 patch.object(mm,'gpu_vendors',return_value=['amd']), patch.object(mm,'run_ffmpeg') as encode:
                result=mm.main([str(source),'--execute','--output-dir',str(output)])
            self.assertEqual(result,1)
            encode.assert_not_called()
            self.assertFalse(output.exists())
            self.assertTrue(source.exists())
