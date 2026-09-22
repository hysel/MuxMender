"""Explicit three-scene DV research using shared sampling and quality services.

Does not enable automatic DV routing or authorize source publication.
"""
import argparse
import json
import math
from pathlib import Path
from types import SimpleNamespace

from auto_optimize import sample_positions
import dv_preservation_test as dv
import muxmender as mm
from mux_integrity import savings_decision


def assess(reports, minimum):
    if len(reports) != 3:
        raise ValueError('Three scene reports required')
    for report in reports:
        if (not report.get('status', '').startswith('verified') or
                report.get('original_stat_unchanged') is not True):
            raise ValueError('Incomplete scene preservation evidence')
        for key in ('original_video_bytes', 'output_video_bytes'):
            if type(report.get(key)) is not int or report[key] <= 0:
                raise ValueError('Invalid scene byte evidence')
    decision = savings_decision(sum(r['original_video_bytes'] for r in reports),
                                sum(r['output_video_bytes'] for r in reports), minimum)
    quality = all(r.get('quality', {}).get('self', {}).get('passed') is True and
                  r.get('quality', {}).get('candidate', {}).get('passed') is True
                  for r in reports)
    decision.update(quality_passed=quality, publication_authorized=False,
                    scope='Three-scene video payload estimate, not full-file savings')
    if not quality:
        decision.update(eligible=False, reason='At least one scene lacks passing quality evidence')
    return decision


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--cq', type=int, required=True)
    parser.add_argument('--combined', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--dovi-tool', required=True)
    parser.add_argument('--minimum-savings-percent',type=float,default=25,
                        help='Aggregate sample video-payload savings target; default 25 percent')
    args = parser.parse_args(argv)
    if not math.isfinite(args.minimum_savings_percent) or not 0<=args.minimum_savings_percent<100:
        parser.error('Minimum savings must be finite and in [0,100)')
    if not 18<=args.cq<=32:
        parser.error('Research CQ must be between 18 and 32')
    return args


def main(argv=None):
    args = parse_args(argv)
    info = mm.probe(args.source, 'ffprobe')
    positions = sample_positions(info.duration_seconds, 10)
    print('Three 10-second scenes:', positions, flush=True)
    if not args.execute:
        return
    root = args.work_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    reports = []
    for number, start in enumerate(positions):
        scene = root / str(number)
        scene.mkdir()
        options = SimpleNamespace(source=args.source, execute=True,
            experimental_nvidia=True, experimental_intel=False,
            experimental_hdr10plus=args.combined, nvenc_cq=args.cq,
            seconds=10, start=start, work_dir=scene, measure_quality=True,
            minimum_savings_percent=args.minimum_savings_percent, ffmpeg='ffmpeg', ffprobe='ffprobe',
            dovi_tool=args.dovi_tool, overall_offset=number*100/3, overall_span=100/3)
        result = dv.run(options)
        paths = list(scene.glob('dv81-*/validation.json'))
        if result or len(paths) != 1:
            raise ValueError('Scene processing failed; inspect retained report')
        reports.append(json.loads(paths[0].read_text()))
    decision = assess(reports, args.minimum_savings_percent)
    (root / 'qualification.json').write_text(json.dumps(dict(
        decision=decision, positions=positions, scenes=reports), indent=2))
    print(json.dumps(decision), flush=True)


if __name__ == '__main__':
    main()
