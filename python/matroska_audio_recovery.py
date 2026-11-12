"""Recover copied-track mux failures without rewriting original timestamps.

This is an encoding route, not validation approval. All normal full-output
packet, decoded audio, metadata, frame timing and quality checks still run.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def eligible(source, output, before, label, hdr_mode, error):
    if (not isinstance(label,str) or not label or
            Path(source).suffix.lower() != '.mkv' or Path(output).suffix.lower() != '.mkv'):
        return False
    if hdr_mode:
        from auto_optimize import main_video
        transfer='arib-std-b67' if hdr_mode=='hlg' else 'smpte2084'
        if hdr_mode not in ('pq','hdr10','hdr10plus','hlg') or main_video(before).get('color_transfer')!=transfer:
            return False
    # Match an identified copied output stream, never an encoder failure. The
    # shared encoder maps the original inventory in order. Its main video is
    # re-encoded; a /copy diagnostic for it is not this recovery route.
    match=re.search(r'\[([avs])ost#0:(\d+)/copy\s+@[^\]]*\]\s+Non-monotonic DTS;',error)
    if match is None or 'Error submitting a packet to the muxer' not in error:return False
    streams=before.get('streams',[]);position=int(match[2])
    if position>=len(streams):return False
    stream=streams[position]
    if stream.get('codec_type')!={'a':'audio','s':'subtitle','v':'video'}[match[1]]:return False
    if match[1]=='v':
        from auto_optimize import main_video
        if stream is main_video(before):return False
    return True


def relay_input_options(identified,relay_identified):
    audio=[t for t in identified['tracks'] if t['type']=='audio']
    copied=relay_identified['tracks']
    if len(audio)!=len(copied):raise ValueError('Audio relay inventory changed')
    result=[]
    for original,new in zip(audio,copied):
        properties=original.get('properties',{});identifier=str(new['id'])+':'
        for key,flag in (('default_track','--default-track-flag'),('forced_track','--forced-display-flag'),
                         ('hearing_impaired','--hearing-impaired-flag'),('visual_impaired','--visual-impaired-flag'),
                         ('text_descriptions','--text-descriptions-flag'),('original','--original-flag'),
                         ('commentary','--commentary-flag')):
            if key in properties:
                if type(properties[key]) is not bool:raise ValueError('Invalid original track flag')
                result += [flag,identifier+str(int(properties[key]))]
        result+=['--language',identifier+properties.get('language_ietf',properties.get('language','und')),
                 '--track-name',identifier+properties.get('track_name','')]
    return result


def relay_mux_command(command, source, relay, identified, relay_identified):
    """Replace only original audio inputs with the timestamp-preserving relay."""
    audio=[t for t in identified['tracks'] if t['type']=='audio']
    copied=relay_identified['tracks']
    if (len(audio)!=len(copied) or any(t['type']!='audio' for t in copied)
            or any(a.get('codec')!=b.get('codec') for a,b in zip(audio,copied))):
        raise ValueError('Audio relay track inventory differs from original')
    ids=[t.get('id') for t in copied]
    if any(type(i) is not int or i<0 for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('Invalid audio relay track IDs')
    mapping={'1:'+str(a['id']):'2:'+str(b['id']) for a,b in zip(audio,copied)}
    result=list(command)
    position=result.index('--track-order')+1
    result[position]=','.join(mapping.get(t,t) for t in result[position].split(','))
    if result[-1]!=str(source):raise ValueError('Original mux input order changed')
    result.insert(len(result)-1,'--no-audio')
    scale=identified.get('container',{}).get('properties',{}).get('timestamp_scale')
    if type(scale) is not int or not 0<scale<=1000000000:
        raise ValueError('Original Matroska timestamp scale unavailable')
    if '--engage' not in result:
        result[1:1]=['--engage','force_passthrough_packetizer','--timestamp-scale',str(scale)]
    result+=['--no-video','--no-subtitles','--no-attachments','--no-chapters',
             '--no-global-tags',*relay_input_options(identified,relay_identified),str(relay)]
    return result


def copy_audio_relay(work,source,relay,before,label,duration):
    """Keep explicit DTS durations before considering decode-clock repair.

    FFmpeg suppresses durations equal to either rounded DefaultDuration. A
    one-sample fallback makes every real DTS packet carry BlockDuration instead;
    the copied compressed audio and its original packet clocks are untouched.
    The complete source/output packet and decoded-audio audits still apply.
    """
    command=[work.args.ffmpeg,'-v','error','-nostdin','-n','-copyts','-i',str(source),
             '-map','0:a','-c','copy','-map_metadata','0','-map_chapters','-1',
             '-avoid_negative_ts','disabled']
    audio=[s for s in before['streams'] if s.get('codec_type')=='audio']
    from dts_terminal_duration import explicit_duration_options
    command += explicit_duration_options(before['streams'])
    command+=['-progress','pipe:1','-nostats',str(relay)]
    try:
        work.execute(command,label+'-audio-duration-relay',duration)
        return 'explicit-original-packet-durations'
    except RuntimeError as exc:
        # Only an identified copied audio clock regression warrants the older
        # native relay. Never retry cancellation, a decoder error or bad input.
        match=re.search(r'\[aost#0:(\d+)/copy\s+@[^\]]*\]\s+Non-monotonic DTS;',str(exc))
        if (match is None or int(match[1])>=len(audio)
                or 'Error submitting a packet to the muxer' not in str(exc)):
            raise
        from artifact_manifest import registered_outputs
        if relay.exists():
            if relay not in registered_outputs(work.directory):
                raise ValueError('Refusing to remove an unregistered audio relay')
            relay.unlink()
        work.execute([sys.executable,'-B',str(Path(__file__).with_name('copied_audio_relay.py')),
                      '--source',str(source),'--output',str(relay)],label+'-audio-packet-relay',duration)
        return 'native-original-packet-clocks'


def hdr_video_view(work,source,before,identified,label,duration):
    """A source-identical primary-video view keeps broken copied DTS out of HDR muxes.

    Every compressed video packet and its clocks must remain exactly equal.
    This does not approve the final output: original non-video/secondary tracks
    are restored afterward and receive ordinary complete output validation.
    """
    from auto_optimize import main_video,stream_metadata_check
    from dv_full_file import copied_matroska_packetizer_options
    from packet_validation import packet_rows
    from itertools import zip_longest
    primary=main_video(before)
    original=[s for s in before['streams'] if s.get('codec_type')!='attachment']
    position=next(i for i,s in enumerate(original) if s is primary)
    track=identified['tracks'][position]
    if track.get('type')!='video':raise ValueError('HDR primary video track mapping changed')
    view=work.directory/(label+'-original-video-view.mkv')
    work.execute(['mkvmerge','-o',str(view),*copied_matroska_packetizer_options(before,identified),
                  '--disable-lacing','--video-tracks',str(track['id']),'--no-audio','--no-subtitles',
                  '--no-attachments','--no-chapters',str(source)],label+'-isolate-original-video',duration)
    metadata=work.probe(view)
    stream_metadata_check(dict(before,streams=[primary]),metadata,primary['codec_name'])
    a=work.copied_packets(source,label+'-video-view-source',[primary['index']],before['format'])[primary['index']]
    b=work.copied_packets(view,label+'-video-view-copy',[0],metadata['format'])[0]
    count=0
    for left,right in zip_longest(packet_rows(a),packet_rows(b)):
        work.guard();count+=1
        if left is None or right is None or left.get('data_hash')!=right.get('data_hash'):
            raise ValueError('HDR source view changed video packet payload/count')
        for key in ('pts_time','dts_time','duration_time'):
            if left.get(key)!=right.get(key):raise ValueError('HDR source view changed an exact video packet clock: '+key)
    if not count:raise ValueError('HDR source view has no video packets')
    cached=work.frame_cache.get(str(Path(source).resolve()))
    if cached is not None:work.frame_cache[str(view.resolve())]=cached
    return view,metadata,dict(video_packets=count,compressed_payloads_exact=True,packet_clocks_exact=True,
                              source_frame_evidence_reused=cached is not None)


def recover(work, source, output, settings, info, before, label, duration, error):
    from auto_optimize import main_video
    from artifact_manifest import registered_outputs
    from dv_full_file import matroska_dv_mux_command
    from dvd_av1_batch import save
    binary = shutil.which('mkvmerge')
    if not binary:
        raise RuntimeError('Copied audio mux recovery requires MKVToolNix; original retained')
    root = work.directory.resolve(strict=True)
    output = Path(output)
    if output.is_symlink() or output.parent.resolve(strict=True) != root:
        raise ValueError('Audio mux recovery output must stay in its owned work directory')
    work.guard()
    identified = json.loads(subprocess.check_output([binary, '-J', str(source)],
                                                    text=True, timeout=60))
    video = output.with_name(output.stem+'-audio-recovery-video.mkv')
    # Validate the track inventory before spending time re-encoding. The same
    # shared two-input mux builder is already used by the preservation route.
    command = matroska_dv_mux_command(video, source, output.with_name(output.stem+'-audio-recovery.mkv'),
                                      before, identified, mkvmerge=binary)
    report = dict(state='retrying', route='video-only-encode-original-track-mux',
                  reason='Copied track DTS regression', validation_required=True)
    save(root/'audio-mux-recovery.json', report)
    if any(s.get('codec_type')=='audio' and s.get('codec_name')=='dts' for s in before['streams']):
        relay=output.with_name(output.stem+'-audio-recovery-packets.mka')
        report['audio_relay']=copy_audio_relay(work,source,relay,before,label,duration)
        relay_identified=json.loads(subprocess.check_output([binary,'-J',str(relay)],text=True,timeout=60))
        command=relay_mux_command(command,source,relay,identified,relay_identified)
        report['route']='video-only-encode-exact-audio-packet-relay'
        save(root/'audio-mux-recovery.json',report)
    encoding_source,encoding_metadata=source,before
    view=None
    if getattr(work,'hdr_mode',None):
        view,encoding_metadata,proof=hdr_video_view(work,source,before,identified,label,duration)
        encoding_source=view;report['hdr_video_view']=proof
        save(root/'audio-mux-recovery.json',report)
    work._encode_preserving_color(encoding_source, video, settings, info, encoding_metadata,
                                 label+'-audio-recovery-video', duration, video_only=True)
    # copyts leaves the original video clock intact: never apply a sync offset.
    work.execute(command, label+'-audio-recovery-mux', duration)
    recovered = Path(command[command.index('-o')+1])
    # A short padded DTS packet can lose its explicit duration during either
    # relay or MKVToolNix remux. Restore only from complete source packet proof;
    # the ordinary full-output timing/audio/quality checks remain unchanged.
    from dts_terminal_duration import restore
    recovered = restore(work, source, recovered, before, label, duration)
    work.guard()
    if output.exists():
        if output not in registered_outputs(root):
            raise ValueError('Refusing to remove an unregistered mux output')
        output.unlink()  # Only the recorded failed generated output, never source.
    from artifact_manifest import command_outputs
    with command_outputs(root, ['generated-link', str(output.absolute())]):
        output.hardlink_to(recovered)
    report.update(state='encoded-awaiting-validation')
    save(root/'audio-mux-recovery.json', report)
    if view is not None:
        if view not in registered_outputs(root):raise ValueError('Unregistered HDR source view')
        view.unlink()
