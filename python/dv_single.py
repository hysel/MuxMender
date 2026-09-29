"""Single-layer DV candidate encoding with native-render quality verification.

This service produces evidence and a separate copy, never publication approval.
It preserves the encoded color-domain samples (no tone mapping during encoding).
"""
from copy import copy
from fractions import Fraction
from pathlib import Path
import json
import re
from auto_optimize import Workflow,encode_command,main_video
from dv_render import single_layer_configuration,measure_native_quality
from dv_full_file import frame_evidence,frames,compare_frames,rpu_digest,timestamped_video_command
from hdr10plus_preserve import write_decoded_timestamps,preserved_tracks_command
from task_progress import digest
import muxmender as mm


def encode_candidate(workflow, source, settings, label, *, dovi_tool='dovi_tool',encoder_ffmpeg=None,device=None):
    if not isinstance(label,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',label):
        raise ValueError('DV candidate label must be a simple name')
    if settings.get('codec')!='hevc':raise ValueError('This single-layer RPU service requires HEVC')
    source=Path(source).resolve(strict=True)
    before=workflow.probe(source);configuration=single_layer_configuration(before)
    directory=Path(workflow.directory)/label;directory.mkdir()
    args=copy(workflow.args);args.source=source
    work=Workflow(args,directory,workflow.guard)
    identity=digest(source,work.guard)
    duration=float(before['format']['duration']);rate=str(Fraction(main_video(before)['avg_frame_rate']))
    def guard():work.guard()
    guard.phase='Checking complete single-layer DV frames';guard.duration=duration;guard.allow_hdr10plus=True
    source_frames=directory/'source-frames.json';frame_evidence(args.ffprobe,source,source_frames,guard)
    clock=directory/'timestamps.txt'
    count=write_decoded_timestamps((dict(f,pts_time=f['best_effort_timestamp_time']) for f in frames(source_frames,True)),
                                   clock,guard,include_end=True)
    def raw(path,label):
        output=directory/(label+'.hevc')
        work.execute([args.ffmpeg,'-v','error','-nostdin','-n','-i',str(path),'-map','0:V:0','-c','copy',
            '-bsf:v','hevc_mp4toannexb','-f','hevc',str(output)],label,duration)
        return output
    def rpu(path,label):
        binary=directory/(label+'.rpu');export=directory/(label+'.json')
        work.execute([dovi_tool,'extract-rpu','-i',str(path),'-o',str(binary)],label+'-extract',duration)
        work.execute([dovi_tool,'export','-i',str(binary),'-d','all='+str(export)],label+'-export',duration)
        return binary,rpu_digest(export,guard)
    original_raw=raw(source,'source-bitstream')
    original_rpu,original_evidence=rpu(original_raw,'source-rpu')
    if original_evidence[0]!=count:raise ValueError('Source RPU count differs from decoded frames')
    encoded=directory/'encoded.mkv'
    command=encode_command(encoder_ffmpeg or args.ffmpeg,source,encoded,settings,mm.probe(source,args.ffprobe),before['streams'])
    work.execute(work.preserve_covers(command,source,before,'encode'),'encode-single-layer',duration)
    encoded_raw=raw(encoded,'encoded-bitstream')
    restored=directory/'restored.hevc'
    work.execute([dovi_tool,'inject-rpu','-i',str(encoded_raw),'-r',str(original_rpu),'-o',str(restored)],'restore-rpu',duration)
    _,restored_evidence=rpu(restored,'restored-rpu')
    if restored_evidence!=original_evidence:raise ValueError('Single-layer RPU sequence changed')
    video=directory/'video.mkv'
    work.execute(timestamped_video_command(args.ffmpeg,restored,video,rate,timestamps=clock),'timestamp-video',duration)
    output=directory/'candidate.mkv'
    work.execute(preserved_tracks_command(args.ffmpeg,video,source,output,before['streams']),'restore-tracks',duration)
    after=work.probe(output)
    if single_layer_configuration(after)!=configuration:raise ValueError('Single-layer DV configuration changed')
    final_raw=raw(output,'final-bitstream');_,final_evidence=rpu(final_raw,'final-rpu')
    if final_evidence!=original_evidence:raise ValueError('Final mux changed RPU sequence')
    candidate_frames=directory/'candidate-frames.json';frame_evidence(args.ffprobe,output,candidate_frames,guard)
    checks=compare_frames(source_frames,candidate_frames,guard)
    work.check_metadata(source,output,before,after,'hevc','final-metadata',verified_frame_count=count,
                        verified_hdr_frames=True,verified_variable_timing=True)
    work.validate_copied_tracks(source,output,before,after,'final-tracks')
    primary=main_video(after)['index']
    indices=[s['index'] for s in after['streams'] if s['codec_type'] in ('video','audio') and s['index']!=primary]
    if indices:
        work.execute([args.ffmpeg,'-v','error','-xerror','-nostdin','-threads','2','-i',str(output),
            *[v for i in indices for v in ('-map','0:'+str(i))],'-f','null','-'],'decode-copied-tracks',duration,strict_decode=True)
    quality=measure_native_quality(work,source,output,count,rate,'native-quality',device=device)
    if configuration['dv_profile']==8:
        from hdr_auto import measure_prefix_quality
        from dv_render import combine_quality_views
        fallback=measure_prefix_quality(args.ffmpeg,source,output,directory,count,rate,guard)
        quality=combine_quality_views(quality,fallback)
    if digest(source,guard)!=identity:raise ValueError('Source content changed during single-layer candidate')
    original_bytes=source.stat().st_size;output_bytes=output.stat().st_size
    result=dict(source=str(source),source_sha256=identity,output=str(output),source_bytes=original_bytes,
        output_sha256=digest(output,work.guard),
        output_bytes=output_bytes,saved_percent=100*(1-output_bytes/original_bytes),frame_checks=checks,
        rpu_frames=count,rpu_digest=final_evidence[1],configuration=configuration,quality=quality,
        copied_tracks_preserved=True,source_unchanged=True,publication_authorized=False,settings=dict(settings),
        status='validated-research-copy' if quality['candidate']['passed'] and output_bytes<original_bytes else 'rejected-research-copy')
    with (directory/'validation.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
    return result
