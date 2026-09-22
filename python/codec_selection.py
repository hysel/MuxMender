"""Rank measured per-video trials. Never encodes, replaces, or deletes media.

Trial producers must validate quality, preservation and runtime support. Missing
evidence fails closed. Equal CQ values are not evidence of equal visual quality.
"""
import argparse
import json
import math
from fractions import Fraction

# Bump when the measured search/evaluation policy changes, not for every UI release.
EVALUATION_POLICY = 'source-driven-adaptive-size-quality-2'


def impossible_size_bound(references, samples, minimum_savings_percent):
    """Rejection-only proof: even zero bytes for remaining clips cannot pass.

    Missing, duplicated, unknown or unsuccessful sample evidence is inconclusive.
    Never infer a whole-movie size or relax the three-scene approval requirement.
    """
    if not math.isfinite(minimum_savings_percent) or not 0 <= minimum_savings_percent < 100:
        raise ValueError('Invalid savings threshold')
    ids=[r.get('id') for r in references]
    sample_ids=[s.get('reference_id') for s in samples]
    if (len(ids)<3 or len(set(ids))!=len(ids) or not samples or
        len(set(sample_ids))!=len(sample_ids) or not set(sample_ids).issubset(ids) or
        any(type(r.get('bytes')) is not int or r['bytes']<=0 for r in references) or
        any(type(s.get('bytes')) is not int or s['bytes']<=0 or
            s.get('encode_completed') is not True or s.get('error') for s in samples)):
        return None
    total=sum(r['bytes'] for r in references);used=sum(s['bytes'] for s in samples)
    budget=Fraction(total)*(100-Fraction(str(minimum_savings_percent)))/100
    if used<=budget:return None
    return dict(output_bytes_lower_bound=used,reference_bytes=total,
                savings_percent_upper_bound=100*(1-used/total),
                completed_samples=len(samples),total_samples=len(references))


