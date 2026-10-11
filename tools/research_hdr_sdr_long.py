"""Read-only-source Mobius excerpt qualification with original copied tracks."""
import copy
from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def probe_command(path,frames=False):
    # Match the shared workflow's bounded reader; auto threads can oversubscribe
    # a container when FFmpeg detects the host's full CPU inventory.
    args=['ffprobe','-v','error','-threads','2']
    if frames:
        args+=['-select_streams','v:0','-show_frames']
    else:
        args+=['-show_streams','-show_chapters','-show_format','-show_data_hash','sha256']
    return args+['-of','json',str(path)]


def nvenc_research_options(policy,codec='hevc'):
    if codec not in ('hevc','av1'):raise ValueError('Unknown NVIDIA research codec')
    limit=policy['video_bps']
    if type(limit) is not int or limit<=0:raise ValueError('Finite bitrate target required')
    # A little rate-control headroom; the measured preset ceiling is unchanged.
    return ['-c:v',codec+'_nvenc','-preset','p7','-tune','hq','-multipass','fullres',
            '-rc','vbr','-cq','18','-b:v',str(limit*95//100),
            '-maxrate',str(limit*98//100),'-bufsize',str(limit*98//100),
            *(['-bf','3','-b_ref_mode','middle'] if codec=='hevc' else ['-bf','0']),'-rc-lookahead','32',
            '-pix_fmt','p010le','-fps_mode','passthrough',
            '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv']


def run(root):
    import av  # Fail before extracting media if the installed image lacks its pinned relay runtime.
    from research_hdr_sdr import require_idle_production, render_filter
    from job_tracking import progress
    from output_presets import preset, expected_metadata
    from auto_optimize import (main_video, paired_streams, metadata_check, compare_frame_rows,
                               compare_packets, quality_command, quality_graph, quality_summary)
    from dv_full_file import matroska_dv_mux_command, copied_matroska_packetizer_options
    from copied_audio_relay import relay
    from matroska_audio_recovery import relay_mux_command
    from native_pipeline import discard_audio_clock_options
    from task_progress import run_probe
    from streaming_pipeline import verify_chapters_preserved
    require_idle_production()
    options=root/'research-options.json'
    codec=json.loads(options.read_text()).get('codec','hevc') if options.exists() else 'hevc'
    nvenc_research_options(preset('tv1080'),codec)  # Validate before reading media.
    if shutil.disk_usage(root).free < 10*1024**3:
        raise RuntimeError('At least 10 GiB research scratch headroom required')
    os.nice(10)
    locator=Path('/work/audio-fix-full-a234ffd131ea/cases/case-0')
    source=Path(json.loads(next(locator.glob('auto-*/status.json')).read_text())['source']).resolve(strict=True)
    if not source.is_relative_to('/media'):raise ValueError('Read-only media source required')
    identity=source.stat()
    def execute(args,label,timeout=1800):
        require_idle_production()
        progress(label,detail='Separate two-minute research copy; originals protected')
        with (root/(label+'.log')).open('x') as log:
            result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                  cwd=root,timeout=timeout)
        if result.returncode and not (args[0]=='mkvmerge' and result.returncode==1):
            raise RuntimeError(label+' failed; inspect its log')
    def probe(path,frames=False):
        command=probe_command(path,frames)
        if not frames:return json.loads(subprocess.check_output(command,timeout=180))
        metadata=probe(path)
        evidence=root/(path.stem+'-frames.json')
        run_probe(command,evidence,'Checking all frames: '+path.stem,180,require_idle_production,
                  float(metadata['format']['duration']),float(metadata['format'].get('start_time',0)))
        if evidence.with_suffix(evidence.suffix+'.stderr').stat().st_size:
            raise ValueError('Frame decoder reported errors: '+path.name)
        return json.loads(evidence.read_text())
    metadata=probe(source);video=main_video(metadata)
    if video.get('color_transfer')!='smpte2084' or video.get('color_primaries')!='bt2020':
        raise ValueError('PQ BT.2020 source required')
    for side in video.get('side_data_list',[]):
        if side.get('side_data_type')=='DOVI configuration record' and side.get('dv_bl_signal_compatibility_id')!=1:
            raise ValueError('HDR10-compatible base layer required')
    start=int(float(metadata['format']['duration'])/2)
    def clock(seconds):return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'
    identified=json.loads(subprocess.check_output(['mkvmerge','-J',str(source)],timeout=60))
    execute(['mkvmerge','-o',str(root/'source-excerpt.mkv'),
             *copied_matroska_packetizer_options(metadata,identified),'--disable-lacing',
             '--split','parts:'+clock(start)+'-'+clock(start+120),str(source)],'extract-source-excerpt')
    excerpts=list(root.glob('source-excerpt*.mkv'))
    if len(excerpts)!=1:raise ValueError('Expected exactly one generated source excerpt')
    excerpt=excerpts[0];before=probe(excerpt);video=main_video(before)
    duration=float(before['format']['duration'])
    if not 100<=duration<=140:raise ValueError('Unexpected keyframe-aligned excerpt duration')
    reference=root/'mobius-lossless-reference.mkv';encoded=root/'mobius-video.mkv'
    output=root/f'mobius-1080p-{codec}-with-tracks.mkv';policy=preset('tv1080')
    execute(['ffmpeg','-hide_banner','-nostdin','-n','-threads','2','-filter_threads','2',
             '-i',str(excerpt),'-map','0:V:0','-an','-sn','-dn','-map_metadata','-1','-map_chapters','-1',
             '-vf',render_filter(video,'tv1080','mobius'),'-c:v','ffv1','-level','3',
             '-pix_fmt','yuv420p10le','-fps_mode','passthrough',
             '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
             str(reference)],'render-mobius-reference')
    execute(['ffmpeg','-hide_banner','-nostdin','-n','-threads','2','-i',str(reference),
             '-map','0:V:0','-an','-sn','-map_metadata','-1','-map_chapters','-1',
             *nvenc_research_options(policy,codec),
             str(encoded)],'encode-'+codec+'-nvidia')
    progress('Reading complete video timing',detail='Auditing excerpt frames before track assembly')
    original_frames=probe(excerpt,True)['frames']
    offset=float(original_frames[0]['best_effort_timestamp_time'])
    clip_id=json.loads(subprocess.check_output(['mkvmerge','-J',str(excerpt)],timeout=60))
    command=matroska_dv_mux_command(encoded,excerpt,output,before,clip_id,start_offset=offset)
    if any(s.get('codec_type')=='audio' for s in before['streams']):
        audio=root/'audio-relay.mka'
        progress('Copying original audio packets',detail='Shared timestamp-preserving audio relay')
        relay(excerpt,audio)
        relay_id=json.loads(subprocess.check_output(['mkvmerge','-J',str(audio)],timeout=60))
        command=relay_mux_command(command,excerpt,audio,clip_id,relay_id)
    execute(command,'assemble-original-tracks')
    after=probe(output);rendered=probe(reference,True);actual=probe(output,True)
    expected_frames=copy.deepcopy(rendered['frames'])
    for f in expected_frames:
        f['best_effort_timestamp_time']=str(Fraction(f['best_effort_timestamp_time'])+Fraction(str(offset)))
    def frame_rows(frames):
        for frame in frames:
            row={key:str(value) for key,value in frame.items() if key!='side_data_list'}
            if frame.get('side_data_list'):
                row['side_data_type']=';'.join(s.get('side_data_type','') for s in frame['side_data_list'])
            yield row
    count=compare_frame_rows(frame_rows(expected_frames),frame_rows(actual['frames']))
    if count!=len(original_frames):raise ValueError('Excerpt frame inventory changed')
    for old,new in zip(original_frames,actual['frames']):
        if abs(Fraction(old['best_effort_timestamp_time'])-Fraction(new['best_effort_timestamp_time']))>Fraction(1,500):
            raise ValueError('Original excerpt video timeline changed')
    expected=expected_metadata(before,'tv1080');primary=main_video(expected)
    primary.update(pix_fmt='yuv420p10le',color_transfer='bt709',color_primaries='bt709',color_space='bt709',color_range='tv')
    primary['side_data_list']=[s for s in primary.get('side_data_list',[]) if not any(
        text in s.get('side_data_type','').lower() for text in ('dovi','dolby','mastering','content light','hdr','2094'))]
    chapter_evidence=verify_chapters_preserved('ffprobe',excerpt,output,180)
    (root/'chapter-evidence.json').write_text(json.dumps(chapter_evidence,indent=2))
    metadata_check(expected,after,codec,verified_frame_count=count,chapter_evidence=chapter_evidence)
    copied=[]
    for a,b in paired_streams(before,after):
        if a['index']==video['index']:continue
        if a['codec_type']=='attachment':
            if not a.get('extradata_hash') or a.get('extradata_hash')!=b.get('extradata_hash'):
                raise ValueError('Attachment byte evidence missing or changed')
            continue
        paths=[]
        for label,path,index in [('before',excerpt,a['index']),('after',output,b['index'])]:
            evidence=root/f'{label}-stream-{index}.txt'
            with evidence.open('x') as stream:
                subprocess.run(['ffprobe','-v','error','-select_streams',str(index),'-show_packets',
                    '-show_data_hash','sha256','-show_entries','packet=pts_time,dts_time,duration_time,data_hash',
                    '-of','compact=p=0',str(path)],stdout=stream,check=True,timeout=300)
            paths.append(evidence)
        compare_packets(*paths);copied.append(a['codec_type'])
        if a['codec_type']=='audio':
            hashes=[]
            for label,path,index in [('before',excerpt,a['index']),('after',output,b['index'])]:
                phase=f'{label}-audio-{index}-pcm'
                execute(['ffmpeg','-hide_banner','-nostdin','-v','error','-xerror','-threads','2',
                    '-i',str(path),'-map','0:'+str(index),'-c:a','pcm_f64le',
                    *discard_audio_clock_options(dict(streams=[a])),
                    '-f','hash','-hash','sha256','-'],phase)
                hashes.append((root/(phase+'.log')).read_text().strip())
            if not hashes[0].startswith('SHA256=') or hashes[0]!=hashes[1]:
                raise ValueError('Decoded audio samples changed')
    execute(['ffmpeg','-hide_banner','-nostdin','-v','error','-xerror','-threads','2','-i',str(output),
             '-map','0:v:0','-map','0:a?',*discard_audio_clock_options(after),
             '-f','null','-'],'decode-complete-excerpt')
    execute(quality_command('ffmpeg',output,reference,
            quality_graph('quality.json',video['avg_frame_rate'],threads=2)),'check-video-quality')
    quality=quality_summary(json.loads((root/'quality.json').read_text()),count,policy['mean'],policy['p5'])
    packets=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_packets','-show_entries','packet=size,duration_time','-of','json',str(output)],timeout=180))['packets']
    video_bps=8*sum(int(p['size']) for p in packets)/sum(float(p['duration_time']) for p in packets)
    latest=source.stat()
    if (identity.st_dev,identity.st_ino,identity.st_size,identity.st_mtime_ns)!=(latest.st_dev,latest.st_ino,latest.st_size,latest.st_mtime_ns):
        raise ValueError('Source identity changed')
    passed=quality['passed'] and video_bps<=policy['video_bps'] and output.stat().st_size<excerpt.stat().st_size
    result=dict(schema='muxmender-mobius-excerpt-v1',passed=passed,quality=quality,video_bps=video_bps,
        codec=codec,thresholds=policy,nvenc_cq=18,encoder_options=nvenc_research_options(policy,codec),seconds=duration,frames=count,
        original_excerpt_bytes=excerpt.stat().st_size,output_bytes=output.stat().st_size,
        savings_percent=100*(1-output.stat().st_size/excerpt.stat().st_size),
        copied_tracks=copied,chapter_evidence=chapter_evidence,decoded_audio_samples_equal=True,frame_timing_metadata_and_packets_passed=True,source_stat_unchanged=True,
        publication_authorized=False,output=output.name,
        scope='Keyframe-aligned two-minute Mobius SDR excerpt. Quality is measured against the same lossless SDR render, not HDR/Dolby Vision appearance. No full-file qualification or replacement.')
    (root/'result.json').write_text(json.dumps(result,indent=2))
    progress('Mobius excerpt checks finished',completed=1,total=1,unit='excerpts',detail='Separate copy ready for playback review' if passed else 'Excerpt did not meet quality, bitrate or size checks')
    return 0 if passed else 1


def run_with_cleanup(root):
    try:return run(root)
    finally:
        for name in ('mobius-lossless-reference.mkv','mobius-video.mkv','audio-relay.mka'):
            (root/name).unlink(missing_ok=True)
        for p in root.glob('source-excerpt*.mkv'):p.unlink()


if __name__=='__main__':
    if not sys.platform.startswith('linux'):raise RuntimeError('Isolated Linux research only')
    root=Path(__file__).resolve().parent
    sys.path.insert(0,str(root/'python'))
    from job_tracking import tracked_call
    raise SystemExit(tracked_call(lambda:run_with_cleanup(root),'Mobius SDR excerpt with copied tracks',root/'reports'))
