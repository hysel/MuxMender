"""Recover a copied-audio mux failure without rewriting audio timestamps.

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
    if (label != 'full-encode' or hdr_mode or
            Path(source).suffix.lower() != '.mkv' or Path(output).suffix.lower() != '.mkv'):
        return False
    # Require the streamcopy audio diagnostic, not merely a generic DTS error.
    return bool(re.search(r'\[aost#[^\]]+/copy\s+@[^\]]*\]\s+Non-monotonic DTS;', error)
                and 'Error submitting a packet to the muxer' in error
                and any(s.get('codec_type') == 'audio' for s in before['streams']))


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
                  reason='Copied audio DTS regression', validation_required=True)
    save(root/'audio-mux-recovery.json', report)
    if any(s.get('codec_type')=='audio' and s.get('codec_name')=='dts' for s in before['streams']):
        relay=output.with_name(output.stem+'-audio-recovery-packets.mka')
        work.execute([sys.executable,'-B',str(Path(__file__).with_name('copied_audio_relay.py')),
                      '--source',str(source),'--output',str(relay)],
                     label+'-audio-packet-relay',duration)
        relay_identified=json.loads(subprocess.check_output([binary,'-J',str(relay)],text=True,timeout=60))
        command=relay_mux_command(command,source,relay,identified,relay_identified)
        report['route']='video-only-encode-exact-audio-packet-relay'
        save(root/'audio-mux-recovery.json',report)
    work._encode_preserving_color(source, video, settings, info, before,
                                 label+'-audio-recovery-video', duration, video_only=True)
    # copyts leaves the original video clock intact: never apply a sync offset.
    work.execute(command, label+'-audio-recovery-mux', duration)
    recovered = Path(command[command.index('-o')+1])
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
