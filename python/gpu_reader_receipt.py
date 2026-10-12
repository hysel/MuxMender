"""Build image reader scopes from complete evidence, never from job labels."""
import math
import re


def sdr_comparison_pair(report,container):
    """Normalize a finished full-source comparison without inventing new proof.

    Container must come from a source-metadata witness, not its filename. The
    generated-only benchmark deliberately cannot produce a production scope.
    """
    if (not isinstance(report,dict) or report.get('error') or report.get('cleanup_error')
            or report.get('scope')!='Read-only complete approved SDR source and generated controls'
            or report.get('controls_passed') is not True or report.get('source_unchanged') is not True):
        raise ValueError('A completed, unchanged full-source SDR comparison is required')
    if report.get('source_container') not in (None,container):
        raise ValueError('Source container witness disagrees with the comparison')
    source=report.get('source',{})
    if not isinstance(source,dict) or source.get('codec_name')!=report.get('codec') or source.get('pix_fmt')!=report.get('pixel_format'):
        raise ValueError('Source and control scopes differ')
    proof=report.get('exact_pairwise_proof',{})
    if not isinstance(proof,dict) or proof.get('every_field_exact') is not True or proof.get('frame_timestamps_exact') is not True:
        raise ValueError('Full-source exact-field parity is missing')
    reads={}
    measurements=report.get('measurements',[])
    if not isinstance(measurements,list) or len(measurements)!=2:raise ValueError('Expected one complete CPU/GPU source pair')
    for row in measurements:
        if not isinstance(row,dict):raise ValueError('Malformed whole-source reader measurement')
        backend=row.get('backend')
        if (backend not in ('cpu','cuda') or backend in reads or row.get('strict_success') is not True
                or row.get('error') is not None or row.get('stderr_bytes')!=0):
            raise ValueError('Whole-source reader did not complete cleanly')
        reads[backend]=dict(strict_success=True,returncode=0,error='',seconds=row.get('seconds'))
    real=dict(binary_sha256=report.get('binary_sha256'),source_changed=False,
        source=dict(source,container=container),full_reads=reads,
        full_pairwise_proof=dict(frames=proof.get('frames'),mode='sdr',every_field_exact=True,
            frame_timestamps_exact=True,frame_timing_preserved=True,geometry_color_exact=True,
            max_timestamp_delta_seconds=0))
    controls=dict(binary_sha256=report.get('binary_sha256'),codec_name=report.get('codec'),
        pixel_format=report.get('pixel_format'),healthy=report.get('raw_healthy'),
        control_passed=True,corruption=report.get('corruption'),false_passes=report.get('false_passes'))
    qualified_scope(real,controls)
    return dict(real=real,controls=controls)


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
    proof=real.get('full_pairwise_proof',{})
    mode=proof.get('mode')
    pixels=('yuv420p','yuv420p10le') if mode=='sdr' else ('yuv420p10le',)
    if source.get('codec_name') not in ('hevc','av1') or source.get('pix_fmt') not in pixels:
        raise ValueError('Reader evidence does not cover this codec and pixel format')
    if controls.get('codec_name')!=source['codec_name']:
        raise ValueError('Damaged controls cover a different codec')
    for backend in ('cpu','cuda'):
        result=real.get('full_reads',{}).get(backend,{})
        if result.get('strict_success') is not True or result.get('returncode')!=0 or result.get('error')!='':
            raise ValueError('Both whole-file readers must drain cleanly to EOF')
        seconds=result.get('seconds')
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0:
            raise ValueError('Missing whole-file reader timings')
    required=('frame_timestamps_exact','frame_timing_preserved','geometry_color_exact',
              'every_field_exact' if mode=='sdr' else 'hdr_metadata_exact')
    if any(proof.get(key) is not True for key in required):
        raise ValueError('Every-frame metadata and timing equality is required')
    if type(proof.get('frames')) is not int or proof['frames']<=0 or proof.get('max_timestamp_delta_seconds')!=0:
        raise ValueError('Frame evidence is incomplete or not exact')
    if mode not in ('sdr','hdr10','hdr10plus','pq','hlg'):
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
    containers=None
    if mode=='sdr':
        if controls.get('pixel_format')!=source['pix_fmt']:
            raise ValueError('SDR controls must match the exact pixel format')
        healthy=controls.get('healthy',{})
        if not isinstance(healthy,dict):raise ValueError('Healthy SDR controls are missing')
        counts=[]
        for backend in ('cpu','cuda'):
            row=healthy.get(backend,{})
            frames=row.get('frames')
            if row.get('strict_success') is not True or type(frames) is not int or frames<=0:
                raise ValueError('SDR controls require nonempty healthy reads on both backends')
            counts.append(frames)
        if counts[0]!=counts[1]:raise ValueError('Healthy control frame counts differ')
        expected={'early-header','early-entropy','middle-header','middle-entropy','late-header','late-entropy','truncated'}
        if len(cases)!=len(expected) or {case.get('case') for case in cases}!=expected:
            raise ValueError('Distributed SDR corruption controls are incomplete')
        container=source.get('container')
        containers=sorted(set(container.split(','))) if isinstance(container,str) else []
        if not containers or not set(containers)<={'matroska','webm','mov','mp4','m4a','3gp','3g2','mj2','mpegts','obu'}:
            raise ValueError('SDR full-source container qualification is missing or unsupported')
    reduction=100*(1-real['full_reads']['cuda']['seconds']/real['full_reads']['cpu']['seconds'])
    if reduction<=0:raise ValueError('No measured whole-file speed benefit')
    # Do not infer dynamic HDR or HLG qualification from a static PQ source.
    modes=[mode]+(['pq'] if mode in ('hdr10','hdr10plus') else [])
    result=dict(codec=source['codec_name'],pixel_format=source['pix_fmt'],hdr_modes=modes,
                full_eof=True,every_frame_cpu_gpu_equal=True,corrupt_controls_rejected=True,
                time_reduction_percent=reduction,qualified_frames=proof['frames'])
    if containers is not None:result['containers']=containers
    return result
