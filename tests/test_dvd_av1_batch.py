import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import dvd_av1_batch as dvd

def fixture():
    return dict(streams=[dict(codec_type='video',codec_name='mpeg2video',width=720,height=480,
        pix_fmt='yuv420p',sample_aspect_ratio='8:9',field_order='tt',avg_frame_rate='30000/1001')],
        format={'duration':'100'})

class DvdTests(unittest.TestCase):
    def test_profile_gate(self):
        self.assertIsNone(dvd.eligibility(fixture()))
        for key,value in [('codec_name','hevc'),('codec_name','av1'),('width',1920),('field_order','progressive'),('sample_aspect_ratio','1:1')]:
            data=fixture();data['streams'][0][key]=value
            self.assertIsNotNone(dvd.eligibility(data))
        data=fixture();data['streams'][0]['side_data_list']=[{'side_data_type':'DOVI configuration record'}]
        self.assertIsNotNone(dvd.eligibility(data))
    def test_command_preserves_tracks_and_no_resize(self):
        cmd=dvd.command('ffmpeg',Path('source.mkv'),Path('output.mkv'))
        self.assertIn('-n',cmd)
        self.assertEqual(cmd[cmd.index('-map')+1],'0')
        self.assertNotIn('scale=',str(cmd))
        self.assertIn('bwdif=mode=send_field:parity=auto:deint=all,format=nv12',cmd)
    @patch('dvd_av1_batch.probe',return_value=fixture())
    @patch('dvd_av1_batch.probe_encoder')
    def test_dry_run_does_not_write_or_start_encoder(self,encoder,probe):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'in';source.mkdir();(source/'a.mkv').write_bytes(b'original')
            output=root/'out'
            args=SimpleNamespace(source=source,output_dir=output,execute=False,ffprobe='ffprobe')
            self.assertEqual(dvd.run(args),0)
            self.assertFalse(output.exists());encoder.assert_not_called()
            self.assertEqual((source/'a.mkv').read_bytes(),b'original')
    @patch('dvd_av1_batch.probe',return_value=fixture())
    def test_execute_requires_explicit_deinterlace(self,probe):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'a.mkv';source.write_bytes(b'x')
            output=Path(temp).parent/(Path(temp).name+'-output')
            args=SimpleNamespace(source=source,output_dir=output,execute=True,accept_deinterlace=False,ffprobe='ffprobe')
            with self.assertRaisesRegex(ValueError,'accept-deinterlace'):dvd.run(args)
            self.assertFalse(output.exists())
    def test_cli_has_no_delete_or_overwrite_option(self):
        with self.assertRaises(SystemExit):dvd.main(['a','--output-dir','b','--delete-originals'])
