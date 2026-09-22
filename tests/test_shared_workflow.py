import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import media_naming as naming
import media_workflow as workflow
import muxmender as cli
import validated_replace as publication
from control_service import Controls


class SharedWorkflowTests(unittest.TestCase):
    def test_naming_is_same_implementation(self):
        self.assertIs(cli.create_rename_plan,naming.create_rename_plan)
        self.assertIs(publication.readable_destination,naming.readable_destination)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'Example Film';folder.mkdir()
            source=folder/'sample-ab1.1080p.mkv';source.write_bytes(b'fixture')
            self.assertEqual(cli.output_path(source,folder,Path(tmp)/'copies').name,
                             publication.readable_destination(source).name)
            plan=cli.create_rename_plan(source)
            self.assertTrue(Path(plan['entries'][0]['destination']).stem.startswith('Example Film'))

    def test_cli_and_app_launch_identical_automatic_arguments(self):
        for mode in ('analyze','test','encode'):
            settings=dict(mode=mode,hardware='nvidia',quality='auto',minimum_savings=25.0,
                          codecs=['hevc','av1'],legacy_color='inspect')
            app=Controls.build_command(SimpleNamespace(output=Path('shared-output')),dict(source='source.mkv',settings=settings),Path('output'))
            with patch('auto_optimize.main',return_value=0) as engine:
                code=cli.main(['automatic','source.mkv','--output-dir','output','--mode',mode,
                              '--hardware','nvidia','--playback-verified-codecs','hevc','av1',
                              '--capability-cache-dir',str(Path('shared-output')/'.gpu-capabilities')])
            self.assertEqual(code,0)
            self.assertEqual(engine.call_args.args[0],app[4:])

    def test_encoder_worker_never_authorizes_deletion(self):
        settings=dict(mode='replace',hardware='auto',quality='auto',minimum_savings=0,
                      codecs=['hevc'],legacy_color='inspect')
        args=workflow.automatic_arguments('source','output',settings)
        self.assertIn('--encode-best',args)
        self.assertNotIn('--delete-originals',args)

    def test_cli_requires_playback_choice(self):
        with patch('auto_optimize.main') as engine,self.assertRaises(SystemExit):
            workflow.main(['source','--output-dir','output','--mode','encode'])
        engine.assert_not_called()
