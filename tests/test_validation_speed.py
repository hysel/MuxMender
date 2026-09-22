import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import auto_optimize as ao
from codec_selection import impossible_size_bound, select_candidate
from test_codec_selection import evidence
from test_auto_optimize import source_data


class ValidationSpeedTests(unittest.TestCase):
    def test_early_size_proof_never_extrapolates_first_scene(self):
        refs=evidence()['references']
        sample=dict(reference_id='0',bytes=1200,encode_completed=True)
        self.assertIsNone(impossible_size_bound(refs,[sample],10))
        sample['bytes']=2700
        self.assertIsNone(impossible_size_bound(refs,[sample],10))
        sample['bytes']=2701
        bound=impossible_size_bound(refs,[sample],10)
        self.assertLess(bound['savings_percent_upper_bound'],10)
        self.assertEqual(bound['completed_samples'],1)

    def test_early_size_invalid_evidence_never_proves_rejection(self):
        refs=evidence()['references']
        good=dict(reference_id='0',bytes=5000,encode_completed=True)
        for change in ({'bytes':True},{'bytes':0},{'bytes':float('nan')},
                       {'encode_completed':False},{'error':'failed'},{'reference_id':'unknown'}):
            with self.subTest(change=change):
                self.assertIsNone(impossible_size_bound(refs,[dict(good,**change)],10))
        self.assertIsNone(impossible_size_bound(refs,[good,good],10))

    def test_partial_rejection_has_honest_reason_and_never_approval(self):
        report=evidence();report['trials']=report['trials'][:1]
        trial=report['trials'][0];trial['samples']=trial['samples'][:1]
        trial['samples'][0].update(bytes=2800,encode_completed=True,quality_pass=False)
        trial['size_screen']=dict(early_bound=True,rejected=True)
        result=select_candidate(report)
        self.assertEqual(result['action'],'keep_original')
        self.assertEqual(result['reason_code'],'already_efficient_for_settings')
        self.assertIsNone(result['selected'])
        self.assertNotIn('savings_percent',result['candidates'][0])
        trial['samples'][0]['bytes']=500
        result=select_candidate(report)
        self.assertFalse(result['cacheable'])
        self.assertIsNone(result['selected'])

    def test_partial_size_proof_cannot_hide_wrong_source_or_failed_encoder(self):
        for change in ({'source_id':'wrong'},{'runtime_supported':False},{'playback_compatible':False}):
            report=evidence();report['trials']=report['trials'][:1];trial=report['trials'][0]
            trial.update(change);trial['samples']=trial['samples'][:1]
            trial['samples'][0].update(bytes=9000,encode_completed=True)
            trial['size_screen']=dict(early_bound=True)
            result=select_candidate(report)
            self.assertFalse(result['cacheable']);self.assertIsNone(result['selected'])

    def test_frame_reader_bounded_threads_reuses_metadata_without_dropping_side_data(self):
        with tempfile.TemporaryDirectory() as folder:
            workflow=ao.Workflow(SimpleNamespace(ffprobe='probe',timeout=60),Path(folder),lambda:None)
            def completed_probe(command,path,*args):
                path.write_text('')
                path.with_suffix(path.suffix+'.stderr').write_text('')
            with patch.object(workflow,'probe') as metadata,patch.object(ao,'run_probe',side_effect=completed_probe) as run:
                workflow.frame_file(Path('input'),'test',dict(duration=12,start_time=2))
        metadata.assert_not_called()
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('-threads')+1],'2')
        self.assertIn('-show_frames',command)
        self.assertNotIn('-read_intervals',command)
        self.assertNotIn('side_data=', ' '.join(command))
        self.assertEqual(run.call_args.args[-2:],(12.,2.))

    def test_full_video_audit_and_packet_checks_are_still_mandatory(self):
        before=source_data();after=copy.deepcopy(before);after['streams'][0]['codec_name']='hevc'
        workflow=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg'),Path('job'),lambda:None)
        with patch.object(workflow,'probe',return_value=after),patch.object(workflow,'frame_file') as frames, \
             patch.object(ao,'compare_frames',return_value=50),patch.object(workflow,'copied_packets',return_value={}) as packets, \
             patch.object(workflow,'execute') as execute,patch.object(ao,'save') as save:
            self.assertEqual(workflow.validate(Path('a'),Path('b'),before,'hevc','test',Path('frames')),50)
        self.assertEqual(packets.call_count,2)
        # Video-only input: its complete successful frame decode is not repeated.
        # Audio-bearing generated fixtures independently test the mandatory audio pass.
        execute.assert_not_called()
        self.assertTrue(save.call_args.args[1]['video_audit_reused'])
        self.assertEqual(save.call_args.args[1]['verified_video_frames'],50)
        self.assertEqual(frames.call_args.args[-1],after['format'])

    def test_separate_dangerous_side_data_line_cannot_be_ignored(self):
        row='width=720|height=480|pix_fmt=yuv420p|sample_aspect_ratio=1:1|interlaced_frame=0|repeat_pict=0|best_effort_timestamp_time=0\n'
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'frames'
            for name in ('DOVI configuration record','Mastering display metadata','Content light level metadata','Display Matrix'):
                p.write_text(row+'side_data_type='+name+'\n')
                with self.assertRaises(ValueError):ao.compare_frames(p,p)


if __name__=='__main__':unittest.main()
