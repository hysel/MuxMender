"""Preserve auxiliary mastering tags without treating SDR pixels as HDR."""


class StructuredMetadataRequired(ValueError):
    """Compact frame records cannot represent complete mastering metadata."""


def static_metadata(frame):
    from hdr10plus_validation import canonical_hdr_metadata
    result=[]
    for item in frame.get('side_data_list',[]):
        name=item.get('side_data_type','')
        if name in ('Mastering display metadata','Content light level metadata'):
            result.append(item)
        elif any(token in name.lower() for token in ('dolby','dovi','hdr','2094','display matrix','mastering','content light')):
            raise ValueError('Unexpected HDR/geometry frame side data')
    return canonical_hdr_metadata(result)


def frame_rows(path):
    from hdr10plus_preserve import frame_records
    for frame in frame_records(path):
        row={key:str(value) for key,value in frame.items() if not isinstance(value,(dict,list))}
        row['_static_hdr_metadata']=static_metadata(frame)
        yield row


def reader_request(cpu,source,threads,decoder_options=()):
    from gpu_frame_reader import SDR_FRAME_FIELDS
    from decoder_context import metadata_reader_options
    return [cpu,'-v','error',*metadata_reader_options(threads),'-select_streams','V:0',
            '-show_frames','-show_entries','frame='+SDR_FRAME_FIELDS+':frame_side_data',
            '-of','json=compact=1',*decoder_options,str(source)]
