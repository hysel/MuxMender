import copy
import json
import os
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from auto_optimize import Workflow
from codec_selection import select_candidate
from source_evidence_cache import SourceEvidenceCache
from validation_resources import ticket_rank,validation_slot
from test_codec_selection import evidence
from parallel_frame_audit import collect_pair
from job_tracking import isolated_progress,progress,measured_operation


class EarlyRejectionTests(unittest.TestCase):
    def test_partial_failed_scene_rejects_without_approving_unencoded_scenes(self):
        report=evidence();report['trials']=report['trials'][:1]
        trial=report['trials'][0];trial['quality_early_screen']=True
        trial['samples']=trial['samples'][:1]
        trial['samples'][0].update(quality_pass=False,quality={'passed':False,'p5':85})
        decision=select_candidate(report)
        self.assertEqual(decision['action'],'keep_original')
        self.assertEqual(decision['candidates'][0]['assessment'],'quality_rejected')
        self.assertEqual(decision['candidates'][0]['unevaluated_reference_ids'],['1','2'])

    def test_partial_pass_never_approves_conversion(self):
        report=evidence();report['trials']=report['trials'][:1]
        trial=report['trials'][0];trial['quality_early_screen']=True
        trial['samples']=trial['samples'][:1]
        trial['samples'][0]['quality']={'passed':True,'p5':99}
        result=select_candidate(report)
        self.assertEqual(result['action'],'keep_original');self.assertFalse(result['cacheable'])

    def test_incomplete_preservation_is_not_a_quality_rejection(self):
        report=evidence();report['trials']=report['trials'][:1]
        trial=report['trials'][0];trial['quality_early_screen']=True
        trial['samples']=trial['samples'][:1]
        trial['samples'][0].update(quality_pass=False,preservation_pass=False,quality={'passed':False})
        self.assertFalse(select_candidate(report)['cacheable'])


