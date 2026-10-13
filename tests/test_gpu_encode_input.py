import unittest
from gpu_encode_input import apply


class GPUEncodeInputTests(unittest.TestCase):
    def setUp(self):
        self.video=dict(codec_name='av1',pix_fmt='yuv420p',field_order='progressive',color_transfer='bt709')
        self.command=['ffmpeg','-xerror','-copyts','-i','source.mkv','-c:v:0','av1_nvenc',
                      '-cq','25','-fps_mode:v:0','passthrough','-filter:v:0','setparams=range=limited','out.mkv']

    def test_keeps_filters_timing_strictness_and_quality(self):
        result=apply(self.command,self.video,'av1_nvenc')
        self.assertEqual(result[result.index('-filter:v:0')+1],'hwdownload,format=nv12,format=yuv420p,setparams=range=limited')
        for option in ('-xerror','-copyts','-fps_mode:v:0'):self.assertIn(option,result)
        self.assertEqual(result[result.index('-cq')+1],'25')
        self.assertLess(result.index('-hwaccel'),result.index('-i'))
        self.assertNotIn('-hwaccel',self.command)

    def test_other_scopes_are_not_silently_certified(self):
        for key,value in [('pix_fmt','yuv420p10le'),('codec_name','hevc'),('field_order','tt'),('color_transfer','smpte2084')]:
            with self.assertRaises(ValueError):apply(self.command,dict(self.video,**{key:value}),'av1_nvenc')
        with self.assertRaises(ValueError):apply(self.command,self.video,'libsvtav1')

    def test_multiple_inputs_or_filters_rejected(self):
        for extra in (['-i','second.mkv'],['-vf','scale=1280:720'],['-hwaccel','cuda']):
            with self.assertRaises(ValueError):apply(self.command[:-1]+extra+self.command[-1:],self.video,'av1_nvenc')
