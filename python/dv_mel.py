"""Shared DV candidate orchestration and MEL encoding service.

Uses ordinary HDR encoding and copied-track validation. Automatic selection is
separate: a successful candidate is evidence, not permission to replace a file.
"""
from copy import copy
from fractions import Fraction
from pathlib import Path
import json
import re
import math

from auto_optimize import Workflow, main_video
from dv_layer_evidence import extract_layers, layer_preservation_evidence, requires_fel_reconstruction
from dv_full_file import frame_evidence, frames, compare_frames, timestamped_video_command
from hdr10plus_preserve import write_decoded_timestamps, preserved_tracks_command
from hdr_auto import measure_prefix_quality
from task_progress import digest
import muxmender as mm


def candidate_service(profile):
    if profile==7:return encode_candidate,'dv-libplacebo-common-render-v1'
    if profile in (5,8):
        from dv_single import encode_candidate as single
        return single,'dv-libplacebo-common-render-v1'
    raise ValueError('Unsupported shared candidate profile')


def candidate_evidence(result, identity, size, profile):
    _,domain=candidate_service(profile)
    fel=profile==7 and requires_fel_reconstruction(result.get('layer_checks',{}).get('enhancement_types'))
    if fel:
        domain='dv-felbaker-common-render-v1'
        layer=result['layer_checks'];quality=result.get('quality',{})
        if (layer.get('scope')!='layer-preservation-only' or quality.get('native_fel_quality_evaluated') is not True
                or result.get('status')=='unqualified-fel-research-copy'
                or any(not re.fullmatch('[0-9a-f]{64}',layer.get(k,'')) for k in ('rpu_sha256','enhancement_video_sha256'))
                or not {'native_dv','compatible_fallback'}<=quality.get('views',{}).keys()):
            raise ValueError('Incomplete native FEL and compatible-fallback evidence')
    count=result['frame_checks']['frames']
    if (result.get('source_sha256')!=identity or result.get('source_bytes')!=size
            or result.get('source_unchanged') is not True or result.get('copied_tracks_preserved') is not True
            or type(count) is not int or count<=0
            or any(result['quality'][k]['frames']!=count for k in ('self','candidate'))
            or result['quality'].get('domain')!=domain):
        raise ValueError('Incomplete or mismatched DV candidate evidence')
    if profile==7 and result['layer_checks']['frames']!=count:
        raise ValueError('Incomplete layer coverage')
    if fel:
        for key in ('self','candidate'):
            views=[result['quality']['views'][view][key] for view in ('native_dv','compatible_fallback')]
            if (any(view.get('frames')!=count for view in views)
                    or any(result['quality'][key][metric]!=min(view[metric] for view in views) for metric in ('mean','p5'))):
                raise ValueError('Native FEL and fallback quality coverage or weakest-view score changed')
    if profile in (5,8) and (result.get('rpu_frames')!=count or result.get('configuration',{}).get('dv_profile')!=profile
            or not re.fullmatch('[0-9a-f]{64}',result.get('rpu_digest',''))):
        raise ValueError('Incomplete single-layer RPU evidence')
    return count


