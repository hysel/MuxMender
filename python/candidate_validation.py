"""Order expensive checks; size bounds can reject work, never approve media."""
import math


def encoded_size(report, trial):
    """Only complete successful encodes of the identical reference set count."""
    refs=report.get('references',[])
    ids=[r.get('id') for r in refs]
    samples=trial.get('samples',[])
    sample_ids=[s.get('reference_id') for s in samples]
    if (not ids or len(set(ids))!=len(ids) or len(sample_ids)!=len(ids)
            or len(set(sample_ids))!=len(sample_ids) or set(sample_ids)!=set(ids)
            or trial.get('source_id')!=report.get('source_id')
            or trial.get('runtime_supported') is not True
            or trial.get('playback_compatible') is not True
            or trial.get('structural_failure') or trial.get('error')
            or any(type(r.get('bytes')) is not int or r['bytes']<=0 for r in refs)
            or any(type(s.get('bytes')) is not int or s['bytes']<=0
                   or s.get('encode_completed') is not True or s.get('error') for s in samples)):
        return None
    return sum(s['bytes'] for s in samples)


def dominance_proof(report, trial, incumbent_id, minimum_savings_percent):
    """Prove an unmeasured larger trial cannot win existing size/speed rules.

    A complete incumbent must already pass every ordinary eligibility check.
    Retain all ties and all candidates inside the existing speed/size band,
    including before the speed policy is activated by a later preset trial.
    """
    from codec_selection import select_candidate
    from encoding_speed import MAXIMUM_RELATIVE_EXTRA_PERCENT,MAXIMUM_PROJECTED_EXTRA_BYTES
    size=encoded_size(report,trial)
    source_bytes=report.get('source_bytes')
    if (size is None or type(source_bytes) is not int or source_bytes<=0
            or any(s.get('quality') or s.get('quality_pass') is True
                   or s.get('preservation_pass') is True or s.get('decode_pass') is True
                   for s in trial.get('samples',[]))):
        return None
    incumbents=[t for t in report.get('trials',[]) if t.get('id')==incumbent_id]
    if len(incumbents)!=1 or incumbent_id==trial.get('id'):return None
    incumbent=incumbents[0]
    # Do not recursively rely on another unmeasured dominance claim.
    if incumbent.get('validation_dominance'):return None
    before=encoded_size(report,incumbent)
    if before is None or size<=before:return None
    single=dict(report,trials=[incumbent])
    try:eligible=select_candidate(single,minimum_savings_percent)
    except (KeyError,TypeError,ValueError,OverflowError):return None
    if eligible['action']!='encode_copy':return None
    reference_bytes=sum(r['bytes'] for r in report['references'])
    # Match the selector's arithmetic at its existing boundary, rather than
    # introducing a subtly different rounded decision for very large sizes.
    try:
        relative_outside=size>before*(1+MAXIMUM_RELATIVE_EXTRA_PERCENT/100)
        projected_extra=(size-before)*source_bytes/reference_bytes
    except OverflowError:return None
    if not math.isfinite(projected_extra):return None
    absolute_outside=projected_extra>MAXIMUM_PROJECTED_EXTRA_BYTES
    if not (relative_outside or absolute_outside):return None
    return dict(policy='validated-candidate-dominance-v1',incumbent_id=incumbent_id,
                candidate_sample_bytes=size,incumbent_sample_bytes=before,
                reference_bytes=reference_bytes,source_bytes=source_bytes,
                outside_relative_speed_band=relative_outside,
                outside_projected_speed_band=absolute_outside,
                quality_evaluated=False,rejection_only=True)


def validate_initial(report, minimum_savings_percent, evaluate, guard, completed=None):
    """Validate size-eligible initial trials smallest first, preserving errors."""
    from codec_selection import select_candidate
    pending=[t for t in report.get('trials',[]) if t.get('validation_deferred') is True]
    def order(trial):
        size=encoded_size(report,trial)
        return (size is None,size or 0,trial.get('id',''))
    pending.sort(key=order)
    for index,trial in enumerate(pending):
        guard()
        decision=select_candidate(report,minimum_savings_percent)
        incumbent=(decision.get('selected') or {}).get('id')
        proof=dominance_proof(report,trial,incumbent,minimum_savings_percent) if incumbent else None
        if proof:
            trial['validation_dominance']=proof
            trial['screened_out']='A fully validated smaller candidate already wins outside the speed/size band; quality not evaluated'
        else:
            evaluate(trial)
        trial['validation_deferred']=False
        if completed:completed(trial,index+1,len(pending))
