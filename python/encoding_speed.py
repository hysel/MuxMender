"""Measured speed/size tradeoff after ordinary candidate eligibility checks."""
import math

POLICY='measured-speed-size-v1'

def faster_presets(settings):
    if settings.get('encoder') not in ('hevc_nvenc','av1_nvenc','h264_nvenc'):return []
    current=settings.get('nvenc_preset') or {'transparent':'p7','balanced':'p6','compact':'p5'}.get(settings.get('quality'))
    if current not in ('p4','p5','p6','p7'):return []
    return [dict(settings,nvenc_preset=p) for p in ('p4','p5') if int(p[1])<int(current[1])]

def timings(trial):
    values={}
    for sample in trial.get('samples',[]):
        timing=sample.get('encoding_timing',{})
        if not isinstance(timing,dict):return None
        seconds=timing.get('execution_seconds')
        identifier=sample.get('reference_id')
        if (identifier in values or timing.get('scope')!='native-stage-active-v1' or
                timing.get('completed') is not True or type(seconds) not in (int,float) or
                not math.isfinite(seconds) or seconds<.5):return None
        values[identifier]=seconds
    return values if values and sum(values.values())>=3 else None

def speed_screen(sample,baseline):
    old=next((s for s in baseline.get('samples',[]) if s.get('reference_id')==sample.get('reference_id')),None)
    if old is None:return dict(rejected=True,reason='No matching baseline scene timing')
    # The short first scene is a rejection screen only, never approval evidence.
    def seconds(row):
        value=row.get('encoding_timing',{})
        if not isinstance(value,dict) or value.get('scope')!='native-stage-active-v1' or value.get('completed') is not True:return None
        n=value.get('execution_seconds')
        return n if type(n) in (int,float) and math.isfinite(n) and n>=.5 else None
    before,after=seconds(old),seconds(sample)
    return dict(rejected=before is None or after is None or after>before*.8,
                baseline_seconds=before,candidate_seconds=after,
                minimum_time_reduction_percent=20,rejection_only=True)


def comparison_presets(report,decision,duration,*,explicit=False):
    if (explicit or type(duration) not in (int,float) or not math.isfinite(duration)
            or duration<300 or decision.get('action')!='encode_copy'):return []
    selected=decision.get('selected') or {}
    trial=next((t for t in report.get('trials',[]) if t.get('id')==selected.get('id')),None)
    if trial is None or timings(trial) is None:return []
    measured=[t.get('settings') for t in report.get('trials',[])]
    return [s for s in faster_presets(selected.get('settings',{})) if s not in measured]


def choose(report,eligible,smallest):
    """Never admit a trial here. Only compare the already eligible trial set.

    A faster choice may be at most 5% larger than the smallest passing output,
    and its projected extra whole-file space at most 512 MiB. Require at least
    20% shorter measured encoding and no slower scene. Missing evidence keeps
    the size-first winner. Timings exclude admission and GPU sharing pauses.
    """
    if report.get('encoding_selection_policy')!=POLICY:return smallest,None
    reference_bytes=sum(r['bytes'] for r in report['references'])
    source_bytes=report.get('source_bytes')
    baseline=timings(smallest[2])
    if type(source_bytes) is not int or source_bytes<=0 or not baseline:return smallest,None
    duration=report.get('source_duration_seconds');overhead=report.get('encoding_comparison_seconds')
    windows=[r.get('window',{}).get('duration') for r in report['references']]
    if (any(type(n) not in (int,float) or not math.isfinite(n) or n<=0 for n in [duration,*windows])
            or type(overhead) not in (int,float) or not math.isfinite(overhead) or overhead<0):return smallest,None
    scale=duration/sum(windows)
    choices=[]
    for row in eligible:
        measured=timings(row[2])
        if not measured or measured.keys()!=baseline.keys():continue
        extra=(row[0]-smallest[0])*source_bytes/reference_bytes
        projected_gain=(sum(baseline.values())-sum(measured.values()))*scale
        if (projected_gain<=overhead or row[0]>smallest[0]*1.05 or extra>512*1024**2 or
                sum(measured.values())>sum(baseline.values())*.8 or
                any(measured[k]>baseline[k] for k in baseline)):continue
        choices.append((sum(measured.values()),row[0],row[1],row,extra))
    if not choices:return smallest,None
    seconds,_,_,winner,extra=min(choices,key=lambda row:row[:3])
    return winner,dict(policy=POLICY,smallest_trial=smallest[1],
        measured_encoding_seconds=seconds,smallest_encoding_seconds=sum(baseline.values()),
        measured_time_reduction_percent=100*(1-seconds/sum(baseline.values())),
        comparison_seconds=overhead,projected_net_encoding_seconds_saved=(sum(baseline.values())-seconds)*scale-overhead,
        projected_extra_bytes=math.ceil(extra),maximum_relative_output_increase_percent=5,
        maximum_projected_extra_bytes=512*1024**2,estimate_only=True,
        quality_thresholds_unchanged=True)
