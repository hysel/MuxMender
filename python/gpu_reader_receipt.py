"""Build image reader scopes from complete evidence, never from job labels."""
import math
import re


def qualified_scope(real,controls):
    """Accept a complete pair and damaged controls for the same reader artifact.

    This grants only a metadata-reader optimization. Quality scoring, source
    checks, copied tracks, output validation and publication stay separate.
    """
    if not isinstance(real,dict) or not isinstance(controls,dict):
        raise ValueError('Reader evidence must be structured')
    digest=real.get('binary_sha256')
    if (not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest)
            or controls.get('binary_sha256')!=digest):
        raise ValueError('Real and damaged-input evidence must bind the same reader build')
    if real.get('error') or real.get('source_changed') is not False:
        raise ValueError('Real source qualification is incomplete or changed')
    source=real.get('source',{})
    if source.get('codec_name') not in ('hevc','av1') or source.get('pix_fmt')!='yuv420p10le':
        raise ValueError('Reader evidence does not cover this codec and pixel format')
    if controls.get('codec_name')!=source['codec_name']:
        raise ValueError('Damaged controls cover a different codec')
    for mode in ('cpu','cuda'):
        result=real.get('full_reads',{}).get(mode,{})
        if result.get('strict_success') is not True or result.get('returncode')!=0 or result.get('error')!='':
            raise ValueError('Both whole-file readers must drain cleanly to EOF')
        seconds=result.get('seconds')
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0:
            raise ValueError('Missing whole-file reader timings')
    proof=real.get('full_pairwise_proof',{})
    if any(proof.get(key) is not True for key in ('hdr_metadata_exact','frame_timestamps_exact',
            'frame_timing_preserved','geometry_color_exact')):
        raise ValueError('Every-frame metadata and timing equality is required')
    if type(proof.get('frames')) is not int or proof['frames']<=0 or proof.get('max_timestamp_delta_seconds')!=0:
        raise ValueError('Frame evidence is incomplete or not exact')
    mode=proof.get('mode')
    if mode not in ('hdr10','hdr10plus','pq','hlg'):
        raise ValueError('HDR qualification mode is missing')
    if mode in ('hdr10','hdr10plus'):
        key='static_hdr_frames' if mode=='hdr10' else 'hdr10plus_frames'
        covered=proof.get(key)
        if type(covered) is not int or not 0<covered<=proof['frames']:
            raise ValueError('Declared HDR qualification lacks matching complete-frame evidence')
    cases=controls.get('corruption',[])
    if not isinstance(cases,list) or len(cases)<3 or controls.get('control_passed') is not True:
        raise ValueError('Healthy and distributed damaged-input controls are required')
    for case in cases:
        if not isinstance(case,dict) or case.get('cuda',{}).get('strict_success') is not False:
            raise ValueError('A deliberately damaged input escaped the GPU reader')
    if controls.get('false_passes')!=[]:
        raise ValueError('Damaged-input regression remains')
    reduction=100*(1-real['full_reads']['cuda']['seconds']/real['full_reads']['cpu']['seconds'])
    if reduction<=0:raise ValueError('No measured whole-file speed benefit')
    # Do not infer dynamic HDR or HLG qualification from a static PQ source.
    modes=[mode]+(['pq'] if mode in ('hdr10','hdr10plus') else [])
    return dict(codec=source['codec_name'],pixel_format=source['pix_fmt'],hdr_modes=modes,
                full_eof=True,every_frame_cpu_gpu_equal=True,corrupt_controls_rejected=True,
                time_reduction_percent=reduction,qualified_frames=proof['frames'])
