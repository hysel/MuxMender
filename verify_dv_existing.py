"""Verify a retained NVIDIA DV full-file output without encoding or modifying media."""
import argparse
import json
from pathlib import Path
import time
import uuid

import dv_full_file as full
import dv_preservation_test as dv
import dv_nvidia_validation as audit
import validate_nvidia as nv
import native_pipeline as np
import muxmender as mm
import job_tracking as jobs
from streaming_pipeline import chapter_summary
from mux_integrity import verify_startup_interleaving
from optimization_acceptance import savings_decision


def main(parent):
    parent = parent.resolve(strict=True)
    previous = json.loads((parent/'validation.json').read_text(encoding='utf-8'))
    if previous.get('encoder_settings',{}).get('encoder') != 'hevc_nvenc' or not previous.get('original_stat_unchanged'):
        raise ValueError('Requires a retained NVIDIA run with unchanged-source evidence')
    source, output = Path(previous['source']), parent/'episode-dolby-vision.mkv'
    directory = parent/('verification-'+time.strftime('%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir()
    guard = dv.NvidiaSampleGuard(directory, reserve=2*1024**3)
    initial = (source.stat().st_size, source.stat().st_mtime_ns)
    report = dict(status='running',source=str(source),output=str(output),parent_run=str(parent),commands=[],
                  scope='Full NVIDIA Profile 8.1 preservation verification; playback review separate')
    ffmpeg, ffprobe = nv.find_tool('ffmpeg'), nv.find_tool('ffprobe')
    dovi = str(Path('tools/dovi_tool-2.3.3/dovi_tool.exe').resolve())
    duration = 0.0
    ff = [ffmpeg,'-hide_banner','-nostdin','-n']
    def stage(command,label,percent):
        guard.phase=label; guard.status(percent); guard()
        report['commands'].append([str(c) for c in command])
        print(label,flush=True)
        return np.stage([str(c) for c in command],duration,timeout=3600,stall=0,guard=guard)
    try:
        decision=savings_decision(source.stat().st_size,output.stat().st_size)
        report['optimization_decision']=decision
        if not decision['eligible']:
            report.update(status='skipped',error=decision['reason'],publication_allowed=False)
            print('SKIPPED: output does not reduce size; no acceptance or publication.',flush=True)
            return 0
        guard.phase='Verify original tracks and timestamps'; guard.status(0)
        before, after = mm.probe(source,ffprobe), mm.probe(output,ffprobe)
        duration = before.duration_seconds
        dv.require_candidate(before); dv.require_candidate(after)
        for field in ('width','height','bit_depth','pixel_format','color_primaries','color_transfer','color_space','color_range'):
            if getattr(before,field) != getattr(after,field): raise ValueError(f'Changed {field}')
        streams, final_streams = {'streams':dv.stream_info(ffprobe,source)}, {'streams':dv.stream_info(ffprobe,output)}
        if nv.stream_inventory(streams) != nv.stream_inventory(final_streams): raise ValueError('Track inventory/dispositions changed')
        if nv.first_video(streams).get('sample_aspect_ratio') != nv.first_video(final_streams).get('sample_aspect_ratio'): raise ValueError('Aspect ratio changed')
        source_pts, source_video_bytes = full.video_packets(ffprobe,source)
        final_pts, final_video_bytes = full.video_packets(ffprobe,output)
        if len(source_pts)!=len(final_pts) or any(abs(a-b)>.002 for a,b in zip(source_pts,final_pts)): raise ValueError('Video packet timeline changed')
        rounding={}
        for selector in ('a','s','t'):
            guard()
            a=np.packet_signatures(ffprobe,source,selector,600)
            b=np.packet_signatures(ffprobe,output,selector,600)
            rounding.update(audit.compare_track_packets(a,b,streams['streams']))
        report['aac_duration_rounding_packets']=rounding
        report['decoded_pcm_checks']={}
        for index in rounding:
            hashes=[]
            for label,path in (('source',source),('output',output)):
                result=stage(ff+['-v','error','-xerror','-i',path,'-map',f'0:{index}','-c:a','pcm_s32le','-f','hash','-hash','sha256','-'],f'Decode {label} AAC track {index} to PCM hash',15)
                hashes.append(next(line.strip() for line in result.splitlines() if line.startswith('SHA256=')))
            if hashes[0]!=hashes[1]: raise ValueError('Decoded AAC audio changed')
            report['decoded_pcm_checks'][index]=dict(identical=True,sha256=hashes[0])
        if chapter_summary(ffprobe,source,60)!=chapter_summary(ffprobe,output,60): raise ValueError('Chapters changed')
        passed,detail=verify_startup_interleaving(output,ffprobe)
        if not passed: raise ValueError(detail)
        report['startup_interleaving']=detail
        fresh=directory/'current-source.hevc'
        stage(ff+['-v','error','-i',source,'-map','0:v:0','-c','copy','-bsf:v','hevc_mp4toannexb','-f','hevc',fresh],'Confirm current source bitstream matches audited frames',25)
        if dv.sha256(fresh)!=dv.sha256(parent/'original.hevc'): raise ValueError('Source bitstream changed since frame audit')
        audit.validate_source_frames(parent/'source-frames.compact',source_pts,guard)
        check_raw, check_rpu = directory/'final-check.hevc', directory/'final-rpu.bin'
        stage(ff+['-v','error','-i',output,'-map','0:v:0','-c','copy','-bsf:v','hevc_mp4toannexb','-f','hevc',check_raw],'Extract final DV bitstream',35)
        stage([dovi,'extract-rpu','-i',check_raw,'-o',check_rpu],'Extract final DV metadata',40)
        digests=[]
        for name,binary in (('source',parent/'original-rpu.bin'),('output',check_rpu)):
            target=directory/(name+'-rpu.json')
            stage([dovi,'export','-i',binary,'-d',f'all={target}'],f'Compare complete {name} RPU metadata',45)
            digests.append(full.rpu_digest(target,guard))
        if digests[0]!=digests[1] or digests[0][0]!=len(source_pts): raise ValueError('RPU content/count/frame order changed')
        report['rpu_content_digest']=digests[0][1]
        guard.phase='Compare every decoded frame and HDR value'; guard.status(60)
        frames=directory/'output-frames.compact'
        report['commands'].append(audit.frame_evidence(ffprobe,output,frames,guard))
        report['decoded_frame_checks']=audit.compare_frames(parent/'source-frames.compact',frames,guard)
        stage(ff+['-v','error','-xerror','-threads','0','-i',output,'-map','0:v:0','-map','0:a?','-f','null','-','-progress','pipe:1','-nostats'],'Full output video/audio decode',80)
        if initial!=(source.stat().st_size,source.stat().st_mtime_ns): raise ValueError('Source stat changed during verification')
        report.update(status='verified-full-file-awaiting-playback',frames=len(source_pts),
                      source_bytes=source.stat().st_size,output_bytes=output.stat().st_size,
                      total_savings_percent=100*(1-output.stat().st_size/source.stat().st_size),
                      video_savings_percent=100*(1-final_video_bytes/source_video_bytes),
                      original_stat_unchanged=True,full_audio_video_decode=True,chapters_unchanged=True,
                      packet_payloads_order_and_pts_unchanged=True,
                      encode_seconds=previous['stage_seconds']['hevc_nvenc full encode'],
                      encode_speed_x=duration/previous['stage_seconds']['hevc_nvenc full encode'],
                      duration_seconds=duration)
        print('Full NVIDIA Dolby Vision checks passed; playback review required.',flush=True)
        return 0
    except Exception as exc:
        report.update(status='failed',error=str(exc)); print(f'FAILED: {exc}',flush=True)
        return 1
    finally:
        (directory/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        guard.phase=report['status']; guard.status(100 if report['status'].startswith('verified') or report['status']=='skipped' else 0)
        print(f'Report: {directory / "validation.json"}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('run',type=Path)
    args=parser.parse_args()
    raise SystemExit(jobs.tracked_call(lambda:main(args.run),'NVIDIA DV retained full-file verification'))
