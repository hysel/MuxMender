import copy
import unittest
from codec_selection import select_candidate


def evidence():
    refs = [{'id': str(i), 'bytes': 1000} for i in range(3)]
    trials = []
    for codec, size in [('hevc', 600), ('av1', 500)]:
        trials.append(dict(id=codec, source_id='source-hash', codec=codec,
                           encoder=codec+'_nvenc', settings={'cq': 23},
                           runtime_supported=True, playback_compatible=True,
                           samples=[dict(reference_id=r['id'], bytes=size,
                                         quality_pass=True, quality_method='reviewed',
                                         preservation_pass=True, decode_pass=True) for r in refs]))
    return dict(schema='muxmender-codec-trials-v1', source_id='source-hash',
                color_mode='sdr', references=refs, trials=trials)


class CodecSelectionTests(unittest.TestCase):
    def test_default_requires_at_least_twenty_five_percent(self):
        report=evidence()
        for trial in report['trials']:
            for sample in trial['samples']:sample['bytes']=751
        self.assertEqual(select_candidate(report)['action'],'keep_original')
        for trial in report['trials']:
            for sample in trial['samples']:sample['bytes']=750
        self.assertEqual(select_candidate(report)['action'],'encode_copy')

    def test_smallest_eligible_wins_and_input_unchanged(self):
        report = evidence()
        before = copy.deepcopy(report)
        result = select_candidate(report)
        self.assertEqual(result['selected']['codec'], 'av1')
        self.assertEqual(result['estimated_savings_percent'], 50)
        self.assertFalse(result['source_replacement_authorized'])
        self.assertEqual(report, before)

    def test_hevc_can_win(self):
        report = evidence()
        for sample in report['trials'][0]['samples']:
            sample['bytes'] = 400
        self.assertEqual(select_candidate(report)['selected']['codec'], 'hevc')

    def test_early_quality_rejection_explains_unexecuted_checks(self):
        report = evidence()
        report['trials'] = report['trials'][:1]
        samples = report['trials'][0]['samples']
        samples[0].update(quality_pass=False, quality={'passed': False, 'p5': 85})
        for sample in samples[1:]:
            sample.update(quality_pass=False, preservation_pass=False, decode_pass=False)
        before = copy.deepcopy(report)
        row = select_candidate(report)['candidates'][0]
        self.assertEqual(row['assessment'], 'quality_rejected')
        self.assertEqual(row['rejected_reasons'], ['measured_quality_below_threshold'])
        self.assertEqual(row['quality_failed_reference_ids'], ['0'])
        self.assertEqual(row['unevaluated_reference_ids'], ['1', '2'])
        self.assertIn('decode_pass_missing_or_failed', row['evidence_reasons'])
        self.assertEqual(report, before)

    def test_processing_error_not_hidden_by_quality_rejection(self):
        report = evidence()
        report['trials'] = report['trials'][:1]
        samples = report['trials'][0]['samples']
        samples[0].update(quality_pass=False, quality={'passed': False})
        samples[1]['error'] = 'Decoder failed'
        result = select_candidate(report)
        self.assertEqual(result['candidates'][0]['assessment'], 'inconclusive')
        self.assertIn('sample_processing_error', result['candidates'][0]['rejected_reasons'])
        self.assertFalse(result['cacheable'])

    def test_reject_failed_or_missing_evidence(self):
        for field in ['quality_pass', 'preservation_pass', 'decode_pass', 'quality_method']:
            report = evidence()
            del report['trials'][1]['samples'][0][field]
            self.assertEqual(select_candidate(report)['selected']['codec'], 'hevc')
        for field in ['runtime_supported', 'playback_compatible', 'settings']:
            report = evidence()
            del report['trials'][1][field]
            self.assertEqual(select_candidate(report)['selected']['codec'], 'hevc')

    def test_mismatched_source_and_samples_rejected(self):
        for change in ['source', 'sample', 'duplicate']:
            report = evidence()
            t = report['trials'][1]
            if change == 'source':
                t['source_id'] = 'other'
            elif change == 'sample':
                t['samples'].pop()
            else:
                t['samples'][0]['reference_id'] = '1'
            self.assertEqual(select_candidate(report)['selected']['codec'], 'hevc')

    def test_keep_original_when_savings_too_small(self):
        self.assertEqual(select_candidate(evidence(), 75)['action'], 'keep_original')

    def test_hdr_deferred(self):
        report = evidence()
        report['color_mode'] = 'dolby_vision'
        self.assertEqual(select_candidate(report)['action'], 'specialized_review')

    def test_invalid_inputs(self):
        for threshold in [float('nan'), float('inf'), -1, 100]:
            with self.assertRaises(ValueError):
                select_candidate(evidence(), threshold)
        report = evidence()
        report['references'].pop()
        with self.assertRaises(ValueError):
            select_candidate(report)

    def test_invalid_sizes_rejected(self):
        for size in [0, -1, True, float('nan')]:
            report = evidence()
            report['trials'][1]['samples'][0]['bytes'] = size
            self.assertEqual(select_candidate(report)['selected']['codec'], 'hevc')
