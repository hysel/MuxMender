"""Profile 8.1 shared-workflow integration qualification, separate copies only.

Reuse the proven DV sample/full preservation services and ordinary candidate
selector. This opt-in adapter cannot authorize production publication yet.
"""
import json
import math
import os
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
import uuid

import dv_preservation_test as dv
import dv_full_file as full
import muxmender as mm
from codec_selection import select_candidate,EVALUATION_POLICY
from dvd_av1_batch import save
from job_tracking import progress,workflow_stage
from task_progress import digest


def score_pass(score,mean,p5):
    return (score.get('passed') is True and
            all(type(score.get(k)) in (int,float) and math.isfinite(score[k])
                for k in ('mean','p5')) and score['mean']>=mean and score['p5']>=p5)


def sample_evidence(report,source,start,seconds,combined,mean,p5):
    if (report.get('source')!=str(source) or report.get('requested_start')!=start or
            report.get('requested_seconds')!=seconds or
            report.get('status')!='verified-structure-awaiting-visual-review' or
            report.get('original_stat_unchanged') is not True):
        raise ValueError('Incomplete or mismatched DV sample preservation')
    if combined and report.get('hdr10plus_content_and_frame_order_unchanged') is not True:
        raise ValueError('Combined dynamic metadata evidence is missing')
    if any(report.get(k) is not True for k in ('rpu_content_and_frame_order_unchanged',
                                               'audio_subtitle_packets_unchanged',
                                               'static_hdr_within_one_quantization_unit')):
        raise ValueError('DV RPU, track or static metadata evidence is missing')
    for key in ('original_video_bytes','output_video_bytes','frames'):
        if type(report.get(key)) is not int or report[key]<=0:raise ValueError('Invalid DV sample '+key)
    identity=report.get('reference_sha256','')
    if len(identity)!=64 or any(c not in '0123456789abcdef' for c in identity):
        raise ValueError('Missing shared reference identity')
    quality=report.get('quality',{})
    if any(quality.get(k,{}).get('frames')!=report['frames'] for k in ('self','candidate')):
        raise ValueError('DV quality frame count does not match preserved sample')
    if quality.get('domain')!='hdr-common-render-v1' or not score_pass(quality.get('self',{}),mean,p5):
        raise ValueError('DV quality self-check or domain failed')
    passed=score_pass(quality.get('candidate',{}),mean,p5)
    return dict(reference_id=str(start),bytes=report['output_video_bytes'],encode_completed=True,
                quality_pass=passed,preservation_pass=True,decode_pass=True,hdr_preservation_pass=True,
                quality_method='VMAF HDR10 base-layer render plus independent DV/HDR preservation',
                quality=dict(quality['candidate'],passed=passed,domain=quality['domain']))


def verified_full(report,source,combined):
    if (report.get('status')!='verified-full-file-awaiting-playback' or
            report.get('source')!=str(source) or report.get('original_stat_unchanged') is not True):
        raise ValueError('Complete DV validation did not pass')
    checks=report.get('decoded_frame_checks',{})
    if type(report.get('frames')) is not int or report['frames']<=0 or checks.get('frames')!=report['frames']:
        raise ValueError('Full DV frame evidence is incomplete')
    keys=['timing_preserved','static_hdr_preserved','frame_picture_preserved','rpu_present_every_frame']
    if combined:keys.append('hdr10plus_preserved')
    if any(checks.get(k) is not True for k in keys):raise ValueError('Full DV metadata evidence is incomplete')
    if (not report.get('rpu_content_digest') or report.get('chapters_unchanged') is not True or
            not (report.get('audio_subtitle_packets_unchanged') is True or
                 (report.get('packet_payloads_order_and_pts_unchanged') is True and report.get('aac_duration_rounding'))) or
            not report.get('final_decode_evidence')):
        raise ValueError('Full DV track, decode or RPU evidence is incomplete')


