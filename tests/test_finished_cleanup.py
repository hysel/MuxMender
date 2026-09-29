import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from replacement_cleanup import cleanup_finished
from auto_optimize import Workflow
from types import SimpleNamespace


class FinishedCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'original.mkv';self.source.write_bytes(b'original')
        self.run=self.root/'run';self.run.mkdir()
        self.output=self.run/'full.mkv';self.output.write_bytes(b'final')
        self.layer=self.run/'admission-layers';self.layer.mkdir()
        for name in ['layered.hevc','base.hevc','metadata.rpu','metadata.json']:(self.layer/name).write_bytes(b'working')
        (self.run/'full-vmaf.json').write_text('{}')
        (self.run/'trials.json').write_text('{}')
        (self.run/'summary.json').write_text('{"p5":91}')
        self.state=dict(state='validated-copy-awaiting-playback',source=str(self.source),original_retained=True,output=str(self.output))
        self.save()

    def save(self):(self.run/'status.json').write_text(json.dumps(self.state))

    def test_success_retains_final_but_removes_layers_and_frame_metrics(self):
        os.link(self.output,self.run/'duplicate.mkv')
        result=cleanup_finished(self.run,execute=True)
        self.assertEqual(result['state'],'cleaned')
        self.assertEqual(self.output.read_bytes(),b'final')
        self.assertFalse((self.run/'duplicate.mkv').exists())
        self.assertFalse(any(self.layer.iterdir()))
        self.assertFalse((self.run/'full-vmaf.json').exists())
        self.assertTrue((self.run/'summary.json').exists())
        self.assertEqual(self.source.read_bytes(),b'original')
        self.assertEqual(cleanup_finished(self.run,execute=True)['files'],0)

    def test_rejected_failed_and_cancelled_work_removes_generated_media(self):
        for state in ['full-output-rejected-insufficient-savings','stopped-original-retained','trials-completed']:
            self.state.update(state=state,decision={'action':'keep_original'});self.save()
            self.output.write_bytes(b'generated')
            cleanup_finished(self.run,execute=True)
            self.assertFalse(self.output.exists())
            self.assertTrue(self.source.exists())

    def test_research_keeps_requested_copy_but_not_working_layers(self):
        self.state.update(state='research-completed-not-approved',research_only=True,candidate=str(self.output),publication_authorized=False)
        self.save();cleanup_finished(self.run,execute=True)
        self.assertTrue(self.output.exists())
        self.assertFalse(any(self.layer.iterdir()))
        self.assertFalse(json.loads((self.run/'status.json').read_text())['publication_authorized'])

    def test_selected_sample_and_reference_retained_other_candidate_removed(self):
        reference=self.run/'reference.mkv';reference.write_bytes(b'reference')
        self.state.update(state='trials-completed',decision={'action':'encode_copy','selected':{'id':'winner'}});self.save()
        (self.run/'trials.json').write_text(json.dumps({'references':[{'path':str(reference)}],
            'trials':[{'id':'winner','samples':[{'output':str(self.output)}]}]}))
        loser=self.run/'loser.mkv';loser.write_bytes(b'loser')
        cleanup_finished(self.run,execute=True)
        self.assertTrue(self.output.exists());self.assertTrue(reference.exists());self.assertFalse(loser.exists())

    def test_missing_output_or_recovery_blocks_success_cleanup(self):
        for name in ['replacement.json','replacement-journal.jsonl']:
            p=self.run/name;p.write_text('{}')
            with self.assertRaises(ValueError):cleanup_finished(self.run,execute=True)
            self.assertTrue((self.layer/'base.hevc').exists());p.unlink()
        self.output.unlink()
        with self.assertRaises(ValueError):cleanup_finished(self.run,execute=True)

    def test_external_or_active_output_never_deleted(self):
        self.state['output']=str(self.source);self.save()
        with self.assertRaises(ValueError):cleanup_finished(self.run,execute=True)
        self.state.update(state='running',output=str(self.output));self.save()
        with self.assertRaises(ValueError):cleanup_finished(self.run,execute=True)

    def test_cleanup_failure_is_recorded_without_masking_processing_result(self):
        work=Workflow(SimpleNamespace(),self.run,lambda:None)
        with patch('replacement_cleanup.cleanup_finished',side_effect=OSError('permission denied')):
            work.cleanup_terminal_artifacts()
        report=json.loads((self.run/'terminal-cleanup.json').read_text())
        self.assertEqual(report['state'],'needs-attention')
        self.assertEqual(json.loads((self.run/'status.json').read_text())['state'],'validated-copy-awaiting-playback')

    def test_layered_error_and_graceful_cancel_always_finalize(self):
        import dv_mel
        from amd_av1_batch import fingerprint
        for failure in [RuntimeError('fixture failure'),KeyboardInterrupt('cancelled')]:
            args=SimpleNamespace(execute=True,encode_best=False,playback_verified_codecs=['hevc'],
                                 min_free_gib=1,ffmpeg='ffmpeg')
            data={'streams':[{'codec_type':'video','side_data_list':[{'dv_profile':7}]}]}
            folder=self.root/('cancelled' if isinstance(failure,KeyboardInterrupt) else 'failed')
            def extract(work,*unused):
                layer=work.directory/'admission-layers';layer.mkdir()
                (layer/'layered.hevc').write_bytes(b'generated')
                (layer/'metadata.json').write_text('{}')
                raise failure
            with patch('dv_mel.extract_layers',side_effect=extract):
                with self.assertRaises(type(failure)):
                    dv_mel.run(args,self.source,folder,data,fingerprint(self.source))
            run=next(folder.glob('auto-*'))
            self.assertFalse((run/'admission-layers/layered.hevc').exists())
            self.assertFalse((run/'admission-layers/metadata.json').exists())
            self.assertEqual(json.loads((run/'terminal-cleanup.json').read_text())['state'],'cleaned')


if __name__=='__main__':unittest.main()
