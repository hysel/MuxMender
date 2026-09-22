import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from auto_optimize import Workflow


class SourceAudioPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.w=Workflow(SimpleNamespace(ffmpeg='ffmpeg',timeout=60),self.root,lambda:None)
        self.meta=dict(format={'duration':'1'},streams=[{'codec_type':'audio','index':1},{'codec_type':'audio','index':3}])

    def test_checks_every_audio_track_without_seeking_or_concealment(self):
        with patch.object(self.w,'execute') as execute:
            self.w.preflight_source_audio(self.root/'source.avi',self.meta)
        command=execute.call_args.args[0]
        self.assertIn('0:1',command);self.assertIn('0:3',command)
        self.assertIn('-xerror',command);self.assertNotIn('-ss',command)
        self.assertNotIn('-err_detect',command)
        self.assertTrue(execute.call_args.kwargs['strict_decode'])
        self.assertEqual(json.loads((self.root/'source-audio-preflight.json').read_text())['state'],'passed')

    def test_corruption_stops_with_actionable_evidence(self):
        with patch.object(self.w,'execute',side_effect=RuntimeError('Strict decode reported an error: incomplete frame')):
            with self.assertRaisesRegex(RuntimeError,'Source audio preflight failed before conversion'):
                self.w.preflight_source_audio(self.root/'source.avi',self.meta)
        evidence=json.loads((self.root/'source-audio-preflight.json').read_text())
        self.assertEqual(evidence['state'],'failed');self.assertTrue(evidence['original_retained'])

    def test_silent_video_does_not_start_decoder(self):
        with patch.object(self.w,'execute') as execute:
            self.w.preflight_source_audio(self.root/'source.mkv',{'streams':[]})
        execute.assert_not_called()

    def test_preflight_precedes_codec_trials_in_shared_engine(self):
        import inspect,auto_optimize
        code=inspect.getsource(auto_optimize.run)
        self.assertLess(code.index('workflow.preflight_source('),code.index('probe_encoder('))
        self.assertLess(code.index('workflow.preflight_source('),code.index('workflow_stage(\'compare\')'))

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg integration dependency unavailable')
    def test_generated_truncated_ac3_is_rejected(self):
        ffmpeg=shutil.which('ffmpeg');self.w.args.ffmpeg=ffmpeg
        good=self.root/'generated.ac3'
        subprocess.run([ffmpeg,'-v','error','-nostdin','-n','-f','lavfi','-i','sine=sample_rate=48000',
                        '-t','0.25','-c:a','ac3','-f','ac3',str(good)],check=True,capture_output=True,timeout=30)
        meta=dict(format={'duration':'0.25'},streams=[{'codec_type':'audio','index':0}])
        self.w.preflight_source_audio(good,meta)
        broken=self.root/'generated-truncated.ac3';broken.write_bytes(good.read_bytes()[:-64])
        with self.assertRaisesRegex(RuntimeError,'Source audio preflight failed'):
            self.w.preflight_source_audio(broken,meta)


if __name__=='__main__':unittest.main()
