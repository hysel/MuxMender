"""Advisory full-file estimates from measured output rates, never approval."""
import math


def positive(value):
    return type(value) in (int,float) and math.isfinite(value) and value>0


def forecast(report, trial):
    """Avoid applying a clip's compression ratio to a different whole-file rate.

    The observed-rate range describes these scenes, not a statistical confidence
    interval or a bound on unseen content. Fixed attachments/covers need separate
    accounting and retain the existing sample-only estimate.
    """
    duration=report.get('source_duration_seconds');size=report.get('source_bytes')
    if not positive(duration) or not positive(size) or report.get('source_has_static_payload'):return None
    refs=report.get('references',[]);samples=trial.get('samples',[])
    if not refs or len(refs)!=len(samples):return None
    if any(not isinstance(r.get('window'),dict) or not positive(r.get('bytes')) for r in refs):return None
    windows={r.get('id'):r['window'].get('duration') for r in refs}
    if len(windows)!=len(refs) or len({s.get('reference_id') for s in samples})!=len(samples):return None
    if set(windows)!={s.get('reference_id') for s in samples}:return None
    if any(not positive(windows[s['reference_id']]) or not positive(s.get('bytes')) for s in samples):return None
    seconds=sum(windows.values());encoded=sum(s['bytes'] for s in samples)
    if seconds>duration*1.01:return None
    rates=[s['bytes']/windows[s['reference_id']] for s in samples]
    rate_output=encoded/seconds*duration
    ratio_output=encoded/sum(r['bytes'] for r in refs)*size
    output=max(rate_output,ratio_output)
    if not positive(output) or any(not positive(rate*duration) for rate in rates):return None
    return dict(method='conservative-sample-consensus-v1',estimated_output_bytes=round(output),
                output_rate_estimate_bytes=round(rate_output),compression_ratio_estimate_bytes=round(ratio_output),
                comparison_estimate_range_bytes=[round(min(min(rates)*duration,ratio_output)),round(max(max(rates)*duration,ratio_output))],
                estimated_savings_percent=100*(1-output/size),
                observed_rate_output_range_bytes=[round(min(rates)*duration),round(max(rates)*duration)],
                sampled_seconds=seconds,source_seconds=duration,source_bytes=size,
                sample_source_rate_ratio=sum(r['bytes'] for r in refs)/seconds/(size/duration),
                estimate_only=True,full_output_validation_required=True,
                range_scope='Observed scene rates only; unseen content, copied tracks and mux overhead can differ')
