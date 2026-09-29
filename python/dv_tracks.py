"""Shared secondary-video preservation checks for specialized DV workflows."""
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace


def primary(streams):
    from auto_optimize import main_video
    return main_video({'streams':streams})


def verify(ffmpeg,ffprobe,source,output,directory,guard=lambda:None,*,end_time=None,frames=None,verified_variable_timing=False):
    from auto_optimize import Workflow,paired_streams,stream_metadata_check,is_cover,compare_packets
    from packet_validation import packet_rows
    work=Workflow(SimpleNamespace(ffmpeg=ffmpeg,ffprobe=ffprobe,timeout=14400),Path(directory),guard)
    before,after=work.probe(source),work.probe(output)
    stream_metadata_check(before,after,'hevc',verified_frame_count=frames,
                          verified_variable_timing=verified_variable_timing)
    first=primary(before['streams'])['index']
    pairs=[(a,b) for a,b in paired_streams(before,after)
           if a['codec_type'] not in ('audio','subtitle','attachment') and a['index']!=first]
    if not pairs:return []
    original=work.copied_packets(source,'dv-secondary-source',[a['index'] for a,b in pairs],before['format'])
    encoded=work.copied_packets(output,'dv-secondary-output',[b['index'] for a,b in pairs],after['format'])
    for a,b in pairs:
        guard();reference=original[a['index']]
        if end_time is not None and not is_cover(a):
            # Reference clips include a complete extra GOP. Compare exactly the
            # packets belonging to the bounded output, never a sampled hash.
            bounded=Path(directory)/f"dv-secondary-{a['index']}-bounded.txt"
            with bounded.open('x',encoding='utf-8') as handle:
                for packet in packet_rows(reference):
                    guard()
                    if Fraction(packet['pts_time'])<Fraction(str(end_time)):
                        handle.write('packet|'+'|'.join(key+'='+value for key,value in packet.items())+'\n')
            reference=bounded
        compare_packets(reference,encoded[b['index']],cover=is_cover(a))
    return [a['index'] for a,b in pairs]
