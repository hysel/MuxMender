import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from quality_profiles import profile, apply_profile
from output_presets import preset
from media_workflow import automatic_arguments
from control_service import Controls
from autonomous_queue import signature
from codec_selection import EVALUATION_POLICY


class QualityProfilesTests(unittest.TestCase):
    def test_profiles_and_defensive_copy(self):
        for name, mean in [('strict',95),('balanced',94),('space-saver',90)]:
            self.assertEqual(profile(name)['mean'],mean)
            self.assertEqual(profile(name)['p5'],90)
        value=profile('balanced');value['mean']=0
        self.assertEqual(profile('balanced')['mean'],94)
        for invalid in (None,[],{},'unknown'):
            with self.assertRaises(ValueError):profile(invalid)

    def test_explicit_profile_replaces_resolution_floor_not_bitrate(self):
        policy=preset('tv1080'); original=dict(policy)
        for name, mean in [('strict',95),('balanced',94),('space-saver',90)]:
            args=SimpleNamespace(output_preset='tv1080',quality_profile=name,vmaf_mean=90,vmaf_p5=90)
            self.assertEqual(apply_profile(args,policy),dict(id=name,mean=mean,p5=90))
        self.assertEqual(policy,original)

    def test_legacy_jobs_and_stricter_numeric_overrides(self):
        for resolution,mean in [('original',90),('tv1080',95)]:
            args=SimpleNamespace(output_preset=resolution,vmaf_mean=90,vmaf_p5=90)
            self.assertEqual(apply_profile(args,preset(resolution))['mean'],mean)
        args=SimpleNamespace(output_preset='tv1080',quality_profile='space-saver',vmaf_mean=98,vmaf_p5=95)
        self.assertEqual(apply_profile(args,preset('tv1080')),dict(id='space-saver',mean=98,p5=95))

    def test_shared_adapter_keeps_legacy_and_forwards_new_choice(self):
        settings=dict(mode='test',hardware='auto',quality='auto',codecs=['hevc'],minimum_savings=25)
        self.assertNotIn('--quality-profile',automatic_arguments('source','output',settings))
        args=automatic_arguments('source','output',dict(settings,quality_profile='strict'))
        self.assertEqual(args[args.index('--quality-profile')+1],'strict')

    def test_cli_and_app_policy_parity_for_every_profile(self):
        import media_workflow
        import auto_optimize
        for name in ('strict','balanced','space-saver'):
            with self.subTest(profile=name),patch('auto_optimize.main',return_value=0) as engine:
                media_workflow.main(['source','--output-dir','output','--quality-profile',name])
                arguments=engine.call_args.args[0]
                self.assertEqual(arguments[arguments.index('--quality-profile')+1],name)
            # Parsing the low-level engine must retain the selected profile,
            # without running any media tools on this host.
            with tempfile.TemporaryDirectory() as tmp,patch('auto_optimize.run',return_value=0) as run:
                media=Path(tmp)/'media';media.mkdir()
                source=media/'fixture.mkv';source.write_bytes(b'fixture')
                auto_optimize.main([str(source),'--output-dir',str(Path(tmp)/'output'),'--quality-profile',name])
                self.assertEqual(run.call_args.args[0].quality_profile,name)

    def test_settings_history_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            media=Path(tmp)/'media';media.mkdir()
            output=Path(tmp)/'output';output.mkdir()
            source=media/'fixture.mkv';source.write_bytes(b'fixture')
            controls=Controls(media,output,lambda _:False,['hevc'],replacement_root=media)
            self.assertEqual(controls.settings({})['quality_profile'],'balanced')
            with self.assertRaises(ValueError):controls.settings(dict(quality_profile='unknown'))
            strict=controls.settings(dict(mode='encode',quality_profile='strict'))
            balanced=controls.settings(dict(mode='encode'))
            job=dict(id='old',source=str(source),signature=signature(source),settings=strict,
                     state='skipped',history_decision=True,evaluation_policy=EVALUATION_POLICY)
            controls.state['jobs']=[job]
            self.assertIsNone(controls.history_match(str(source),signature(source),balanced))
            self.assertIs(controls.history_match(str(source),signature(source),strict),job)
            del job['settings']['quality_profile']
            self.assertIsNone(controls.history_match(str(source),signature(source),balanced))
            for state in ('pending','running','kept-original'):
                job['state']=state
                self.assertIs(controls.history_match(str(source),signature(source),balanced),job)
            job['settings']=strict;strict['quality_profile']='strict'
            controls.save()
            reopened=Controls(media,output,lambda _:False,['hevc'],replacement_root=media)
            self.assertEqual(reopened.state['jobs'][0]['settings']['quality_profile'],'strict')

    def test_accessible_ui_and_preview_use_acceptance_not_encoder_tuning(self):
        from ui.controls import PANEL, SCRIPT
        self.assertIn('for="quality-gate-profile"',PANEL)
        self.assertIn('aria-describedby="quality-profile-help"',PANEL)
        self.assertIn('value="balanced" selected',PANEL)
        self.assertIn("quality_profile:controlElement('quality-gate-profile').value",SCRIPT)
        self.assertIn('Quality checks: ',SCRIPT)
