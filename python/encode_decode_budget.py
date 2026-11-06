"""Measured software-decoder feed budget for NVENC, separate from quality pools.

Only the source decode worker count changes. Encoder settings, comparison
filters, score thresholds and complete output validation are unchanged.
"""
from pathlib import Path

from adaptive_resources import cpu_room, finite, memory_room, pressure_ok
from resource_governor import SDRWorkerBudget


def qualified_encode(command, video, hdr_mode, source=None, output_preset='original', hdr_policy='preserve'):
    """Unmeasured media keeps its ordinary decoder budget; never reject it."""
    if (not command or not isinstance(video, dict) or Path(str(command[0])).stem.lower() != 'ffmpeg'
            or output_preset != 'original' or hdr_policy != 'preserve'
            or hdr_mode not in ('pq', 'hdr10', 'hdr10plus')
            or video.get('codec_name') != 'hevc'
            or video.get('pix_fmt') != 'yuv420p10le'
            or video.get('field_order') != 'progressive'
            or video.get('color_transfer') != 'smpte2084'
            or any(type(video.get(k)) is not int or not 0 < video[k] <= limit
                   for k, limit in (('width', 3840), ('height', 2160)))):
        return False
    # The metadata belongs to the original. Do not apply it to a recovered
    # lossless clip, tone-mapped intermediate or an unverified source view.
    inputs = [command[i+1] for i, key in enumerate(command[:-1]) if key == '-i']
    if source is None or len(inputs) != 1:
        return False
    try:
        original = Path(source).resolve(strict=True)
        if not original.is_file() or Path(inputs[0]).resolve(strict=True) != original:
            return False
    except (OSError, ValueError, TypeError):
        return False
    filters = [str(command[i+1]) for i, key in enumerate(command[:-1])
               if key in ('-vf', '-filter:v', '-filter:v:0', '-filter_complex', '-lavfi')]
    if ('-show_frames' in command or any(key == '-f' and command[i+1] == 'framehash'
            for i, key in enumerate(command[:-1]))
            or any(word in graph for graph in filters for word in ('libvmaf', 'tonemap', 'libplacebo'))):
        return False
    return any((str(key) in ('-c:v', '-codec:v', '-vcodec')
                or str(key).startswith(('-c:v:', '-codec:v:')))
               and str(command[i+1]).endswith('_nvenc') for i, key in enumerate(command[:-1]))


def decoder_budget(data, allocation, ceiling):
    """Select the measured four-worker feed only with free, bounded resources."""
    effective = allocation.get('effective_cpus')
    room = cpu_room(data)
    if (not finite(effective) or effective < 8 or type(ceiling) is not int or ceiling < 4
            or room is None or not pressure_ok(data) or not memory_room(data, 4)
            or type(data.get('app_cpu_scope')) is not bool
            or type(data.get('container_tasks')) is not int or data['container_tasks'] < 0):
        return 2
    if 'container_task_limit' in data:
        available = data.get('container_tasks_available')
        if not finite(available) or available < 16:
            return 2
    # cpu_room excludes external demand. Also leave room for active app work;
    # the atomic stage lease will recheck and reserve the actual four workers.
    own = data['cpus'] * data['container_cpu_percent'] / 100 if data.get('app_cpu_scope') is True else 0
    available = min(effective, room) - own
    return 4 if available >= 6 else 2


class EncodeDecoderBudget(SDRWorkerBudget):
    """Reuse the cancellable, five-second CPU/memory sampler; no GPU probing."""
    def select(self, data):
        from cpu_allocation import capacity, scoring_ceiling
        return decoder_budget(data, capacity(), scoring_ceiling(4))
