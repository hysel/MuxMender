import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('feeding',Path(__file__).parents[1]/'tools/benchmark_encode_feeding.py')
feeding=importlib.util.module_from_spec(spec);spec.loader.exec_module(feeding)


class FeedingTests(unittest.TestCase):
    def test_only_decode_options_change(self):
        commands={mode:feeding.command('ffmpeg','source.mkv','output.mkv',mode) for mode in ('cpu2','cpu4','cuda')}
        for cmd in commands.values():
            self.assertIn('-xerror',cmd)
            self.assertEqual(cmd[cmd.index('-cq')+1],'25')
            self.assertEqual(cmd[cmd.index('-preset')+1],'p5')
            self.assertEqual(cmd[cmd.index('-c:v')+1],'av1_nvenc')
            self.assertEqual(cmd[-1],'output.mkv')
        self.assertEqual(commands['cpu4'][commands['cpu4'].index('-threads')+1],'4')
        self.assertIn('cuda',commands['cuda'])
        self.assertNotIn('-hwaccel',commands['cpu2'])

    def test_pixel_check_not_lossy(self):
        cmd=feeding.command('ffmpeg','source.mkv','frames.md5','cuda',pixels=True)
        self.assertIn('rawvideo',cmd);self.assertIn('framemd5',cmd)
        self.assertNotIn('av1_nvenc',cmd)
        self.assertIn('hwdownload,format=nv12,format=yuv420p',cmd)

    def test_reject_unknown_mode(self):
        with self.assertRaises(ValueError):feeding.command('ffmpeg','s','o','unknown')
