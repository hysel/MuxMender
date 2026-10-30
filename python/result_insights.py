"""Bounded, read-only user reports from one request's retained evidence."""
import json
import math
from itertools import islice
from pathlib import Path

LABELS={'encoding':'Encoding','quality':'Picture quality checks','validation':'File checks',
        'waiting':'Waiting for resources','paused':'Paused for other apps','other':'Other work'}

def number(n):return type(n) in (int,float) and math.isfinite(n) and n>=0

def read_report(path,root):
    try:
        if any(p.is_symlink() for p in (path,path.parent)) or not path.resolve().is_relative_to(root.resolve()):return {}
        if path.stat().st_size>8*1024**2:return {}
        with path.open('rb') as stream:raw=stream.read(8*1024**2+1)
        if len(raw)>8*1024**2:return {}
        data=json.loads(raw)
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

def time_report(folder,job):
    paths=list(islice(folder.glob('job-*/job.json'),65))
    if len(paths)>64:return dict(available=False,reason='Too many timing records to combine safely.')
    records=[read_report(p,folder) for p in paths]
    if any(not r for r in records):return dict(available=False,reason='Some timing records are missing or unreadable; no combined total shown.')
    if not records:return dict(available=False,reason='No timing breakdown was recorded for this attempt.')
    records.sort(key=lambda r:r.get('started',0) if number(r.get('started')) else 0)
    totals={k:0. for k in LABELS};previous_end=None
    for r in records:
        start=r.get('started');end=r.get('finished',r.get('updated'));values=r.get('performance_seconds')
        if (not number(start) or not number(end) or end<start or
                previous_end is not None and start<previous_end or
                not isinstance(values,dict) or not values or any(not number(v) for v in values.values()) or
                r.get('performance_schema',0)<3):
            return dict(available=False,reason='Timing records are incomplete or overlap; a combined total would be misleading.')
        if sum(values.values())>end-start+2:
            return dict(available=False,reason='Recorded times exceed their measurement window; no combined total shown.')
        previous_end=end
        for key,value in values.items():
            bucket=('encoding' if key=='encoding' else 'quality' if key=='quality_measurement'
                else 'waiting' if key.endswith('_wait') else 'paused' if key=='gpu_pause'
                else 'validation' if key in ('metadata','checksums','full_decode','track_validation','frame_validation') else 'other')
            totals[bucket]+=value
    total=sum(totals.values())
    if total<=0:return dict(available=False,reason='No measured stage times are available yet.')
    return dict(available=True,partial=job.get('state') in ('pending','running'),recorded_seconds=total,
        stages=[dict(key=k,label=label,seconds=totals[k],share_percent=100*totals[k]/total) for k,label in LABELS.items()],
        note='Recorded processing time, including waits and pauses. Queue time before starting and unrecorded gaps are excluded; this is not an overall completion percentage.')

def option_name(trial):
    settings=trial.get('settings',{});encoder=trial.get('encoder','')
    name={'av1':'AV1','hevc':'HEVC','h264':'H.264'}.get(trial.get('codec'),'Encoding option')
    if isinstance(encoder,str) and encoder.endswith('_nvenc'):
        preset=settings.get('nvenc_preset') or {'transparent':'p7','balanced':'p6','compact':'p5'}.get(settings.get('quality'))
        if preset in ('p4','p5','p6','p7'):name+=' · '+preset.upper()
        cq=settings.get('nvenc_cq',{'transparent':18,'balanced':21,'compact':25}.get(settings.get('quality')))
        if type(cq) is int and 0<=cq<=63:name+=' · CQ '+str(cq)
    return name

def choice_report(folder):
    paths=list(islice(folder.glob('auto-*/selection.json'),2))
    if len(paths)!=1:return dict(available=False,reason='No single encoding-choice report was recorded for this attempt.')
    selection=read_report(paths[0],folder);report=read_report(paths[0].parent/'trials.json',folder)
    if not selection:return dict(available=False,reason='The encoding-choice report is unavailable.')
    selected=selection.get('selected') or {};speed=selection.get('encoding_speed_selection') or {}
    summary=('Chose a faster option that passed the checks, with a similar estimated file size.' if speed
        else 'Chose the smallest passing sample output.' if selection.get('action')=='encode_copy'
        else selection.get('reason') or 'No encoding option was selected.')
    outcomes={'eligible':'Passed; another option was preferred','speed_screened':'Did not show enough speed benefit',
        'size_screened':'Did not save enough space','insufficient_savings':'Did not save enough space',
        'quality_rejected':'Did not meet the quality target','inconclusive':'Checks incomplete'}
    assessments={c.get('id'):c for c in selection.get('candidates',[]) if isinstance(c,dict)}
    options=[]
    from encoding_speed import timings
    for trial in report.get('trials',[])[:64]:
        if not isinstance(trial,dict):continue
        row=assessments.get(trial.get('id'),{});measured=timings(trial)
        options.append(dict(name=option_name(trial),selected=trial.get('id')==selected.get('id'),
            outcome='Selected' if trial.get('id')==selected.get('id') else outcomes.get(row.get('assessment'),'Checks incomplete'),
            sample_savings_percent=row.get('savings_percent') if number(row.get('savings_percent')) else None,
            encode_seconds=sum(measured.values()) if measured else None,
            measured_samples=len(measured) if measured else 0,expected_samples=len(report.get('references',[])) or None))
    notes=[]
    if number(speed.get('measured_time_reduction_percent')):notes.append(f"{speed['measured_time_reduction_percent']:.1f}% less measured sample encoding time.")
    if number(speed.get('projected_extra_bytes')):notes.append(f"Projected extra file size: {speed['projected_extra_bytes']/1e6:.1f} MB compared with the smallest passing option.")
    if any(r['assessment']=='speed_screened' for r in assessments.values()):notes.append('Some faster options were stopped early because their measured speed gain was too small.')
    if not speed and not report.get('encoding_selection_policy'):notes.append('No preset speed comparison was recorded for this attempt.')
    return dict(available=True,summary=summary,notes=notes,options=options,
        note='Sample estimates, not guaranteed full-file results. Sample encoding time excludes queue waits and GPU-sharing pauses. See the final result above for full-file validation and replacement status.')

def result_insights(folder,job):
    result=dict(job_id=job['id'])
    for key,reader in [('timing',lambda:time_report(folder,job)),('choice',lambda:choice_report(folder))]:
        try:result[key]=reader()
        except (TypeError,ValueError,KeyError,AttributeError):
            result[key]=dict(available=False,reason='This older report is incomplete or unreadable.')
    if job.get('publication_only') and not result['choice']['available']:
        result['choice']=dict(available=True,options=[],notes=[],
            summary='This attempt uses an existing validated copy rather than re-encoding it.',
            note='Encoding comparisons belong to the original copy attempt. These details cover the current publication attempt.')
    return result