def run(workflow_args, source, root, data, baseline):
    """Automatic frontend adapter for DV HEVC, separate copies only.

    No vendor exclusion: compiled backends are tried against real references;
    actual failures remain candidate-specific. FEL requires a reconstruction
    metric and is identified from the complete RPU inventory, not a filename.
    """
    import shutil
    import os
    import time
    import uuid
    from amd_av1_batch import fingerprint
    from dvd_av1_batch import save
    from job_tracking import progress, workflow_stage
    from codec_selection import EVALUATION_POLICY
    args=workflow_args
    configs=[s for s in main_video(data).get('side_data_list',[]) if 'dv_profile' in s]
    if len(configs)!=1:raise ValueError('Expected one DV configuration')
    profile=configs[0]['dv_profile'];candidate_service(profile)
    plan=dict(route='dv7-layer-preserving' if profile==7 else f'dv{profile}-native-preserving',source=str(source),source_deletion=False,
              publication_authorized=False,full_copy=args.encode_best,evaluation_policy=EVALUATION_POLICY)
    if not args.execute:
        print(json.dumps(dict(dry_run=True,plan=plan),indent=2));return 0
    if 'hevc' not in args.playback_verified_codecs:
        raise ValueError('DV preservation path needs HEVC playback support')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    directory=root/('auto-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);directory.mkdir()
    state=dict(state='running',source=str(source),original_retained=True,publication_authorized=False,
               integration_qualification_required=True)
    save(directory/'plan.json',plan);save(directory/'status.json',state)
    def guard():
        if (root/'STOP').exists() or (directory/'STOP').exists():raise KeyboardInterrupt('STOP requested')
        if fingerprint(source)!=baseline:raise RuntimeError('Source changed during layered workflow')
        if shutil.disk_usage(directory).free<args.min_free_gib*1024**3:
            raise RuntimeError('Output reserve exhausted')
    work=Workflow(args,directory,guard)
    try:
        guard();identity=digest(source,guard)
        workflow_stage('inspect')
        if profile==7:
            inventory=extract_layers(work,source,'admission-layers')
            if requires_fel_reconstruction(inventory['enhancement_types']):
                from dv_fel_quality import renderer_plugin
                args.fel_render_plugin=renderer_plugin(args)
        encoder_ffmpeg=getattr(args,'encoder_ffmpeg',None) or args.ffmpeg
        names=mm.ffmpeg_encoder_names(encoder_ffmpeg)
        vendors=list(mm.HARDWARE_ENCODERS) if args.hardware=='auto' else [args.hardware]
        candidates=[]
        for vendor in vendors:
            encoder=mm.HARDWARE_ENCODERS.get(vendor,{}).get('hevc')
            if encoder not in names:continue
            if vendor=='nvidia':
                for cq in getattr(args,'hevc_nvenc_cq',None) or [24,28]:
                    candidate=dict(codec='hevc',encoder=encoder,quality='balanced',nvenc_cq=cq,nvenc_preset='p7')
                    if getattr(args,'nvenc_maxrate_mbps',None) is not None:
                        candidate['nvenc_maxrate_mbps']=args.nvenc_maxrate_mbps
                    candidates.append(candidate)
            else:
                candidates.extend(dict(codec='hevc',encoder=encoder,quality=q) for q in args.qualities)
        if not candidates:raise RuntimeError('No compiled HEVC backend for selected hardware; no automatic CPU fallback')
        workflow_stage('compare')
        report,decision=compare_candidates(work,source,candidates,args.seconds,
            playback_verified_codecs=args.playback_verified_codecs,
            minimum_savings_percent=args.minimum_savings_percent,mean_floor=args.vmaf_mean,p5_floor=args.vmaf_p5,
            encoder_ffmpeg=encoder_ffmpeg,profile=profile)
        save(directory/'trials.json',report);save(directory/'selection.json',decision)
        state.update(state='trials-completed',decision=decision)
        if decision['action']!='encode_copy':
            if any(s.get('error') for t in report['trials'] for s in t['samples']):
                raise RuntimeError('Layered candidate evaluation was incomplete; see individual trial errors')
        elif args.encode_best:
            workflow_stage('encode')
            result=reuse_whole_source_candidate(work,source,report,decision,source_id=identity,
                savings_mode=getattr(args,'savings_mode','fixed'),minimum_savings_percent=args.minimum_savings_percent,
                mean_floor=args.vmaf_mean,p5_floor=args.vmaf_p5,profile=profile)
            if result is None:
                result=refine_full_candidate(work,source,decision['selected']['settings'],source_id=identity,
                    playback_verified_codecs=args.playback_verified_codecs,
                    savings_mode=getattr(args,'savings_mode','fixed'),minimum_savings_percent=args.minimum_savings_percent,
                    mean_floor=args.vmaf_mean,p5_floor=args.vmaf_p5,encoder_ffmpeg=encoder_ffmpeg,profile=profile)
            state['full_refinement']=result['status']
            if result['status']=='validated_copy':
                output=Path(result['selected']['output'])
                if output.is_symlink() or not output.resolve(strict=True).is_relative_to(directory.resolve()):
                    raise ValueError('Layered output escapes owned directory')
                # The encoder only creates a copy. Qualification evidence lets
                # the common publisher act later, if replacement was selected.
                final=directory/'full-hevc.mkv';os.link(output,final)
                output_hash=digest(final,guard)
                qualified=publication_qualified(result['selected'],identity,source.stat().st_size,
                    output_hash,profile,args.vmaf_mean,args.vmaf_p5,
                    experimental=bool(getattr(args,'experimental_dv81',False)))
                state.update(state='validated-copy-awaiting-playback',output=str(final),source_sha256=identity,
                    output_sha256=output_hash,saved_percent=result['selected']['saved_percent'],
                    publication_authorized=qualified,integration_qualification_required=not qualified)
            else:
                if result['status'] in ('savings_target_missed','savings_requirement_unreachable'):
                    state.update(state='full-output-rejected-insufficient-savings',reason=result['status'])
                else:
                    decision=dict(action='keep_original',selected=None,cacheable=False,
                        reason_code='full_quality_refinement_exhausted',source_replacement_authorized=False,
                        reason='Original retained: bounded full-file refinement did not meet the quality requirements')
                    save(directory/'selection.json',decision)
                    state.update(state='trials-completed',decision=decision)
        guard()
        if digest(source,guard)!=identity:raise RuntimeError('Layered source content changed')
        save(directory/'status.json',state)
        progress(state['state'],directory=directory,detail='Layered workflow finished; original retained')
        print(json.dumps(state,indent=2));return 0
    except BaseException as exc:
        state.update(state='stopped-original-retained',error=str(exc));save(directory/'status.json',state)
        raise
    finally:
        work.cleanup_terminal_artifacts()


def publication_qualified(result, identity, size, output_hash, profile, mean_floor, p5_floor, *, experimental=False):
    """Fresh full-result qualification, not user permission or a source mutation.

    Explicit research remains copy-only. This Phase 1 qualification covers the
    NVIDIA P5/P7 paths exercised in the isolated application image. Other
    backends can still produce checked copies through the shared evaluator.
    """
    if experimental or profile not in (5,7):return False
    if result.get('settings',{}).get('encoder')!='hevc_nvenc':return False
    if result.get('status')!='validated-research-copy':return False
    candidate_evidence(result,identity,size,profile)
    if not re.fullmatch('[0-9a-f]{64}',output_hash) or result.get('output_sha256')!=output_hash:
        raise ValueError('Full DV output identity changed before qualification')
    checks=result['frame_checks']
    if any(checks.get(k) is not True for k in ('timing_preserved','static_hdr_preserved',
            'frame_picture_preserved','rpu_present_every_frame')):
        raise ValueError('Full DV preservation evidence is incomplete')
    from dv_workflow import score_pass
    if any(not score_pass(result['quality'][k],mean_floor,p5_floor) for k in ('self','candidate')):
        raise ValueError('Full DV quality requirements not met')
    if profile==7:
        layer=result['layer_checks']
        from dv_layer_evidence import profile7_configuration
        profile7_configuration(layer.get('configuration'))
        if (layer.get('scope')!='layer-preservation-only'
                or any(not re.fullmatch('[0-9a-f]{64}',layer.get(k,'')) for k in ('rpu_sha256','enhancement_video_sha256'))):
            raise ValueError('Complete DV enhancement preservation evidence required')
        fallback='compatible_fallback'
        views=result['quality'].get('views',{})
        for kind in ('self','candidate'):
            scores=[views.get(view,{}).get(kind,{}) for view in ('native_dv',fallback)]
            if (any(s.get('frames')!=checks['frames'] or not score_pass(s,mean_floor,p5_floor) for s in scores)
                    or any(result['quality'][kind][metric]!=min(s[metric] for s in scores) for metric in ('mean','p5'))):
                raise ValueError('Full native and fallback DV quality evidence required')
    return True


def reuse_whole_source_candidate(workflow, source, report, decision, *, source_id,
                                savings_mode='fixed',minimum_savings_percent=25,
                                mean_floor=90,p5_floor=90,profile=7):
    """Reuse a complete fresh trial, not a clip or an old history decision.

    Verify source/output hashes again and apply the full-file quality and exact
    savings policy. Missing reusable evidence falls back to ordinary refinement;
    changed files are errors, never permission to skip validation.
    """
    from savings_policy import requirement,meets_requirement
    from dv_workflow import score_pass
    references=report.get('references',[])
    selected=decision.get('selected') or {}
    if decision.get('action')!='encode_copy' or len(references)!=1:return None
    reference=references[0];source=Path(source).resolve(strict=True)
    if (reference.get('whole_source') is not True or reference.get('sha256')!=source_id
            or not reference.get('path') or Path(reference['path']).resolve(strict=True)!=source):return None
    trial=next((t for t in report.get('trials',[]) if t.get('id')==selected.get('id')),None)
    if not trial or len(trial.get('samples',[]))!=1:return None
    sample=trial['samples'][0];result=sample.get('whole_source_result')
    if (not result or sample.get('reference_id')!=reference.get('id')
            or result.get('settings')!=selected.get('settings')
            or not re.fullmatch('[0-9a-f]{64}',result.get('output_sha256',''))):return None
    workflow.guard()
    if digest(source,workflow.guard)!=source_id:raise ValueError('Whole-source trial input changed')
    size=source.stat().st_size
    if reference.get('bytes')!=size or report.get('source_id')!=source_id:
        raise ValueError('Whole-source reference identity is inconsistent')
    candidate_evidence(result,source_id,size,profile)
    if not score_pass(result['quality']['self'],mean_floor,p5_floor):raise ValueError('Whole-source self-check failed')
    if not score_pass(result['quality']['candidate'],mean_floor,p5_floor):return None
    output=Path(result['output'])
    if output.is_symlink() or not output.resolve(strict=True).is_relative_to(Path(workflow.directory).resolve()):
        raise ValueError('Whole-source output escapes the owned run directory')
    if output.resolve()==source or output.stat().st_size!=result['output_bytes'] or digest(output,workflow.guard)!=result['output_sha256']:
        raise ValueError('Whole-source trial output changed')
    policy=requirement(size,savings_mode,minimum_savings_percent)
    saves=meets_requirement(size,result['output_bytes'],policy)
    reused=dict(source_id=source_id,savings_policy=policy,publication_authorized=False,
                reused_whole_source_trial=True,status='validated_copy' if saves else 'savings_target_missed',
                attempts=[dict(settings=result['settings'],status='quality_passed',result=result)])
    if saves:reused['selected']=result
    with (Path(workflow.directory)/'mel-full-refinement.json').open('x',encoding='utf-8') as handle:
        json.dump(reused,handle,indent=2)
    return reused


def refine_full_candidate(workflow, source, settings, *, source_id, playback_verified_codecs,
                          max_attempts=3, savings_mode='fixed', minimum_savings_percent=25,
                          mean_floor=90, p5_floor=90, dovi_tool='dovi_tool', encoder_ffmpeg=None,profile=7):
    """Bounded full-file refinement, never publication or source replacement.

    Only measured quality rejection permits refinement. Structural failures
    propagate: they must not become a cached 'already optimized' decision.
    """
    from auto_optimize import adaptive_candidates
    from savings_policy import requirement, meets_requirement
    from dv_workflow import score_pass
    from job_tracking import progress
    encode,domain=candidate_service(profile)
    if type(max_attempts) is not int or not 1<=max_attempts<=8:
        raise ValueError('Full-file attempt budget must be between 1 and 8')
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=100
           for v in (mean_floor,p5_floor)):
        raise ValueError('Invalid quality floors')
    if settings.get('codec')!='hevc' or settings.get('codec') not in playback_verified_codecs:
        raise ValueError('Full DV codec is not playback-qualified')
    source=Path(source).resolve(strict=True)
    def unchanged():
        workflow.guard()
        if digest(source,workflow.guard)!=source_id:raise ValueError('Full-file source identity changed')
    unchanged()
    size=source.stat().st_size
    policy=requirement(size,savings_mode,minimum_savings_percent)
    report=dict(source_id=source_id,savings_policy=policy,attempts=[],
                publication_authorized=False,status='pending')
    target=Path(workflow.directory)/'mel-full-refinement.json'
    if target.exists():raise ValueError('Full-file refinement report already exists')
    def save():
        with target.open('w',encoding='utf-8') as handle:json.dump(report,handle,indent=2)
    if not policy['possible']:
        report['status']='savings_requirement_unreachable';save();return report
    current=dict(settings)
    measured=dict(trials=[])
    attempted=set()
    for index in range(max_attempts):
        unchanged()
        attempted.add(json.dumps(current,sort_keys=True))
        progress('Full-file quality refinement',index,max_attempts,unit='attempts',
                 detail=f'Attempt {index+1}; quality requirements unchanged')
        attempt=dict(settings=current,status='running')
        report['attempts'].append(attempt);save()
        try:
            result=encode(workflow,source,current,'mel-full-'+str(index),
                                    dovi_tool=dovi_tool,encoder_ffmpeg=encoder_ffmpeg)
            unchanged()
            candidate_evidence(result,source_id,size,profile)
            if not score_pass(result['quality']['self'],mean_floor,p5_floor):
                raise ValueError('Full-file quality self-check failed')
            passed=score_pass(result['quality']['candidate'],mean_floor,p5_floor)
            saves=meets_requirement(size,result['output_bytes'],policy)
        except (OSError,RuntimeError,ValueError,KeyError,TypeError) as exc:
            attempt.update(status='validation_error',error=str(exc))
            report['status']='validation_error';save()
            raise
        attempt.update(status='quality_passed' if passed else 'quality_rejected',result=result)
        if passed:
            report['status']='validated_copy' if saves else 'savings_target_missed'
            if saves:report['selected']=result
            save();return report
        measured['trials'].append(dict(encoder=current['encoder'],codec=current['codec'],settings=current,
            runtime_supported=True,playback_compatible=True,
            samples=[dict(quality=dict(result['quality']['candidate'],passed=False))]))
        options=[dict(current,**candidate) for candidate in adaptive_candidates(measured)]
        options=[candidate for candidate in options if json.dumps(candidate,sort_keys=True) not in attempted]
        # A retry after a quality failure must actually increase requested NVENC
        # quality; preserve rate caps and other source-specific options.
        if current['encoder'].endswith('_nvenc') and 'nvenc_cq' in current:
            options=[c for c in options if c.get('nvenc_cq',999)<current['nvenc_cq']]
        report['status']='quality_retry_budget_exhausted' if index+1==max_attempts else 'quality_refinement_unavailable'
        save()
        if not options:return report
        current=options[0]
    return report


