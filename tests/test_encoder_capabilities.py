import subprocess
import unittest
from unittest.mock import patch
import encoder_capabilities as ec

class EncoderCapabilitiesTests(unittest.TestCase):
    @patch('encoder_capabilities.subprocess.run')
    def test_success_uses_only_generated_frames(self, run):
        run.return_value=subprocess.CompletedProcess([],0,'','')
        result=ec.probe_encoder('ffmpeg','av1_amf')
        self.assertEqual(result['status'],'working')
        self.assertIn('lavfi',result['command'])
        self.assertEqual(run.call_args.kwargs['timeout'],30)
    @patch('encoder_capabilities.subprocess.run')
    def test_failure_and_timeout_and_missing_tool(self, run):
        run.return_value=subprocess.CompletedProcess([],1,'','No device')
        self.assertEqual(ec.probe_encoder('ffmpeg','hevc_nvenc')['status'],'failed')
        run.side_effect=subprocess.TimeoutExpired('ffmpeg',30)
        self.assertEqual(ec.probe_encoder('ffmpeg','hevc_qsv')['status'],'timed-out')
        run.side_effect=FileNotFoundError('ffmpeg')
        self.assertEqual(ec.probe_encoder('ffmpeg','hevc_qsv')['status'],'unavailable')
    @patch('encoder_capabilities.probe_encoder')
    @patch('muxmender.gpu_vendors',return_value=['amd'])
    @patch('muxmender.ffmpeg_encoder_names',return_value={'av1_amf'})
    def test_listing_is_not_runtime_success(self,names,vendors,probe):
        rows=ec.inventory(execute=False)
        probe.assert_not_called()
        self.assertTrue(all(r['status']=='not-tested' for r in rows))
    @patch('encoder_capabilities.probe_encoder',return_value={'status':'working'})
    @patch('muxmender.gpu_vendors',return_value=['amd'])
    @patch('muxmender.ffmpeg_encoder_names',return_value={'av1_amf','hevc_nvenc'})
    def test_only_detected_listed_hardware_tested(self,names,vendors,probe):
        ec.inventory(execute=True)
        probe.assert_called_once_with('ffmpeg','av1_amf')