def run(args,source,root,data,baseline):
    from auto_optimize import Workflow,sample_positions,sampling_window
    from amd_av1_batch import fingerprint
    if args.hardware not in ('auto','nvidia'):
        raise ValueError('This integration qualification currently uses the NVIDIA preservation path')
    if 'hevc' not in args.playback_verified_codecs:
        raise ValueError('DV Profile 8.1 integration requires HEVC playback support')
    if getattr(args,'nvenc_maxrate_mbps',None) is not None:
        raise ValueError('DV integration has not qualified a peak-rate override')
    info=mm.probe(source,args.ffprobe)
    dv.require_candidate(info)  # Profile 5/7 and enhancement layers must not enter this path.
    seconds=min(30,sampling_window(info.duration_seconds,args.seconds))
    positions=sample_positions(info.duration_seconds,seconds)
    cqs=getattr(args,'hevc_nvenc_cq',None) or [28,29,30,32]
    plan=dict(source=str(source),positions=positions,seconds=seconds,cqs=cqs,
              minimum_savings_percent=args.minimum_savings_percent,
              mean_floor=args.vmaf_mean,p5_floor=args.vmaf_p5,
              source_deletion=False,publication_authorized=False,
              evaluation_policy=EVALUATION_POLICY,route='dv81-integration-qualification',
              quality_domain='hdr-common-render-v1')
    if not args.execute:
        print(json.dumps(dict(dry_run=True,plan=plan),indent=2));return 0
    for tool in (args.ffmpeg,args.ffprobe,'dovi_tool','hdr10plus_tool'):
        if not shutil.which(tool):raise ValueError('Missing DV integration dependency: '+tool)
    # Sampled absence is not whole-file proof: the ordinary full-frame service
    # rejects unexpected HDR10+ before encoding; it never silently discards it.
    import hdr_inspection
    video=next(s for s in data['streams'] if s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic'))
    inspection=hdr_inspection.inspect(args.ffprobe,source,video,info.duration_seconds)
    combined=any('2094-40' in name or 'hdr10+' in name for name in inspection['side_data_types'])
    plan['combined_hdr10plus']=combined
    root.mkdir(parents=True,exist_ok=True)
    directory=root/('auto-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir()
    state=dict(state='running',source=str(source),original_retained=True,publication_authorized=False)
    save(directory/'plan.json',plan);save(directory/'status.json',state)

    def guard():
        if (directory/'STOP').exists() or (root/'STOP').exists():raise KeyboardInterrupt('STOP requested')
        if fingerprint(source)!=baseline:raise RuntimeError('Source changed during DV integration')
        if shutil.disk_usage(directory).free<args.min_free_gib*1024**3:raise RuntimeError('Output reserve exhausted')

    workflow=Workflow(args,directory,guard)
    try:
        guard();source_hash=digest(source,guard)
        workflow.preflight_source(source,data,source_hash)
        report=dict(schema='muxmender-codec-trials-v1',source_id=source_hash,color_mode='pq',
                    dv_profile='8.1',references=[],trials=[])
        identities={}
        workflow_stage('compare')
        for cq in cqs:
            trial=dict(id='dv81-nvenc-cq'+str(cq),source_id=source_hash,codec='hevc',encoder='hevc_nvenc',
                       settings=dict(codec='hevc',encoder='hevc_nvenc',nvenc_cq=cq,combined=combined),
                       playback_compatible=True,runtime_supported=False,samples=[])
            report['trials'].append(trial)
            for number,start in enumerate(positions):
                guard();scene=directory/(trial['id']+'-scene'+str(number));scene.mkdir()
                progress('Testing Dolby Vision candidate',detail=f'CQ {cq}, scene {number+1} of 3')
                options=SimpleNamespace(source=source,execute=True,experimental_nvidia=True,
                    experimental_intel=False,experimental_hdr10plus=combined,nvenc_cq=cq,
                    seconds=seconds,start=start,work_dir=scene,measure_quality=True,
                    minimum_savings_percent=args.minimum_savings_percent,ffmpeg=args.ffmpeg,
                    ffprobe=args.ffprobe,dovi_tool='dovi_tool',source_guard=guard)
                code=dv.run(options)
                files=list(scene.glob('dv81-*/validation.json'))
                if code or len(files)!=1:raise RuntimeError('DV scene failed; see retained validation report')
                evidence=json.loads(files[0].read_text())
                sample=sample_evidence(evidence,source,start,seconds,combined,args.vmaf_mean,args.vmaf_p5)
                identity=(evidence['reference_sha256'],evidence['original_video_bytes'],evidence['frames'])
                if start in identities and identities[start]!=identity:raise ValueError('DV candidates used different reference samples')
                if start not in identities:
                    identities[start]=identity
                    report['references'].append(dict(id=str(start),bytes=identity[1],sha256=identity[0]))
                trial['samples'].append(sample);trial['runtime_supported']=True
                save(directory/'trials.json',report)
        decision=select_candidate(report,args.minimum_savings_percent)
        save(directory/'selection.json',decision)
        guard()
        if digest(source,guard)!=source_hash:raise RuntimeError('Source content changed')
        if not args.encode_best or decision['action']!='encode_copy':
            state.update(state='trials-completed',decision=decision)
        else:
            workflow_stage('encode')
            work=directory/'full-preservation';work.mkdir()
            options=SimpleNamespace(source=source,execute=True,work_dir=work,ffmpeg=args.ffmpeg,
                ffprobe=args.ffprobe,dovi_tool='dovi_tool',experimental_nvidia=True,experimental_intel=False,
                experimental_hdr10plus=combined,nvenc_cq=decision['selected']['settings']['nvenc_cq'],
                qp_i=18,qp_p=20,min_savings=args.minimum_savings_percent,video_only_folder=False,source_guard=guard)
            code=full.run(options)
            records=list(work.glob('dv-full-*/validation.json'))
            if not code and not records:
                # The existing full service may reject its additional bounded
                # preflight before a full run directory is created. A measured
                # keep is not an encoder crash, and never a validation success.
                preflights=list(work.glob('nvidia-size-preflight-*/dv81-*/validation.json'))
                if len(preflights)==1:
                    preflight=json.loads(preflights[0].read_text())
                    optimization=preflight.get('optimization_decision',{})
                    if (preflight.get('source')==str(source) and preflight.get('status')=='skipped'
                            and preflight.get('original_stat_unchanged') is True
                            and optimization.get('eligible') is False):
                        guard()
                        if digest(source,guard)!=source_hash:raise RuntimeError('Source hash changed')
                        decision=dict(decision,action='keep_original',selected=None,cacheable=False,
                                      reason_code='dv_full_preflight_rejected',reason=optimization['reason'])
                        save(directory/'selection.json',decision)
                        state.update(state='trials-completed',decision=decision)
                        save(directory/'status.json',state)
                        workflow.cleanup_terminal_artifacts()
                        return 0
            if code or len(records)!=1:raise RuntimeError('DV full preservation did not produce a complete validation report')
            result=json.loads(records[0].read_text())
            guard()
            if digest(source,guard)!=source_hash:raise RuntimeError('Source hash changed')
            if result.get('status')=='skipped':
                if result.get('optimization_decision',{}).get('eligible') is not False:
                    raise RuntimeError('DV skip lacks measured size rejection evidence')
                state.update(state='full-output-rejected-insufficient-savings',
                             full_validation_performed=False,decision=result.get('optimization_decision'))
            else:
                workflow_stage('validate');verified_full(result,source,combined)
                output=Path(result['output'])
                if output.is_symlink() or not output.resolve(strict=True).is_relative_to(work.resolve()):
                    raise ValueError('DV output escapes owned work directory')
                if digest(source,guard)!=source_hash:raise RuntimeError('Source hash changed')
                actual=100*(1-output.stat().st_size/baseline['size'])
                if output.stat().st_size>=baseline['size'] or actual<args.minimum_savings_percent:
                    raise ValueError('DV full output missed selected savings threshold')
                # The ordinary publisher requires the output directly in auto-*.
                # Hardlink within owned scratch avoids a second large disk copy.
                final=directory/'full-hevc.mkv';os.link(output,final)
                state.update(state='validated-copy-awaiting-playback',output=str(final),saved_percent=actual,
                             source_sha256=source_hash,output_sha256=digest(final,guard),
                             integration_qualification_required=True)
        save(directory/'status.json',state)
        if state['state']=='full-output-rejected-insufficient-savings' or (
                state['state']=='trials-completed' and decision['action']=='keep_original'):
            workflow.cleanup_terminal_artifacts()
        print(json.dumps(state,indent=2));return 0
    except BaseException as exc:
        state.update(state='stopped-original-retained',error=str(exc));save(directory/'status.json',state)
        # Keep failed integration evidence for diagnosis; no source cleanup.
        raise