def compare_candidates(workflow, source, candidates, seconds, *, playback_verified_codecs,
                       minimum_savings_percent=25, mean_floor=90, p5_floor=90,
                       dovi_tool='dovi_tool', encoder_ffmpeg=None,profile=7,max_refinements=4):
    """Shared measured selector over source-verified DV references.

    A runtime failure belongs to its candidate; it is not a GPU-family ban or a
    successful size/quality rejection. This function never publishes media.
    """
    from codec_selection import select_candidate, EVALUATION_POLICY
    from dv_workflow import score_pass
    from job_tracking import progress
    from auto_optimize import adaptive_candidates
    encode,domain=candidate_service(profile)
    if type(max_refinements) is not int or not 0<=max_refinements<=8:
        raise ValueError('Sample refinement budget must be between 0 and 8')
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=100
           for v in (mean_floor,p5_floor)):
        raise ValueError('Invalid quality floors')
    if not math.isfinite(minimum_savings_percent) or not 0<=minimum_savings_percent<100:
        raise ValueError('Invalid savings threshold')
    prepared=prepare_references(workflow,source,seconds,dovi_tool=dovi_tool)
    references=prepared['references']
    report=dict(schema='muxmender-codec-trials-v1',source_id=prepared['source_id'],
                source_bytes=prepared['source_bytes'],color_mode='pq',dv_profile={7:'7-layered',5:'5',8:'8-native'}[profile],
                evaluation_policy=EVALUATION_POLICY,references=references,trials=[])
    candidates=list(candidates)
    initial_count=len(candidates)
    completed=0
    for index,settings in enumerate(candidates):
        workflow.guard()
        trial=dict(id='mel-'+str(index),source_id=prepared['source_id'],codec=settings.get('codec'),
                   encoder=settings.get('encoder'),settings=dict(settings),runtime_supported=False,
                   playback_compatible=settings.get('codec') in playback_verified_codecs,samples=[])
        report['trials'].append(trial)
        if not trial['playback_compatible']:
            trial['error']='Codec has not been selected as playback-compatible'
            continue
        for number,reference in enumerate(references):
            workflow.guard()
            path=Path(reference['path'])
            if digest(path,workflow.guard)!=reference['sha256']:raise ValueError('Shared reference changed')
            progress('Comparing Dolby Vision encoding candidates',completed,len(candidates)*len(references),
                     unit='candidate scenes',detail=f'Candidate {index+1}, scene {number+1}')
            sample=dict(reference_id=reference['id'],encode_completed=False)
            trial['samples'].append(sample)
            try:
                result=encode(workflow,path,settings,f'mel-{index}-scene-{number}',
                                        dovi_tool=dovi_tool,encoder_ffmpeg=encoder_ffmpeg)
                candidate_evidence(result,reference['sha256'],reference['bytes'],profile)
                self_pass=score_pass(result['quality']['self'],mean_floor,p5_floor)
                passed=self_pass and score_pass(result['quality']['candidate'],mean_floor,p5_floor)
                if not self_pass:raise ValueError('DV quality self-check failed')
                sample.update(output=result.get('output'),bytes=result['output_bytes'],encode_completed=True,quality_pass=passed,
                              preservation_pass=True,decode_pass=True,hdr_preservation_pass=True,
                              quality_method=('Native DV and HDR10 fallback renders plus complete enhancement-layer and frame validation' if profile==7
                                              else 'Native DV render plus complete RPU and frame validation'),
                              enhancement_type=('FEL' if requires_fel_reconstruction(result.get('layer_checks',{}).get('enhancement_types')) else 'MEL') if profile==7 else None,
                              quality=dict(result['quality']['candidate'],passed=passed,domain=result['quality']['domain']))
                if reference.get('whole_source') and path.resolve()==Path(source).resolve():
                    sample['whole_source_result']=result
                trial['runtime_supported']=True
            except (OSError,RuntimeError,ValueError) as exc:
                workflow.guard()
                sample['error']=str(exc)
            completed+=1
            with (Path(workflow.directory)/'mel-trials.json').open('w',encoding='utf-8') as handle:
                json.dump(report,handle,indent=2)
        # Finish the initial matrix before refining. Only complete, measured
        # quality failures justify a retry; runtime/metadata errors never do.
        # Reuse the ordinary search and the same immutable references/floors.
        if index==len(candidates)-1 and len(candidates)-initial_count<max_refinements:
            current=select_candidate(report,minimum_savings_percent)
            rejected={row['id'] for row in current['candidates'] if row['assessment']=='quality_rejected'}
            measured=[t for t in report['trials'] if t['id'] in rejected
                      and not t.get('error') and not any(s.get('error') for s in t['samples'])]
            if current['action']!='encode_copy' and measured:
                attempted={json.dumps(c,sort_keys=True) for c in candidates}
                for option in adaptive_candidates(dict(trials=measured)):
                    parent=next(t for t in reversed(measured) if t['encoder']==option['encoder'])
                    candidate=dict(parent['settings'],**option)
                    if json.dumps(candidate,sort_keys=True) not in attempted:
                        candidates.append(candidate)
                        report['sample_refinements']=len(candidates)-initial_count
                        break
    if digest(Path(source),workflow.guard)!=prepared['source_id']:raise ValueError('Source changed during MEL comparison')
    decision=select_candidate(report,minimum_savings_percent)
    with (Path(workflow.directory)/'mel-selection.json').open('x',encoding='utf-8') as handle:
        json.dump(decision,handle,indent=2)
    return report,decision


