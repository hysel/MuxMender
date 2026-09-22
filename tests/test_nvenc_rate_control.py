from pathlib import Path
import unittest
from unittest.mock import patch

import auto_optimize as ao
from media_workflow import automatic_arguments
from test_auto_optimize import source_data


class RateControlTests(unittest.TestCase):
    def command(self, encoder='hevc_nvenc', **extra):
        settings=dict(codec='hevc',encoder=encoder,quality='balanced',**extra)
        with patch.object(ao.mm,'encoder_options',return_value=['-c:v',encoder,'-cq','21','-preset','p6']):
            return ao.encode_command('ffmpeg',Path('in'),Path('out'),settings,None,source_data()['streams'])

    def test_default_unchanged(self):
        self.assertNotIn('-maxrate:v:0',self.command())

    def test_explicit_ceiling_preserves_cq_timing_and_no_overwrite(self):
        for encoder in ('hevc_nvenc','av1_nvenc'):
            command=self.command(encoder,nvenc_maxrate_mbps=200,nvenc_cq=18)
            self.assertEqual(command[command.index('-maxrate:v:0')+1],'200000000')
            self.assertEqual(command[command.index('-cq')+1],'18')
            self.assertIn('-n',command)
            self.assertIn('-copyts',command)
            self.assertNotIn('-vf',command)

    def test_reject_invalid_settings_and_non_nvenc(self):
        for value in (0,-1,1001,True,20.5,'200'):
            with self.assertRaises(ValueError):self.command(nvenc_maxrate_mbps=value)
        with self.assertRaises(ValueError):self.command('hevc_amf',nvenc_maxrate_mbps=200)

    def test_shared_adapter_passes_same_setting(self):
        settings=dict(mode='test',hardware='nvidia',minimum_savings=10,codecs=['hevc'],
                      quality='auto',nvenc_maxrate_mbps=200)
        command=automatic_arguments('in','out',settings)
        self.assertEqual(command[command.index('--nvenc-maxrate-mbps')+1],'200')
        self.assertEqual(command[command.index('--minimum-savings-percent')+1],'10')
        settings['hardware']='amd'
        with self.assertRaises(ValueError):automatic_arguments('in','out',settings)


if __name__=='__main__':unittest.main()
