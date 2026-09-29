import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('dv_renderer_probe',Path(__file__).resolve().parents[1]/'tools/probe_dv_renderer.py')
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class RendererProbeTests(unittest.TestCase):
    def test_software_success_is_not_hardware_success(self):
        self.assertFalse(probe.renderer_device('[Vulkan] Using device: llvmpipe (software)')['hardware_confirmed'])
        self.assertFalse(probe.renderer_device('No device details')['hardware_confirmed'])
        self.assertTrue(probe.renderer_device('[Vulkan] Using device: NVIDIA example GPU')['hardware_confirmed'])

    def test_probe_is_one_generated_frame(self):
        cmd=probe.command('ffmpeg')
        self.assertEqual(cmd[cmd.index('-frames:v')+1],'1')
        self.assertEqual(cmd[cmd.index('-i')+1],'color=size=64x64:rate=1')
        self.assertIn('apply_dolbyvision=true',cmd[cmd.index('-vf')+1])
