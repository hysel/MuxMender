"""Opt-in qualification route: NVDEC feeds unchanged NVENC/output validation."""


def apply(command, video, encoder):
    if (encoder not in ('av1_nvenc','hevc_nvenc') or video.get('codec_name')!='av1'
            or video.get('pix_fmt')!='yuv420p' or video.get('field_order')!='progressive'
            or video.get('color_transfer') in ('smpte2084','arib-std-b67')):
        raise ValueError('GPU input qualification currently requires progressive AV1 8-bit SDR and NVENC')
    if command.count('-i')!=1 or any(k in command for k in ('-hwaccel','-filter_complex')):
        raise ValueError('GPU input qualification requires an unmodified single-input decode path')
    result=list(command)
    position=result.index('-i')
    result[position:position]=['-hwaccel','cuda','-hwaccel_output_format','cuda']
    # Keep existing CPU filters (including color metadata and resize) unchanged.
    prefix='hwdownload,format=nv12,format=yuv420p'
    filters=[i for i,value in enumerate(result) if value in ('-vf','-filter:v','-filter:v:0')]
    if len(filters)>1:raise ValueError('Multiple video filters need explicit qualification')
    if filters:result[filters[0]+1]=prefix+','+result[filters[0]+1]
    else:result[-1:-1]=['-filter:v:0',prefix]
    return result
