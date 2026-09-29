"""Layer-preservation evidence; not permission to encode or publish Profile 7.

Callers independently extract both files, remove RPU from each enhancement
stream, and export complete RPU JSON. Geometry, decoded timing, other tracks,
quality and savings still require their normal validators.
"""
import hashlib
import json
import math
from pathlib import Path
import re

from dv_full_file import rpu_digest


def requires_fel_reconstruction(types):
    """Any FEL frame needs reconstruction, even in a mixed MEL/FEL sequence."""
    if (not isinstance(types, list) or not types
            or any(kind not in ('MEL', 'FEL') for kind in types)
            or len(set(types)) != len(types)):
        raise ValueError('Enhancement inventory is missing or unresolved')
    return 'FEL' in types


def profile7_configuration(config):
    if not isinstance(config, dict) or any(type(config.get(k)) is not int or config[k] != v
            for k, v in {'dv_profile': 7, 'el_present_flag': 1,
                         'bl_present_flag': 1, 'rpu_present_flag': 1}.items()):
        raise ValueError('Profile 7 layer signaling is incomplete')
    return dict(config)


def rpu_inventory(path, guard=lambda: None):
    """Read every RPU, not a profile label or a short opening sample."""
    types = set()

    def inspect(record):
        if type(record.get('dovi_profile')) is not int or record['dovi_profile'] != 7:
            raise ValueError('RPU is not Profile 7')
        el_type = record.get('el_type')
        if el_type not in ('MEL', 'FEL'):
            raise ValueError('RPU enhancement type is unresolved')
        types.add(el_type)

    count, digest = rpu_digest(Path(path), guard, inspect=inspect)
    if not count:
        raise ValueError('No enhancement RPU records found')
    return dict(frames=count, enhancement_types=sorted(types), rpu_sha256=digest)


def extract_layers(workflow, source, label, *, dovi_tool='dovi_tool'):
    """Logged, cancellable full-layer extraction for shared workflow callers.

    A fresh owned subdirectory prevents retries overwriting evidence. Caller
    supplies the ordinary source-identity/storage guard through Workflow; this
    inventory does not authorize encoding, quality acceptance or publication.
    """
    from auto_optimize import main_video
    if not isinstance(label, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', label):
        raise ValueError('Layer evidence label must be a simple name')
    workflow.guard()
    source = Path(source)
    metadata = workflow.probe(source)
    video = main_video(metadata)
    configs = [s for s in video.get('side_data_list', [])
               if s.get('side_data_type') == 'DOVI configuration record']
    if len(configs) != 1:
        raise ValueError('Exactly one Dolby Vision configuration is required')
    config = profile7_configuration(configs[0])
    if video.get('codec_name') != 'hevc':
        raise ValueError('Layer extraction requires an HEVC bitstream')
    duration = float(metadata.get('format', {}).get('duration') or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Layer extraction needs a measured positive duration')
    directory = Path(workflow.directory) / label
    directory.mkdir()  # Exclusive; never reuse a partially written inventory.
    raw, base, enhancement, payload, rpu, exported = [directory/name for name in (
        'layered.hevc', 'base.hevc', 'enhancement.hevc', 'enhancement-video.hevc',
        'metadata.rpu', 'metadata.json')]
    commands = [
        [workflow.args.ffmpeg, '-v', 'error', '-nostdin', '-n', '-i', str(source),
         '-map', '0:'+str(video['index']), '-c', 'copy', '-bsf:v', 'hevc_mp4toannexb',
         '-f', 'hevc', str(raw)],
        [dovi_tool, 'demux', '-i', str(raw), '--bl-out', str(base), '--el-out', str(enhancement)],
        [dovi_tool, 'remove', '-i', str(enhancement), '-o', str(payload)],
        [dovi_tool, 'extract-rpu', '-i', str(raw), '-o', str(rpu)],
        [dovi_tool, 'export', '-i', str(rpu), '-d', 'all='+str(exported)],
    ]
    for number, command in enumerate(commands):
        workflow.execute(command, label+'-extract-'+str(number), duration)
    inventory = rpu_inventory(exported, workflow.guard)
    size, checksum = _payload(payload, workflow.guard)
    _payload(base, workflow.guard)
    result = dict(inventory, configuration=config, source=str(source),
                  primary_stream_index=video['index'], base=str(base), enhancement=str(enhancement),
                  enhancement_video=str(payload), rpu=str(rpu), rpu_export=str(exported),
                  enhancement_video_bytes=size, enhancement_video_sha256=checksum,
                  scope='layer-inventory-only')
    workflow.guard()
    with (directory/'inventory.json').open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    return result


def _payload(path, guard):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as stream:
        while True:
            guard()
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    if not size:
        raise ValueError('Enhancement video payload is empty')
    return size, digest.hexdigest()


def layer_preservation_evidence(source_el, output_el, source_rpu, output_rpu,
                                source_config, output_config, expected_frames,
                                *, guard=lambda: None):
    """Prove exact EL video and ordered RPU semantics, including P7 signaling.

    FEL can be inventoried, but this function does not establish that re-encoding
    its base layer preserves reconstructed pictures. Never use this result alone
    as an eligibility or replacement decision.
    """
    if type(expected_frames) is not int or expected_frames <= 0:
        raise ValueError('Positive decoded frame count required')
    for config in (source_config, output_config):
        profile7_configuration(config)
    if source_config != output_config:
        raise ValueError('Dolby Vision configuration changed')
    source_payload = _payload(source_el, guard)
    if source_payload != _payload(output_el, guard):
        raise ValueError('Enhancement video payload changed')
    before = rpu_inventory(source_rpu, guard)
    after = rpu_inventory(output_rpu, guard)
    if before != after or before['frames'] != expected_frames:
        raise ValueError('Complete ordered RPU metadata or frame coverage changed')
    return dict(before,
                enhancement_video_bytes=source_payload[0],
                enhancement_video_sha256=source_payload[1],
                configuration=dict(output_config), scope='layer-preservation-only')
