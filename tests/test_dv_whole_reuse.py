import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from dv_mel import reuse_whole_source_candidate


def fixture(root):
    source=root/'source.mkv';source.write_bytes(b's'*100)
    run=root/'run';run.mkdir();output=run/'candidate.mkv';output.write_bytes(b'o'*40)
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    settings=dict(codec='hevc',encoder='hevc_nvenc',nvenc_cq=22)
    score=dict(frames=24,mean=98,p5=96,passed=True)
    result=dict(source_sha256=sha,source_bytes=100,source_unchanged=True,copied_tracks_preserved=True,
                frame_checks=dict(frames=24),layer_checks=dict(frames=24,enhancement_types=['MEL']),output=str(output),output_bytes=40,
                output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),settings=settings,
                quality=dict(self=dict(score),candidate=dict(score),domain='dv-libplacebo-common-render-v1'))
    report=dict(source_id=sha,references=[dict(id='0',whole_source=True,sha256=sha,bytes=100,path=str(source))],
                trials=[dict(id='candidate',samples=[dict(reference_id='0',whole_source_result=result)])])
    decision=dict(action='encode_copy',selected=dict(id='candidate',settings=settings))
    return SimpleNamespace(directory=run,guard=lambda:None),source,report,decision,sha,result


class WholeSourceReuseTests(unittest.TestCase):
    def test_complete_trial_is_reused_with_full_savings_policy(self):
        for threshold,status in ((25,'validated_copy'),(65,'savings_target_missed')):
            with self.subTest(threshold=threshold),tempfile.TemporaryDirectory() as tmp:
                work,source,report,decision,sha,result=fixture(Path(tmp))
                reused=reuse_whole_source_candidate(work,source,report,decision,source_id=sha,minimum_savings_percent=threshold)
                self.assertEqual(reused['status'],status)
                self.assertTrue(reused['reused_whole_source_trial'])
                self.assertFalse(reused['publication_authorized'])
                self.assertEqual('selected' in reused,status=='validated_copy')
                self.assertEqual(source.read_bytes(),b's'*100)

    def test_samples_or_unbound_old_outputs_require_normal_full_validation(self):
        for defect in ('sample','no-hash','wrong-settings','wrong-reference'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as tmp:
                work,source,report,decision,sha,result=fixture(Path(tmp))
                if defect=='sample':report['references'][0]['whole_source']=False
                if defect=='no-hash':del result['output_sha256']
                if defect=='wrong-settings':result['settings']=dict(nvenc_cq=24)
                if defect=='wrong-reference':report['trials'][0]['samples'][0]['reference_id']='other'
                self.assertIsNone(reuse_whole_source_candidate(work,source,report,decision,source_id=sha))
                self.assertFalse((work.directory/'mel-full-refinement.json').exists())

    def test_source_output_mutation_and_unowned_output_are_errors(self):
        for defect in ('source','output','unowned'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);work,source,report,decision,sha,result=fixture(root)
                if defect=='source':source.write_bytes(b't'*100)
                if defect=='output':Path(result['output']).write_bytes(b'p'*40)
                if defect=='unowned':
                    other=root/'other.mkv';other.write_bytes(b'o'*40);result['output']=str(other)
                with self.assertRaises(ValueError):reuse_whole_source_candidate(work,source,report,decision,source_id=sha)

    def test_quality_failure_is_not_promoted_by_hash_or_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            work,source,report,decision,sha,result=fixture(Path(tmp))
            result['quality']['candidate'].update(mean=80,passed=False)
            self.assertIsNone(reuse_whole_source_candidate(work,source,report,decision,source_id=sha))
