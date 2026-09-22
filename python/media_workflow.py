"""Shared automatic-workflow adapter for the standalone CLI and app queue.

Encoding, admission, metadata preservation, scoring and validation are owned by
auto_optimize, never reimplemented by this adapter or a UI.
"""
import argparse
import math
import os
import sys
import time
from pathlib import Path


def file_age_settings(unit='all', value=None):
    if unit == 'all':
        return dict(age_unit='all', age_value=None)
    if unit not in ('hours', 'days', 'weeks') or type(value) is not int or not 1 <= value <= 100000:
        raise ValueError('File age requires 1–100000 whole hours, days or weeks')
    return dict(age_unit=unit, age_value=value)


def creation_time(path):
    """Actual filesystem birth time; never substitute Unix metadata-change time."""
    stat = Path(path).stat()
    birth = getattr(stat, 'st_birthtime', None)
    if birth is None and os.name == 'nt':
        birth = stat.st_ctime  # Older Windows Python exposes creation here.
    if birth is None and sys.platform.startswith('linux'):
        import ctypes
        import struct
        try:
            statx = ctypes.CDLL(None, use_errno=True).statx
            statx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_uint, ctypes.c_void_p]
            statx.restype = ctypes.c_int
            buffer = ctypes.create_string_buffer(256)
            if statx(-100, os.fsencode(path), 0x100, 0x800, buffer) == 0:
                mask = struct.unpack_from('=I', buffer.raw)[0]
                if mask & 0x800:
                    seconds, nanos = struct.unpack_from('=qI', buffer.raw, 80)
                    birth = seconds + nanos / 1e9
        except (AttributeError, OSError):
            pass
    return birth if birth is not None and math.isfinite(birth) else None


def file_age_match(path, settings, now=None):
    age = file_age_settings(settings.get('age_unit', 'all'), settings.get('age_value'))
    if age['age_unit'] == 'all':
        return True, None
    birth = creation_time(path)
    if birth is None:
        return False, 'creation_date_unavailable'
    now = time.time() if now is None else now
    seconds = age['age_value'] * {'hours': 3600, 'days': 86400, 'weeks': 604800}[age['age_unit']]
    return (True, None) if now-seconds <= birth <= now else (False, 'outside_age_window')


def automatic_arguments(source, output, settings, *, min_free_gib=12, capability_cache_dir=None):
    mode=settings['mode']
    if mode not in ('analyze','test','encode','replace'):
        raise ValueError('This operation does not launch an encoding worker')
    args=[str(source),'--output-dir',str(output),'--hardware',settings['hardware'],
          '--minimum-savings-percent',format(float(settings['minimum_savings']),'.15g'),
          '--min-free-gib',str(min_free_gib)]
    if capability_cache_dir is not None:args+=['--capability-cache-dir',str(capability_cache_dir)]
    if settings['codecs']:args+=['--playback-verified-codecs',*settings['codecs']]
    if settings['quality']!='auto':args+=['--qualities',settings['quality']]
    else:args+=['--adaptive']
    if settings.get('legacy_color','inspect')!='inspect':args+=['--legacy-color',settings['legacy_color']]
    if mode in ('test','encode','replace'):args+=['--execute']
    if mode in ('encode','replace'):args+=['--encode-best']
    # Replacement authorization/publication belongs to the shared journaled
    # publisher, never to the encoder worker. This worker always makes a copy.
    return args


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--capability-cache-dir',type=Path)
    parser.add_argument('--mode',choices=('analyze','test','encode'),default='analyze')
    parser.add_argument('--hardware',choices=('auto','nvidia','amd','intel'),default='auto')
    parser.add_argument('--quality',choices=('auto','transparent','balanced','compact'),default='auto')
    parser.add_argument('--playback-verified-codecs',nargs='+',choices=('hevc','av1'),default=[])
    parser.add_argument('--minimum-savings-percent',type=float,default=0)
    parser.add_argument('--legacy-color',choices=('inspect','bt709-limited'),default='inspect')
    parser.add_argument('--age-unit', choices=('all','hours','days','weeks'), default='all')
    parser.add_argument('--age-value', type=int)
    args=parser.parse_args(argv)
    try:
        age = file_age_settings(args.age_unit, args.age_value)
        selected, reason = file_age_match(args.source, age)
    except ValueError as exc:
        parser.error(str(exc))
    if not selected:
        print('Not queued: '+reason.replace('_',' '))
        return 0
    if args.mode!='analyze' and not args.playback_verified_codecs:
        parser.error('Select at least one playback-verified codec before testing or encoding')
    from auto_optimize import main as execute
    return execute(automatic_arguments(args.source,args.output_dir,dict(mode=args.mode,
        hardware=args.hardware,quality=args.quality,codecs=args.playback_verified_codecs,
        minimum_savings=args.minimum_savings_percent,legacy_color=args.legacy_color),
        capability_cache_dir=args.capability_cache_dir))


if __name__=='__main__':raise SystemExit(main())
