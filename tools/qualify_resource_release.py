"""Isolated Linux integration checks for the resource/performance release."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest


def main():
    if sys.platform!='linux':raise RuntimeError('Run this integration package on Linux')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output=args.output.resolve()
    temporary=args.output/'test-tmp'
    temporary.mkdir(parents=True,exist_ok=True)
    # Queue tests exercise the real scratch-space guard. Container /tmp may be
    # a small tmpfs even when the dedicated research workspace has ample space.
    tempfile.tempdir=str(temporary)
    root=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(root),str(root/'python'),str(root/'tests')]
    from job_tracking import tracked_call
    modules=['test_resource_yield','test_cooperative_pause','test_resource_governor',
             'test_cpu_allocation','test_sdr_worker_integration','test_quality_thread_budget',
             'test_gpu_activity','test_control_service','test_webui',
             'test_gpu_sharing_autosave_ui','test_restart_recovery','test_restart_service',
             'test_gpu_encode_input','test_ffmpeg9_runtime_audit','test_copy_approval_ui']
    def run():
        suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        import json
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/'result.json').write_text(json.dumps(dict(tests=result.testsRun,
            failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
            passed=result.wasSuccessful(),scope='Isolated generated integration; not final-image or real external-app contention qualification'),indent=2))
        return 0 if result.wasSuccessful() else 1
    return tracked_call(run,'Release integration: FFmpeg 9 and dynamic resources',args.output/'reports')


if __name__=='__main__':raise SystemExit(main())
