"""Five-scene AV1 CQ22 qualification, then a conditional full safe copy.

Uses installed shared validators, never publishes or weakens selected gates.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys


def sample_eligible(rows,required_percent):
    from quality_profiles import profile
    finite_score=lambda value:type(value) in (int,float) and math.isfinite(value)
    policy=profile('space-saver')
    valid=(len(rows)==5 and all(r.get('quality',{}).get('passed') is True
        and finite_score(r['quality'].get('mean')) and r['quality']['mean']>=policy['mean']
        and finite_score(r['quality'].get('p5')) and r['quality']['p5']>=policy['p5']
        and type(r['quality'].get('frames')) is int and r['quality']['frames']>0 for r in rows))
    source=sum(r['source_bytes'] for r in rows);output=sum(r['output_bytes'] for r in rows)
    return valid and source>0 and 100*(1-output/source)>=required_percent


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux image qualification only')
    spec=importlib.util.spec_from_file_location('scheduling_helpers',Path(__file__).with_name('benchmark_job_scheduling.py'))
    helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
    engine=helpers.image_engine()
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();identifier=args.request;root=args.output
    if len(identifier)!=32 or any(x not in '0123456789abcdef' for x in identifier):raise ValueError('Invalid request')
    if root.exists() or not root.is_absolute() or not root.resolve().is_relative_to('/output'):raise ValueError('Use a new isolated output folder')
    helpers.idle();root.mkdir()
    from job_tracking import tracked_call,progress
    from savings_policy import requirement
    from replacement_cleanup import prune_generated
    from task_progress import digest
    from autonomous_queue import write
    import app_version
    write(root/'engine.json',dict(version=app_version.VERSION,module=engine.__file__,sha256=hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()))
    os.environ['MUXMENDER_VALIDATION_LOCK_ROOT']=str(root/'admission')
    os.environ['MUXMENDER_PAUSE_LEASE']='/output/ui-requests/gpu-yield-lease.json'
    rows=[];retained=[]
    def run():
        queue=json.loads(Path('/output/ui-requests/requests.json').read_text())
        previous=next(j for j in queue['jobs'] if j['id']==identifier)
        source=Path(previous['source']);stamp=helpers.identity(source)
        if source.is_symlink() or not source.resolve().is_relative_to('/media'):raise ValueError('Invalid source')
        if previous['settings'].get('quality_profile')!='space-saver':raise ValueError('Use the approved Space saver case')
        reports=list((Path('/output/ui-requests')/('request-'+identifier)).glob('auto-*/trials.json'))
        if len(reports)!=1:raise ValueError('One previous trial report required')
        references=json.loads(reports[0].read_text())['references']
        if len(references)!=5:raise ValueError('Expected all five scene windows')
        baseline=digest(source);needed=requirement(source.stat().st_size,previous['settings'].get('savings_mode','fixed'),previous['settings']['minimum_savings'])
        settings=dict(codec='av1',encoder='av1_nvenc',quality='balanced',nvenc_cq=22,nvenc_preset='p7')
        for index,reference in enumerate(references):
            helpers.idle();progress('Checking CQ22 scene '+str(index+1)+' of 5',index,5,unit='scenes',detail='Original resolution; unchanged Space saver 90/90 gates')
            inputs=root/f'inputs-{index}';inputs.mkdir();start=float(reference['position'])
            with (inputs/'extract.log').open('x') as log:
                subprocess.run(['mkvmerge','-o',str(inputs/'source.mkv'),'--split',f'parts:{start:.3f}s-{start+10:.3f}s',str(source)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
            clips=list(inputs.glob('*.mkv'))
            if len(clips)!=1:raise ValueError('Expected exactly one excerpt')
            row=helpers.task(dict(clip=str(clips[0]),settings=settings,mean=90,profile='space-saver'),str(root/f'scene-{index}'))
            rows.append(row);write(root/'scene-results.json',dict(results=rows,complete=len(rows)==5,publication_authorized=False))
        if helpers.identity(source)!=stamp or digest(source)!=baseline:raise ValueError('Source changed')
        eligible=sample_eligible(rows,needed['effective_percent'])
        write(root/'decision.json',dict(samples_eligible=eligible,savings_policy=needed,settings=settings,quality_policy=dict(mean=90,p5=90),publication_authorized=False))
        if not eligible:
            write(root/'result.json',dict(complete=True,state='original-kept',full_conversion_started=False,publication_authorized=False))
            progress('CQ22 samples did not meet both quality and savings requirements',detail='Original retained; no full conversion started')
            return 0
        helpers.idle();full=root/'full';full.mkdir()
        workflow,before,info=helpers.prepare_workflow(dict(clip=str(source),mean=90,profile='space-saver'),full)
        duration=float(before['format']['duration']);output=full/'full-av1.mkv'
        progress('Encoding qualified CQ22 safe copy',detail='No replacement authorized')
        workflow.encode_preserving_color(source,output,settings,info,before,'full-encode',duration)
        size_pass=source.stat().st_size-output.stat().st_size>=needed['required_bytes'] and output.stat().st_size<source.stat().st_size
        if not size_pass:
            write(root/'result.json',dict(complete=True,state='original-kept-full-size',full_conversion_started=True,publication_authorized=False))
            return 0
        progress('Validating full CQ22 safe copy',detail='Complete frame, audio, timing and metadata checks; quality measured on all five scenes')
        frames=workflow.frame_file(source,'full-source',before['format']);count=workflow.validate(source,output,before,'av1','full',frames)
        if digest(source)!=baseline:raise ValueError('Original changed; no output approved')
        output_hash=digest(output)
        write(root/'result.json',dict(complete=True,state='validated-research-safe-copy',full_conversion_started=True,
            output=str(output),source_bytes=source.stat().st_size,output_bytes=output.stat().st_size,
            saved_percent=100*(1-output.stat().st_size/source.stat().st_size),source_sha256=baseline,
            output_sha256=output_hash,validated_frames=count,quality_scope='All five sample scenes; complete technical validation of full output',publication_authorized=False))
        retained.append(output)
        return 0
    try:return tracked_call(run,'AV1 CQ22: all scenes and conditional full copy',folder=root/'reports')
    finally:
        cleanup=prune_generated(root,execute=True,keep_paths=retained)
        write(root/'cleanup-summary.json',{k:cleanup[k] for k in ('state','files','bytes')})


if __name__=='__main__':raise SystemExit(main())
