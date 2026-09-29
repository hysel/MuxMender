from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

import auto_optimize as ao
from media_workflow import automatic_arguments
from test_auto_optimize import source_data


class RateControlTests(unittest.TestCase):
    def test_explicit_trial_preset_is_bounded_and_default_unchanged(self):
        default=ao.explicit_hevc_trials([19,20,21,19])
        self.assertEqual([x['nvenc_cq'] for x in default],[19,20,21])
        self.assertTrue(all('nvenc_preset' not in x for x in default))
        qualified=ao.explicit_hevc_trials([19,20,21],'p7')
        for settings in qualified:
            self.assertEqual(settings['nvenc_preset'],'p7')
            command=self.command(nvenc_cq=settings['nvenc_cq'],nvenc_preset=settings['nvenc_preset'])
            self.assertEqual(command[command.index('-preset')+1],'p7')
            self.assertIn('-n',command)
            self.assertIn('-copyts',command)
        for values,preset in [([17],'p7'),([True],'p7'),([19],'p1'),([],'p7')]:
            with self.assertRaises(ValueError):ao.explicit_hevc_trials(values,preset)

    def test_explicit_preset_cli_requires_explicit_cq(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(ao,'run',return_value=0) as run:
            (Path(folder)/'input').mkdir()
            source=Path(folder)/'input'/'fixture.mkv';source.write_bytes(b'generated')
            args=[str(source),'--output-dir',str(Path(folder)/'output'),'--hardware','nvidia',
                  '--playback-verified-codecs','hevc','--hevc-nvenc-preset','p7']
            with self.assertRaises(SystemExit):ao.main(args)
            run.assert_not_called()
            self.assertEqual(ao.main(args+['--hevc-nvenc-cq','19','21']),0)
            self.assertEqual(run.call_args.args[0].hevc_nvenc_preset,'p7')

    def command(self, encoder='hevc_nvenc', **extra):
        settings=dict(codec='hevc',encoder=encoder,quality='balanced',**extra)
        with patch.object(ao.mm,'encoder_options',return_value=['-c:v',encoder,'-cq','21','-preset','p6','-tune','hq']):
            return ao.encode_command('ffmpeg',Path('in'),Path('out'),settings,None,source_data()['streams'])

    def test_default_unchanged(self):
        self.assertNotIn('-maxrate:v:0',self.command())
        command=self.command()
        self.assertEqual(command[command.index('-tune')+1],'hq')
        self.assertNotIn('-rc-lookahead',command)
        self.assertNotIn('-multipass',command)

    def test_optional_analysis_preserves_other_arguments(self):
        for encoder in ('hevc_nvenc','av1_nvenc'):
            original=self.command(encoder)
            measured=self.command(encoder,nvenc_analysis='lookahead32-fullres')
            index=measured.index('-rc-lookahead')
            self.assertEqual(measured[index:index+4],['-rc-lookahead','32','-multipass','fullres'])
            self.assertEqual(measured[:index]+measured[index+4:],original)
        for encoder,value in [('hevc_nvenc','invalid'),('hevc_amf','lookahead32-fullres'),('h264_nvenc','lookahead32-fullres')]:
            with self.assertRaises(ValueError):self.command(encoder,nvenc_analysis=value)

    def test_analysis_cli_requires_supported_scope(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(ao,'run',return_value=0) as run:
            (Path(folder)/'input').mkdir()
            source=Path(folder)/'input'/'fixture.mkv';source.write_bytes(b'generated')
            args=[str(source),'--output-dir',str(Path(folder)/'output'),
                  '--nvenc-analysis','lookahead32-fullres']
            with self.assertRaises(SystemExit):ao.main(args+['--hardware','amd','--playback-verified-codecs','hevc'])
            run.assert_not_called()
            self.assertEqual(ao.main(args+['--hardware','nvidia','--playback-verified-codecs','hevc']),0)
            self.assertEqual(run.call_args.args[0].nvenc_analysis,'lookahead32-fullres')

    def test_optional_uhq_changes_only_tuning(self):
        for encoder in ('hevc_nvenc','av1_nvenc'):
            original=self.command(encoder)
            tuned=self.command(encoder,nvenc_tune='uhq')
            expected=list(original);expected[expected.index('-tune')+1]='uhq'
            self.assertEqual(tuned,expected)
        for encoder,tuning in [('hevc_nvenc','invalid'),('hevc_amf','uhq'),('h264_nvenc','uhq')]:
            with self.assertRaises(ValueError):self.command(encoder,nvenc_tune=tuning)

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
