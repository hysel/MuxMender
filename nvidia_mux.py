"""Separate NVENC video production from bounded, stream-copy final muxing."""
from mux_integrity import INTERLEAVE_MICROSECONDS


def video_stage_command(command):
    """Derive a video-only command; input timestamps remain on the source timeline."""
    result = list(command)
    index = result.index('-map')
    if result[index + 1] != '0':
        raise ValueError('Expected the standard single-input stream mapping')
    result[index + 1] = '0:v:0'
    # Finalization restores all source dispositions at their original indices.
    index = 0
    while index < len(result) - 1:
        if result[index].startswith('-disposition:'):
            del result[index:index + 2]
        else:
            index += 1
    if '-copyts' not in result:
        index = result.index('-i')
        result[index:index] = ['-copyts']
    if '-avoid_negative_ts' not in result:
        result[-1:-1] = ['-avoid_negative_ts', 'disabled']
    if '-fps_mode' not in result:
        result[-1:-1] = ['-fps_mode', 'passthrough']
    if '-enc_time_base:v' not in result:
        result[-1:-1] = ['-enc_time_base:v', 'demux']
    return result


def finalize_command(video, source, output, source_probe, ffmpeg):
    """Keep original stream order, metadata, chapters and explicit dispositions."""
    streams = source_probe['streams']
    if sum(s.get('codec_type') == 'video' for s in streams) != 1:
        raise ValueError('NVIDIA finalization requires exactly one video stream')
    mapping = []
    disposition = []
    for index, stream in enumerate(streams):
        mapping += ['-map', '0:v:0' if stream['codec_type'] == 'video' else f"1:{stream['index']}"]
        flags = '+'.join(k for k, value in stream.get('disposition', {}).items() if value) or '0'
        disposition += [f'-disposition:{index}', flags]
    return [ffmpeg, '-hide_banner', '-nostdin', '-n', '-copyts',
            '-i', str(video), '-i', str(source), *mapping,
            '-map_metadata', '1', '-map_chapters', '1', '-c', 'copy',
            *disposition, '-avoid_negative_ts', 'disabled',
            '-max_interleave_delta', str(INTERLEAVE_MICROSECONDS), str(output)]