def select_candidate(report, minimum_savings_percent=10.0):
    """Select smallest eligible aggregate output from identical sample sets.

    source_id should be a source content hash, not just a filename. This function
    validates evidence structure, not the truth of a caller's quality assertions.
    HDR trials require separate native-preservation and rendered-quality evidence.
    """
    if not math.isfinite(minimum_savings_percent) or not 0 <= minimum_savings_percent < 100:
        raise ValueError('Savings threshold must be finite and between 0 and 100')
    if report.get('schema') != 'muxmender-codec-trials-v1':
        raise ValueError('Unsupported trial report')
    source_id = report.get('source_id')
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError('Source identity is required')
    result = dict(action='keep_original', source_id=source_id, selected=None,
                  candidates=[], reason='No eligible trial meets the savings threshold',
                  reason_code='evaluation_inconclusive', cacheable=False,
                  estimate_only=True, full_output_validation_required=True,
                  source_replacement_authorized=False)
    if report.get('color_mode') not in ('sdr','pq','hlg'):
        result.update(action='specialized_review', reason='HDR/Dolby Vision requires a dedicated preservation evaluator')
        return result
    refs = report.get('references', [])
    ids = [r['id'] for r in refs]
    if len(ids) < 3 or len(set(ids)) != len(ids):
        raise ValueError('At least three distinct shared reference samples are required')
    if any(type(r.get('bytes')) is not int or r['bytes'] <= 0 for r in refs):
        raise ValueError('Positive reference byte sizes are required')
    reference_bytes = sum(r['bytes'] for r in refs)
    eligible = []
    seen = set()
    for trial in report.get('trials', []):
        trial_id = trial.get('id')
        if not isinstance(trial_id, str) or not trial_id or trial_id in seen:
            raise ValueError('Trial IDs must be nonempty and unique')
        seen.add(trial_id)
        reasons = []
        if trial.get('source_id') != source_id:
            reasons.append('source_identity_mismatch')
        if trial.get('runtime_supported') is not True:
            reasons.append('encoder_not_runtime_verified')
        if trial.get('playback_compatible') is not True:
            reasons.append('target_playback_not_verified')
        if trial.get('codec') not in ('hevc', 'av1'):
            reasons.append('unsupported_codec')
        if not trial.get('encoder') or not isinstance(trial.get('settings'), dict) or not trial['settings']:
            reasons.append('missing_encoder_settings')
        samples = trial.get('samples', [])
        sample_ids = [s.get('reference_id') for s in samples]
        if len(samples) != len(refs) or set(sample_ids) != set(ids):
            reasons.append('unmatched_reference_samples')
        structural_reasons=list(reasons)
        valid_sizes=all(type(s.get('bytes')) is int and s['bytes']>0 for s in samples)
        encode_evidence=bool(samples) and all(s.get('encode_completed') is True and not s.get('error') for s in samples)
        if (not [r for r in structural_reasons if r!='unmatched_reference_samples'] and
                trial.get('size_screen',{}).get('early_bound') is True):
            bound=impossible_size_bound(refs,samples,minimum_savings_percent)
            if bound:
                result['candidates'].append(dict(id=trial_id,codec=trial.get('codec'),**bound,
                    rejected_reasons=['insufficient_savings'],assessment='size_screened',quality_evaluated=False))
                continue
        # A size-screened trial is negative evidence only. It must never become
        # eligible without the ordinary quality/preservation/decode checks.
        if not structural_reasons and valid_sizes and encode_evidence and trial.get('size_screen',{}).get('rejected') is True:
            output_bytes=sum(s['bytes'] for s in samples)
            savings=100*(1-output_bytes/reference_bytes)
            if output_bytes>=reference_bytes or savings < minimum_savings_percent:
                result['candidates'].append(dict(id=trial_id,codec=trial.get('codec'),
                    output_bytes=output_bytes,savings_percent=savings,
                    rejected_reasons=['insufficient_savings'],assessment='size_screened',quality_evaluated=False))
                continue
        for sample in samples:
            if report.get('color_mode') in ('pq','hlg'):
                if sample.get('hdr_preservation_pass') is not True:
                    reasons.append('hdr_preservation_missing_or_failed')
                if sample.get('quality',{}).get('domain')!='hdr-common-render-v1':
                    reasons.append('hdr_quality_domain_missing')
            if sample.get('error'):
                reasons.append('sample_processing_error')
            for check in ('quality_pass', 'preservation_pass', 'decode_pass'):
                if sample.get(check) is not True:
                    reasons.append(check + '_missing_or_failed')
            if not sample.get('quality_method'):
                reasons.append('missing_quality_method')
            if type(sample.get('bytes')) is not int or sample['bytes'] <= 0:
                reasons.append('invalid_output_size')
        row = dict(id=trial_id, codec=trial.get('codec'), rejected_reasons=sorted(set(reasons)))
        row['assessment']='inconclusive'
        if (not structural_reasons and valid_sizes and not any(s.get('error') for s in samples)
                and any(s.get('quality_pass') is False and s.get('quality',{}).get('passed') is False
                        and s.get('preservation_pass') is True and s.get('decode_pass') is True for s in samples)):
            row['assessment']='quality_rejected'
            # Keep the evidence failures available for diagnostics, but distinguish
            # a measured rejection from unexecuted follow-up scene checks.
            row['quality_failed_reference_ids']=[s.get('reference_id') for s in samples
                if s.get('quality_pass') is False and s.get('quality',{}).get('passed') is False
                and s.get('preservation_pass') is True and s.get('decode_pass') is True]
            row['unevaluated_reference_ids']=[s.get('reference_id') for s in samples
                if not s.get('quality')]
            row['evidence_reasons']=row['rejected_reasons']
            row['rejected_reasons']=['measured_quality_below_threshold']
            row['detail']='A measured scene failed quality; untested scenes are not decoder or metadata failures.'
        if not reasons:
            output_bytes = sum(s['bytes'] for s in samples)
            savings = 100 * (1 - output_bytes / reference_bytes)
            row.update(output_bytes=output_bytes, savings_percent=savings)
            if output_bytes>=reference_bytes or savings < minimum_savings_percent:
                row['rejected_reasons'].append('insufficient_savings')
                row['assessment']='insufficient_savings'
            else:
                row['assessment']='eligible'
                eligible.append((output_bytes, trial_id, trial, savings))
        result['candidates'].append(row)
    if not eligible and result['candidates']:
        reasons = {reason for row in result['candidates'] for reason in row['rejected_reasons']}
        result['reason'] = ('No eligible trial: ' + ', '.join(sorted(reasons)))
        if all(r['assessment'] in ('size_screened','insufficient_savings','quality_rejected') for r in result['candidates']):
            result.update(reason_code='already_efficient_for_settings',cacheable=True,
                reason='No worthwhile savings found with current settings: short tests found no eligible size reduction within the quality limits. Original retained.')
        else:
            result['reason']='Evaluation incomplete: one or more encoders or validation checks failed or lacked evidence. Original retained; retry after resolving the issue.'
    if eligible:
        _, _, winner, savings = min(eligible, key=lambda row: (row[0], row[1]))
        result.update(action='encode_copy', reason='Smallest eligible measured sample output',
                      reason_code='candidate_selected',cacheable=False,
                      selected={k: winner[k] for k in ('id', 'codec', 'encoder', 'settings')},
                      estimated_savings_percent=savings)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', help='Measured trial JSON; read-only input')
    parser.add_argument('--minimum-savings-percent', type=float, default=10)
    args = parser.parse_args()
    with open(args.report, encoding='utf-8') as handle:
        report = json.load(handle)
    print(json.dumps(select_candidate(report, args.minimum_savings_percent), indent=2))


if __name__ == '__main__':
    main()
