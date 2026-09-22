"""Read-only revalidation of retained encodes inside the isolated research lab.

Never publishes, alters either input, or cleans pre-existing intermediates.
"""
import argparse
import json
import time
from pathlib import Path
from types import SimpleNamespace

import auto_optimize as ao


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--timing-only', action='store_true')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    plan = json.loads((args.run/'plan.json').read_text())
    source = Path(plan['source'])
    output = args.run/'full-hevc.mkv'
    identities = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in (source, output)}
    def guard():
        for path, identity in identities.items():
            if (path.stat().st_size, path.stat().st_mtime_ns) != identity:
                raise ValueError('Research input changed: '+str(path))
    workflow = ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg', ffprobe='ffprobe', timeout=14400),
                           args.work, guard)
    started = time.time()
    before = workflow.probe(source)
    # Reapply the existing run's disclosed color interpretation for metadata
    # comparison only. Fresh decoded source frames remain independent evidence.
    for key, value in (plan.get('color_inspection') or {}).get('effective', {}).items():
        if value is None:
            before['streams'][0].pop(key, None)
        else:
            before['streams'][0][key] = value
    reference = workflow.frame_file(source, 'fresh-source', before['format'])
    if args.timing_only:
        after = workflow.probe(output)
        frames = workflow.frame_file(output, 'fresh-output', after['format'])
        count = workflow.compare_frame_files(reference, frames)
        result = dict(frame_timing_passed=True, frames=count,
                      source_rate=before['streams'][0].get('avg_frame_rate'),
                      output_rate=after['streams'][0].get('avg_frame_rate'),
                      full_validation_passed=False)
    else:
        count = workflow.validate(source, output, before, 'hevc', 'retained', reference)
        result = dict(full_preservation_validation_passed=True, frames=count,
                      quality_retested=False, publication_authorized=False)
    guard()
    result.update(elapsed_seconds=time.time()-started, source=str(source), output=str(output),
                  size_reduction_percent=100*(1-output.stat().st_size/source.stat().st_size))
    (args.work/'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
