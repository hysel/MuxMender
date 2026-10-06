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
    def test_null_clock_reset_retries_complete_strict_decode_without_timestamp_changes_to_media(self):
        error=RuntimeError('Strict decode reported an error: [null @ 0x1234] Application provided invalid, non monotonically increasing dts to muxer in stream 1: 118272 >= 0')
        with patch.object(self.w,'execute',side_effect=[error,None]) as execute:
            self.w.preflight_source_audio(self.root/'source.mkv',self.meta)
        first,second=execute.call_args_list
        command=first.args[0];index=command.index('-af')
        self.assertEqual(second.args[0],command[:index]+command[index+2:])
        self.assertTrue(second.kwargs['strict_decode'])
        self.assertNotIn('-ss',second.args[0])
        proof=json.loads((self.root/'source-audio-preflight.json').read_text())
        self.assertTrue(proof['original_clock_retry'])

    def test_retry_decoder_failure_is_not_concealed(self):
        error=RuntimeError('Strict decode reported an error: [null @ 0x1234] Application provided invalid, non monotonically increasing dts to muxer in stream 1: 118272 >= 0')
        with patch.object(self.w,'execute',side_effect=[error,RuntimeError('damaged audio frame')]):
            with self.assertRaisesRegex(RuntimeError,'damaged audio frame'):
                self.w.preflight_source_audio(self.root/'source.mkv',self.meta)
        self.assertEqual(json.loads((self.root/'source-audio-preflight.json').read_text())['state'],'failed')

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
        self.assertEqual(command[command.index('-af')+1],'asetpts=N/SR/TB')
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
    def test_duplicate_timestamps_do_not_fail_discard_only_decode(self):
        ffmpeg=shutil.which('ffmpeg');self.w.args.ffmpeg=ffmpeg
        source=self.root/'generated-duplicate-timestamps.mkv'
        subprocess.run([ffmpeg,'-v','error','-nostdin','-n','-f','lavfi','-t','0.25','-i','sine=sample_rate=48000',
                        '-af','asetpts=floor(N/2048)*2048','-c:a','pcm_s16le',str(source)],
                       check=True,capture_output=True,timeout=30)
        before=source.read_bytes()
        meta=dict(format={'duration':'0.25'},streams=[{'codec_type':'audio','index':0}])
        with self.assertRaisesRegex(RuntimeError,'non monotonically increasing dts'):
            self.w.execute([ffmpeg,'-hide_banner','-nostdin','-v','error','-xerror','-threads','2',
                            '-i',str(source),'-map','0:0','-progress','pipe:1','-nostats','-f','null','-'],
                           'unfiltered-null-check',0.25,strict_decode=True)
        self.w.preflight_source_audio(source,meta)
        # The final candidate audit must use the same discard-only clock, not
        # just source preflight. Independent packet/timeline checks stay called.
        with patch.object(self.w,'compare_frame_files',return_value=24), \
             patch.object(self.w,'check_metadata') as metadata_check, \
             patch.object(self.w,'validate_copied_tracks') as packet_check:
            self.w.validate(source,source,meta,'hevc','final-clock',self.root/'frames',
                            output_frames=self.root/'frames',output_metadata=meta)
        metadata_check.assert_called_once();packet_check.assert_called_once()
        self.assertEqual(source.read_bytes(),before)

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
        with patch.object(self.w,'compare_frame_files',return_value=24), \
             patch.object(self.w,'check_metadata'),patch.object(self.w,'validate_copied_tracks'):
            with self.assertRaisesRegex(RuntimeError,'Strict decode reported an error'):
                self.w.validate(good,broken,meta,'hevc','broken-final',self.root/'frames',
                                output_frames=self.root/'frames',output_metadata=meta)

    def test_clock_options_do_not_change_video_or_delivered_encoder(self):
        from native_pipeline import discard_audio_clock_options
        self.assertEqual(discard_audio_clock_options({'streams':[{'codec_type':'video'}]}),[])
        self.assertEqual(discard_audio_clock_options(self.meta),['-af','asetpts=N/SR/TB'])
        import inspect,auto_optimize
        self.assertNotIn('discard_audio_clock_options',inspect.getsource(auto_optimize.encode_command))


if __name__=='__main__':unittest.main()
