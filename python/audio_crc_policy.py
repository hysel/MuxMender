"""Classify existing source-audio issues; never approve changed output packets."""
import re
from native_pipeline import strict_decode_line


def decoder_names(codec):
    aliases={'ac3':{'ac3_fixed'},'dts':{'dca'},'aac':{'aac_fixed'},
             'mp3':{'mp3float'},'mp2':{'mp2float'},'mp1':{'mp1float'},
             'opus':{'libopus'},'vorbis':{'libvorbis'}}
    return {codec}|aliases.get(codec,set())


def crc_diagnostics(lines):
    """Accept only CRC diagnostics and their immediate decoder error wrapper.

    Used on a complete diagnostic decode. The caller must also verify successful
    process completion and independently compare every compressed output packet.
    This is not proof of clean decoded audio.
    """
    count = 0
    pending = False
    for line in lines:
        text = line.strip()
        if re.fullmatch(r'\[ac3(?:_fixed)? @ 0x[0-9a-fA-F]+\] frame CRC mismatch', text):
            count += 1
            pending = True
            continue
        if pending and re.fullmatch(
                r'\[aist#\d+:\d+/ac3 @ 0x[0-9a-fA-F]+\] '
                r'\[dec:ac3(?:_fixed)? @ 0x[0-9a-fA-F]+\] '
                r'Error submitting packet to decoder: Invalid data found when processing input', text):
            pending = False
            continue
        strict_decode_line(line)
    return count


def source_audio_diagnostics(lines, codec):
    """Accept source audio decoder diagnostics, not video, I/O or resource errors.

    This identifies a warning, not successful audio decoding. Complete packet
    identity and timing remain necessary before an output can be approved.
    """
    codecs=decoder_names(codec)
    count=0
    for line in lines:
        text=line.strip()
        if re.search(r'out of memory|cannot allocate memory|permission denied|input/output error|no space left|device.*failed',text,re.I):
            raise RuntimeError('Source audio diagnosis could not complete: '+text)
        match=re.fullmatch(r'\[([A-Za-z0-9_]+) @ 0x[0-9a-fA-F]+\] (.+)',text)
        if match and match.group(1) in codecs:
            count+=1
            continue
        repeated=re.fullmatch(r'Last message repeated ([1-9][0-9]*) times',text)
        if count and repeated:
            count+=int(repeated.group(1));continue
        wrapper=re.fullmatch(r'\[aist#\d+:\d+/([A-Za-z0-9_]+) @ 0x[0-9a-fA-F]+\] '
                             r'\[dec:([A-Za-z0-9_]+) @ 0x[0-9a-fA-F]+\] '
                             r'Error submitting packet to decoder: Invalid data found when processing input',text)
        if count and wrapper and all(name in codecs for name in wrapper.groups()):continue
        if count and text=='Conversion failed!':continue
        strict_decode_line(line)
    return count


def warning(index, count):
    return dict(code='source_audio_issues_preserved', stream_index=index,
                reported_issues=count, audio_repaired=False,
                message='The original audio had decoding issues. Its compressed audio was kept unchanged; existing audio issues remain.')
