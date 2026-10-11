"""Generated evidence tests; no library media or GPU commands are executed."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from codec_selection import select_candidate
from quality_profiles import profile, validate_policy, scores_meet_policy
from workspace_history import decision_evidence


def measured_report(identifier):
    references=[dict(id=str(i),bytes=1000) for i in range(3)]
    trials=[]
    # These are invented measurements, not hardware benchmark results.
    for name,codec,size,mean in [('detail','hevc',650,97),('balanced','av1',500,94.5),('compact','av1',400,91)]:
        trials.append(dict(id=name,source_id='fixture-hash',codec=codec,encoder=codec+'_nvenc',
            settings=dict(codec=codec,encoder=codec+'_nvenc',quality=name),
            runtime_supported=True,playback_compatible=True,
            samples=[dict(reference_id=r['id'],bytes=size,encode_completed=True,
                quality_pass=True,quality_method='VMAF',preservation_pass=True,decode_pass=True,
                quality=dict(mean=mean,p5=90.5,frames=48,passed=True)) for r in references]))
    selected=profile(identifier)
    return dict(schema='muxmender-codec-trials-v1',source_id='fixture-hash',color_mode='sdr',
        quality_policy=dict(id=identifier,mean=selected['mean'],p5=selected['p5']),references=references,trials=trials)


class QualityAutomationTests(unittest.TestCase):
    def test_bounded_nvenc_search_does_not_repeat_ineffective_cq_variants(self):
        from auto_optimize import adaptive_candidates
        report=dict(output_preset='tv1080',trials=[dict(encoder='hevc_nvenc',codec='hevc',
            runtime_supported=True,playback_compatible=True,settings=dict(quality='balanced'),samples=[])])
        extra=adaptive_candidates(report)
        self.assertEqual(len(extra),1)
        self.assertEqual(extra[0]['nvenc_preset'],'p7')
        self.assertNotIn('nvenc_cq',extra[0])
        report['trials'].append(dict(report['trials'][0],settings=extra[0]))
        self.assertEqual(adaptive_candidates(report),[])

    def test_each_user_choice_selects_smallest_candidate_that_actually_meets_it(self):
        for identifier,winner in [('strict','detail'),('balanced','balanced'),('space-saver','compact')]:
            with self.subTest(profile=identifier):
                report=measured_report(identifier);before=copy.deepcopy(report)
                result=select_candidate(report)
                self.assertEqual(result['action'],'encode_copy')
                self.assertEqual(result['selected']['id'],winner)
                self.assertEqual(result['quality_policy'],report['quality_policy'])
                self.assertFalse(result['source_replacement_authorized'])
                self.assertEqual(report,before,'Selection must not lower limits or rewrite evidence')

    def test_no_candidate_never_lowers_quality_and_is_not_authorized(self):
        report=measured_report('strict');report['trials']=report['trials'][1:]
        decision=select_candidate(report)
        self.assertEqual(decision['action'],'keep_original')
        self.assertIsNone(decision['selected'])
        self.assertEqual(decision['quality_policy']['mean'],95)
        self.assertFalse(decision['source_replacement_authorized'])

    def test_missing_nonfinite_or_false_numeric_proof_never_approves(self):
        for changes in ({'mean':float('nan')},{'p5':float('inf')},{'mean':True},
                        {'frames':0},{'frames':True},{'passed':False},{'p5':89.9}):
            with self.subTest(changes=changes):
                report=measured_report('space-saver');report['trials']=report['trials'][:1]
                report['trials'][0]['samples'][0]['quality'].update(changes)
                self.assertEqual(select_candidate(report)['action'],'keep_original')
        report=measured_report('strict')
        for trial in report['trials']:
            for sample in trial['samples']:sample.pop('quality')
        self.assertEqual(select_candidate(report)['action'],'keep_original')

    def test_other_gates_still_apply_even_when_scores_pass(self):
        for check in ('decode_pass','preservation_pass','quality_pass'):
            report=measured_report('space-saver')
            for trial in report['trials']:trial['samples'][0][check]=False
            self.assertEqual(select_candidate(report)['action'],'keep_original')
        report=measured_report('space-saver')
        for trial in report['trials']:
            for sample in trial['samples']:sample['bytes']=950
        self.assertEqual(select_candidate(report,10)['action'],'keep_original')

    def test_recorded_profile_cannot_be_lower_than_named_floor(self):
        for changes in ({'mean':90},{'p5':89},{'mean':float('nan')},{'id':'unknown'}):
            policy=dict(id='strict',mean=95,p5=90);policy.update(changes)
            with self.assertRaises(ValueError):validate_policy(policy)
        self.assertFalse(scores_meet_policy(None,dict(id='strict',mean=95,p5=90)))

    def test_history_summary_retains_selected_policy_and_measured_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=measured_report('balanced');selection=select_candidate(report)
            (Path(tmp)/'trials.json').write_text(json.dumps(report),encoding='utf-8')
            evidence=decision_evidence(tmp,selection)
            self.assertEqual(evidence['quality_policy'],report['quality_policy'])
            self.assertEqual(evidence['quality'][1]['samples'][0]['mean'],94.5)
