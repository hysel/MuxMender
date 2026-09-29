import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dv_renderer import selected_device,discover


class RendererDiscoveryTests(unittest.TestCase):
    def test_selected_device_not_merely_gpu_listing(self):
        self.assertIsNone(selected_device(['0: NVIDIA GPU (discrete)']))
        self.assertFalse(selected_device(['Device 0 selected: llvmpipe (CPU)'])['hardware'])
        for name in ('AMD GPU (discrete)','Intel GPU (integrated)','NVIDIA GPU (discrete)'):
            self.assertTrue(selected_device(['Device 1 selected: '+name])['hardware'])

    def test_skip_software_and_try_visible_hardware_without_mutating_environment(self):
        with tempfile.TemporaryDirectory() as tmp,patch('dv_renderer.ctypes.util.find_library',return_value=None):
            before=dict(os.environ)
            def probe(command,*args,**kw):
                if 'vulkan=gpu:0' in command:
                    kw['observe']('Device 0 selected: llvmpipe (CPU)\n')
                    kw['observe']('1: Intel GPU (integrated)\n')
                else:kw['observe']('Device 1 selected: Intel GPU (integrated)\n')
            with patch('dv_renderer.stage',side_effect=probe):result=discover('ffmpeg',tmp,lambda:None)
            self.assertEqual(result['device']['index'],1)
            self.assertEqual(dict(os.environ),before)

    def test_explicit_loader_override_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'VK_DRIVER_FILES':'selected.json'}):
            with patch('dv_renderer.ctypes.util.find_library') as library,patch('dv_renderer.stage') as probe:
                probe.side_effect=lambda *a,**kw:kw['observe']('Device 0 selected: software (CPU)\n')
                with self.assertRaisesRegex(RuntimeError,'No working hardware'):discover('ffmpeg',tmp,lambda:None)
            library.assert_not_called()
            self.assertFalse(json.loads((Path(tmp)/'renderer.json').read_text())['hardware_confirmed'])