def reference_rpu_coverage(workflow, path, label, dovi_tool):
    """Require one displayed picture per exported RPU before testing a cut.

    Open-GOP cuts can retain RPU for non-displayed leading pictures. Never
    delete those records heuristically: choose another start or use the source.
    """
    from dv_full_file import rpu_digest
    directory=Path(workflow.directory)/label;directory.mkdir()
    work=Workflow(workflow.args,directory,workflow.guard)
    duration=float(work.probe(path)['format']['duration'])
    raw=directory/'reference.hevc';binary=directory/'reference.rpu';export=directory/'rpu.json'
    work.execute([work.args.ffmpeg,'-v','error','-nostdin','-n','-i',str(path),'-map','0:V:0',
                  '-c','copy','-bsf:v','hevc_mp4toannexb','-f','hevc',str(raw)],'extract-reference',duration)
    work.execute([dovi_tool,'extract-rpu','-i',str(raw),'-o',str(binary)],'extract-rpu',duration)
    work.execute([dovi_tool,'export','-i',str(binary),'-d','all='+str(export)],'export-rpu',duration)
    def guard():work.guard()
    guard.phase='Checking reference picture and RPU coverage';guard.duration=duration;guard.allow_hdr10plus=True
    evidence=directory/'frames.json';frame_evidence(work.args.ffprobe,path,evidence,guard)
    pictures=sum(1 for _ in frames(evidence,True));rpus=rpu_digest(export,guard)[0]
    if min(pictures,rpus)<=0:raise ValueError('Reference lacks complete DV picture evidence')
    result=dict(displayed_frames=pictures,rpu_records=rpus,complete=pictures==rpus)
    with (directory/'coverage.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
    return result


def prepare_references(workflow, source, seconds, *, dovi_tool='dovi_tool'):
    """Use shared source-verified GOP references; whole original for short input.

    The keyframe service proves compressed-packet and decoded-picture identity;
    references are never re-encoded ground truth. Full MEL layer/frame validation
    still runs for each candidate after this sampling step.
    """
    from auto_optimize import reference_plan
    from reference_sampling import recover_reference
    source=Path(source).resolve(strict=True)
    workflow.guard()
    metadata=workflow.probe(source)
    plan=reference_plan(float(metadata['format']['duration']),seconds)
    identity=digest(source,workflow.guard)
    size=source.stat().st_size
    references=[]
    actual_windows=set()
    rejected=[]
    for index,position in enumerate(plan['positions']):
        workflow.guard()
        if plan['whole_source']:
            path=source
            proof=dict(method='whole-source',source_sha256=identity)
        else:
            excluded=[]
            requested=position
            recovery_error=None
            for attempt in range(3):
                label=f'mel-reference-{index}-{attempt}'
                try:
                    path,proof=recover_reference(workflow,source,metadata,requested,plan['seconds'],label,
                                                 excluded_starts=excluded)
                except ValueError as exc:
                    recovery_error=str(exc)
                    rejected.append(dict(requested_start=position,error=str(exc)))
                    break
                coverage=reference_rpu_coverage(workflow,path,label+'-coverage',dovi_tool)
                proof['rpu_coverage']=coverage
                if coverage['complete']:break
                rejected.append(dict(requested_start=position,source_evidence=proof))
                excluded.append(proof['plan']['keyframe_pts'])
                hints=reference_idr_hints(workflow,path,label,proof)
                requested=next((hint for hint in hints if hint not in {Fraction(x) for x in excluded}),position)
            else:
                coverage=dict(complete=False)
            if recovery_error is not None or (excluded and (not coverage['complete'] or len(excluded)==3)):
                # Sampling failure is not a format rejection. Complete-source
                # evaluation avoids cutting its dependency/metadata structure.
                references=[dict(id='0',path=str(source),sha256=identity,bytes=size,whole_source=True,
                    requested_start=0,source_evidence=dict(method='whole-source',source_sha256=identity))]
                plan=dict(plan,whole_source=True,positions=[0],fallback_reason=(
                    'reference_recovery_failed' if recovery_error is not None else 'open_gop_rpu_picture_coverage'))
                break
            window=(proof['plan']['keyframe_pts'],proof['plan']['end_keyframe_pts'])
            if window in actual_windows:raise ValueError('Sampling repeated the same source GOP window')
            actual_windows.add(window)
        references.append(dict(id=str(index),path=str(path),sha256=digest(path,workflow.guard),
                               bytes=path.stat().st_size,whole_source=plan['whole_source'],
                               requested_start=position,source_evidence=proof))
    if digest(source,workflow.guard)!=identity:raise ValueError('Source changed during reference preparation')
    result=dict(source_id=identity,source_bytes=size,plan=plan,references=references,rejected_boundaries=rejected)
    with (Path(workflow.directory)/'mel-references.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2)
    return result


def idr_positions(bitstream, packets, shift, guard=lambda:None):
    """Sampling hints only: original packet/picture/timing proof remains required.

    Match one primary first-slice picture to each copied packet before using its
    time. Multi-slice frames count once; EL pictures and non-VCL NALs do not.
    """
    from hevc_inventory import Inventory
    inventory=Inventory(track_pictures=True)
    with Path(bitstream).open('rb') as stream:
        while block:=stream.read(1024*1024):
            guard();inventory.feed(block)
    inventory.finish()
    if len(inventory.picture_types)!=len(packets):return []
    offset=Fraction(shift)
    result=[]
    for kind,packet in zip(inventory.picture_types,packets):
        if kind not in (19,20) or 'K' not in packet.get('flags','') or 'D' in packet.get('flags',''):continue
        if packet.get('pts_time') in (None,'N/A'):continue
        point=Fraction(packet['pts_time'])-offset
        if point>=0:result.append(point)
    return result


def reference_idr_hints(workflow,path,label,proof):
    packets=json.loads((Path(workflow.directory)/(label+'-sample-packets.json')).read_text())['packets']
    index=main_video(workflow.probe(path))['index']
    return idr_positions(Path(workflow.directory)/(label+'-coverage')/'reference.hevc',
        [p for p in packets if p['stream_index']==index],proof['common_timestamp_shift'],workflow.guard)


def encode_candidate(workflow, source, settings, label, *, dovi_tool='dovi_tool', encoder_ffmpeg=None):
    return _encode_layered(workflow,source,settings,label,dovi_tool=dovi_tool,encoder_ffmpeg=encoder_ffmpeg)


def encode_fel_research_candidate(workflow, source, settings, label, *, dovi_tool='dovi_tool', encoder_ffmpeg=None):
    """Explicit diagnostic copy only; never eligible for automatic selection.

    Retains original EL/RPU while re-encoding BL. Its HDR10 fallback metric is
    not reconstructed FEL quality evidence, even if every fallback score passes.
    """
    return _encode_layered(workflow,source,settings,label,dovi_tool=dovi_tool,
                           encoder_ffmpeg=encoder_ffmpeg,fel_research=True)


def _encode_layered(workflow, source, settings, label, *, dovi_tool='dovi_tool', encoder_ffmpeg=None,fel_research=False):
    if not isinstance(label,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',label):
        raise ValueError('MEL candidate label must be a simple name')
    if settings.get('codec')!='hevc':
        raise ValueError('Retained HEVC enhancement layer requires an HEVC base')
    source=Path(source).resolve(strict=True)
    directory=Path(workflow.directory)/label
    directory.mkdir()
    args=copy(workflow.args)
    args.source=source
    work=Workflow(args,directory,workflow.guard)
    before=work.probe(source)
    video=main_video(before)
    duration=float(before['format']['duration'])
    rate=Fraction(video['avg_frame_rate'])
    if rate<=0:raise ValueError('MEL fallback frame rate is unresolved')
    identity=digest(source,work.guard)

    def frame_guard():work.guard()
    frame_guard.phase='Checking complete layered frames'
    frame_guard.duration=duration
    frame_guard.allow_hdr10plus=True
    original=extract_layers(work,source,'original-layers',dovi_tool=dovi_tool)
    is_fel=requires_fel_reconstruction(original['enhancement_types'])
    if fel_research and not is_fel:
        raise ValueError('Explicit FEL research requires a complete FEL inventory')
    if is_fel and not fel_research:
        from dv_fel_quality import renderer_plugin
        args.fel_render_plugin=renderer_plugin(args)
    source_frames=directory/'source-frames.json'
    frame_evidence(args.ffprobe,source,source_frames,frame_guard)
    clock=directory/'timestamps.txt'
    count=write_decoded_timestamps((dict(f,pts_time=f['best_effort_timestamp_time'])
                                   for f in frames(source_frames,True)),clock,work.guard,include_end=True)
    if original['frames']!=count:raise ValueError('Source RPU and decoded picture coverage differ')
    base=directory/'base.mkv'
    work.execute(timestamped_video_command(args.ffmpeg,original['base'],base,str(rate),timestamps=clock),
                 'materialize-base',duration)
    base_data=work.probe(base)
    info=mm.probe(base,args.ffprobe)
    if info.dolby_vision:raise ValueError('Separated base unexpectedly retains Dolby Vision signaling')
    # Tool builds can differ independently of GPU capability (e.g. a newer
    # demuxer built against NVENC headers newer than the host driver). The
    # caller may explicitly choose a qualified encoder executable; never
    # silently change drivers, vendor, codec or use a CPU fallback here.
    encoding_args=copy(args)
    encoding_args.source=base
    encoding_args.ffmpeg=encoder_ffmpeg or args.ffmpeg
    encoding_directory=directory/'base-encoding';encoding_directory.mkdir()
    encoder=Workflow(encoding_args,encoding_directory,work.guard)
    encoder.hdr_mode='pq'
    reference=encoder.frame_file(base,'base-reference',base_data['format'])
    encoded=encoding_directory/'encoded-base.mkv'
    encoder.encode_preserving_color(base,encoded,settings,info,base_data,'encode-base',duration)
    if encoder.validate(base,encoded,base_data,'hevc','validate-base',reference)!=count:
        raise ValueError('Base picture count changed')
    raw=directory/'encoded-base.hevc'
    work.execute([args.ffmpeg,'-v','error','-nostdin','-n','-i',str(encoded),'-map','0:V:0','-c','copy',
                  '-bsf:v','hevc_mp4toannexb','-f','hevc',str(raw)],'extract-encoded-base',duration)
    combined=directory/'before-rpu-alignment.hevc'
    work.execute([dovi_tool,'mux','--bl',str(raw),'--el',original['enhancement'],'-o',str(combined)],
                 'restore-enhancement',duration)
    # A new base GOP structure can reorder RPU associated with copied EL access
    # units. Reinject the complete original display-ordered RPU sequence against
    # the new base, then independently verify every RPU and unchanged EL video.
    layered=directory/'layered.hevc'
    work.execute([dovi_tool,'inject-rpu','-i',str(combined),'-r',original['rpu'],'-o',str(layered)],
                 'restore-rpu-picture-alignment',duration)
    packaged=directory/'video.mkv'
    work.execute(timestamped_video_command(args.ffmpeg,layered,packaged,str(rate),timestamps=clock,
                 preserve_enhancement=True),'timestamp-layered',duration)
    output=directory/'candidate.mkv'
    work.execute(preserved_tracks_command(args.ffmpeg,packaged,source,output,before['streams']),
                 'restore-source-tracks',duration)
    final=extract_layers(work,output,'output-layers',dovi_tool=dovi_tool)
    output_frames=directory/'output-frames.json'
    frame_evidence(args.ffprobe,output,output_frames,frame_guard)
    checks=compare_frames(source_frames,output_frames,frame_guard)
    layers=layer_preservation_evidence(original['enhancement_video'],final['enhancement_video'],
        original['rpu_export'],final['rpu_export'],original['configuration'],final['configuration'],
        checks['frames'],guard=work.guard)
    after=work.probe(output)
    work.check_metadata(source,output,before,after,'hevc','final-metadata',verified_frame_count=count,
                        verified_hdr_frames=True,verified_variable_timing=True)
    work.validate_copied_tracks(source,output,before,after,'final-tracks')
    # Main video already has full strict frame evidence. Decode secondary video
    # and every audio track; copied packet identity is not a decode check.
    primary=main_video(after)['index']
    indices=[s['index'] for s in after['streams'] if s['codec_type'] in ('video','audio') and s['index']!=primary]
    if indices:
        work.execute([args.ffmpeg,'-v','error','-xerror','-nostdin','-threads','2','-i',str(output),
                      *[v for i in indices for v in ('-map','0:'+str(i))],'-f','null','-'],
                     'decode-copied-streams',duration,strict_decode=True)
    fallback_quality=measure_prefix_quality(args.ffmpeg,source,output,directory,count,str(rate),work.guard)
    if is_fel:
        from dv_fel_quality import measure_research_quality
        quality=measure_research_quality(work,original,final,layers,count,str(rate),fallback_quality)
    else:
        from dv_render import measure_native_quality, combine_quality_views
        quality=measure_native_quality(work,source,output,count,str(rate),'native-quality',mel_evidence=layers)
        quality=combine_quality_views(quality,fallback_quality)
    if digest(source,work.guard)!=identity:raise ValueError('Source content changed during MEL candidate')
    original_bytes=source.stat().st_size
    output_bytes=output.stat().st_size
    result=dict(source=str(source),source_sha256=identity,output=str(output),source_bytes=original_bytes,
                output_sha256=digest(output,work.guard),
                output_bytes=output_bytes,saved_percent=100*(1-output_bytes/original_bytes),
                frame_checks=checks,layer_checks=layers,quality=quality,settings=dict(settings),
                copied_tracks_preserved=True,source_unchanged=True,publication_authorized=False,
                tools=dict(ffmpeg=args.ffmpeg,ffprobe=args.ffprobe,encoder_ffmpeg=encoding_args.ffmpeg),
                status='unqualified-fel-research-copy' if fel_research else
                       'validated-research-copy' if quality['candidate']['passed'] and output_bytes<original_bytes
                       else 'rejected-research-copy')
    with (directory/'validation.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
    return result