class AudioAuditTests(unittest.TestCase):
    def test_current_audio_proof_cannot_survive_changed_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'reference.mkv';output=root/'output.mkv'
            source.write_bytes(b'source');output.write_bytes(b'output')
            workflow=Workflow(SimpleNamespace(),root,lambda:None)
            workflow.remember_audio_audit(source,output,2)
            self.assertEqual(workflow.audited_audio_indices(source,output),{2})
            output.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed'):
                workflow.audited_audio_indices(source,output)

    def test_unaudited_track_has_no_reusable_decode(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);workflow=Workflow(SimpleNamespace(),root,lambda:None)
            self.assertEqual(workflow.audited_audio_indices(root/'reference',root/'output'),set())

    def test_only_already_strictly_decoded_audio_is_removed_from_final_maps(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'reference.mkv';output=root/'output.mkv'
            source.write_bytes(b'source');output.write_bytes(b'output')
            w=Workflow(SimpleNamespace(ffmpeg='ffmpeg'),root,lambda:None)
            data=dict(format={'duration':'1'},streams=[dict(index=0,codec_type='video'),
                dict(index=2,codec_type='audio'),dict(index=3,codec_type='audio')])
            with patch.object(w,'probe',return_value=data),patch.object(w,'frame_file',return_value=root/'frames'), \
                 patch.object(w,'compare_frame_files',return_value=24),patch.object(w,'check_metadata'), \
                 patch.object(w,'validate_copied_tracks',side_effect=lambda *a:w.remember_audio_audit(source,output,2)), \
                 patch.object(w,'execute') as decode:
                w.validate(source,output,data,'hevc','test',root/'source-frames')
            command=decode.call_args.args[0]
            self.assertIn('0:3',command);self.assertNotIn('0:2',command)
            self.assertTrue(decode.call_args.kwargs['strict_decode'])
            report=json.loads((root/'test-decode-evidence.json').read_text())
            self.assertEqual(report['complete_pcm_audits_reused'],[2])


class PairedAuditTests(unittest.TestCase):
    def test_parallel_children_do_not_overwrite_parent_progress(self):
        updates=[]
        with patch('job_tracking._active') as job:
            with isolated_progress(updates.append):
                with measured_operation('frame_validation'):
                    progress('child',stage_percent=50)
            job.save.assert_not_called()
            progress('parent')
            job.save.assert_called_once()
        self.assertEqual(updates[0]['phase'],'child')

    def test_pair_collects_both_complete_evidence_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'reference';output=root/'output'
            source.write_bytes(b'source');output.write_bytes(b'output')
            w=Workflow(SimpleNamespace(),root,lambda:None)
            data=dict(format={'duration':'1'});barrier=threading.Barrier(2)
            def frames(worker,path,label,metadata):
                barrier.wait(timeout=3)
                progress('reader',stage_percent=50)
                evidence=root/(label+'-frames.jsonl');evidence.write_text('complete')
                return evidence
            with patch.object(w,'probe',return_value=data),patch.object(Workflow,'frame_file',frames):
                left,right,actual=collect_pair(w,source,output,data)
            self.assertEqual(left.read_text(),'complete');self.assertEqual(right.read_text(),'complete')
            self.assertEqual(actual,data)

    def test_first_failure_stops_other_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'reference';output=root/'output'
            source.write_bytes(b'source');output.write_bytes(b'output')
            w=Workflow(SimpleNamespace(),root,lambda:None)
            data=dict(format={'duration':'1'})
            def frames(worker,path,label,metadata):
                if path==source:raise ValueError('Reader failed')
                while True:
                    worker.guard();time.sleep(.01)
            with patch.object(w,'probe',return_value=data),patch.object(Workflow,'frame_file',frames):
                with self.assertRaisesRegex(ValueError,'Reader failed'):collect_pair(w,source,output,data)


@unittest.skipUnless(os.name=='posix','Private evidence ownership requires POSIX')
class SourceCacheTests(unittest.TestCase):
    def test_only_matching_authenticated_passing_proofs_are_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=SourceEvidenceCache(Path(folder)/'cache')
            context=dict(source_sha256='a'*64,tracks=[1],policy='test-policy',decoder='v1')
            proof=dict(state='passed',tracks=[1],complete_decode=True,strict_decode=True)
            cache.store(context,proof)
            self.assertEqual(cache.load(context),proof)
            for field,value in [('source_sha256','b'*64),('policy','new'),('decoder','v2'),('tracks',[2])]:
                self.assertIsNone(cache.load(dict(context,**{field:value})))
            path=cache._path(context);data=json.loads(path.read_text())
            data['payload']['proof']['tracks']=[2];path.write_text(json.dumps(data))
            self.assertIsNone(cache.load(context))
            with self.assertRaisesRegex(ValueError,'passing'):
                cache.store(context,dict(proof,state='failed'))

    def test_untrusted_permissions_disable_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'cache';root.mkdir(mode=0o777);root.chmod(0o777)
            with self.assertRaisesRegex(ValueError,'private'):
                SourceEvidenceCache(root)


class AdmissionOrderTests(unittest.TestCase):
    def test_short_trial_priority_expires_before_starvation(self):
        with tempfile.TemporaryDirectory() as folder:
            long=Path(folder)/'wait-00000000000000000001-long.lock'
            short=Path(folder)/'wait-00000000000000000002-short.lock'
            long.write_text(json.dumps(dict(started=100,seconds=3600)))
            short.write_text(json.dumps(dict(started=105,seconds=5)))
            self.assertLess(ticket_rank(short,110),ticket_rank(long,110))
            self.assertLess(ticket_rank(long,131),ticket_rank(short,131))
            long.write_text('')
            self.assertLess(ticket_rank(long,110),ticket_rank(short,110))

    @unittest.skipUnless(os.name=='posix','OS leases require Linux')
    def test_live_short_trial_can_pass_new_long_ticket_but_not_aged_ticket(self):
        import fcntl
        for age,allowed in ((0,True),(31,False)):
            with tempfile.TemporaryDirectory() as folder:
                pool=Path(folder)/'gpu';pool.mkdir()
                older=pool/'wait-00000000000000000001-older.lock'
                with older.open('w') as stream:
                    json.dump(dict(started=time.monotonic()-age,seconds=3600),stream);stream.flush()
                    fcntl.flock(stream,fcntl.LOCK_EX)
                    with patch('validation_resources.AdmissionBudget.sample',return_value=1):
                        def admitted():
                            with validation_slot(['ffmpeg','-c:v','hevc_nvenc'],pool='gpu',
                                env={'MUXMENDER_VALIDATION_LOCK_ROOT':folder},timeout=0,estimated_duration=5):pass
                        if allowed:admitted()
                        else:
                            with self.assertRaises(TimeoutError):admitted()


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('ffmpeg'),
                     'Generated media checks run only in the Linux research image')
class SourceCacheIntegrationTests(unittest.TestCase):
    def test_second_attempt_reuses_complete_audio_check_only_for_same_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);inputs=root/'inputs';inputs.mkdir()
            source=inputs/'generated.wav'
            ffmpeg=shutil.which('ffmpeg')
            subprocess.run([ffmpeg,'-v','error','-nostdin','-n','-f','lavfi','-i',
                'sine=sample_rate=48000:duration=0.25','-c:a','pcm_s16le',str(source)],
                capture_output=True,check=True,timeout=30)
            work=root/'work';work.mkdir()
            args=SimpleNamespace(source=source,ffmpeg=ffmpeg,timeout=30,
                source_evidence_cache_dir=root/'cache')
            workflow=Workflow(args,work,lambda:None)
            metadata=dict(format={'duration':'0.25'},streams=[dict(index=0,codec_type='audio')])
            checksum=hashlib.sha256(source.read_bytes()).hexdigest()
            workflow.preflight_source_audio(source,metadata,checksum)
            with patch.object(workflow,'execute',side_effect=AssertionError('Repeated decode')):
                workflow.preflight_source_audio(source,metadata,checksum)
            source.write_bytes(source.read_bytes()+b'changed content')
            changed=hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.object(workflow,'execute') as decode:
                workflow.preflight_source_audio(source,metadata,changed)
            decode.assert_called_once()


if __name__=='__main__':unittest.main()
