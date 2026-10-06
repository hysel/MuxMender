"""Pure Docker-context transport checks; never execute a native image locally."""
import hashlib
from pathlib import Path
import tarfile
import tempfile
import unittest
import sys
import json
from unittest.mock import patch
from types import SimpleNamespace
from tools.stage_reader_integration import write_context
from tools.benchmark_shared_gpu_reader import finish_report


class ImageStageTests(unittest.TestCase):
    def test_success_is_published_after_cleanup_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owned=root/'generated-control';owned.write_bytes(b'owned')
            retained=root/'small-log';retained.write_bytes(b'evidence')
            events=[]
            def save(**values):
                self.assertFalse(owned.exists())
                self.assertTrue((root/'benchmark.json').is_file())
                events.append(values)
            report=dict(shared_engine_passed=True)
            finish_report(SimpleNamespace(save=save),report,root,[owned])
            self.assertEqual(events[-1]['state'],'completed')
            self.assertEqual(report['temporary_bytes_removed'],5)
            self.assertEqual(retained.read_bytes(),b'evidence')

    def test_cleanup_or_evidence_failure_never_publishes_success(self):
        for operation in ('unlink','write_text'):
            with self.subTest(operation=operation),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);owned=root/'generated-control';owned.write_bytes(b'owned')
                events=[];report=dict(shared_engine_passed=True)
                with patch.object(Path,operation,side_effect=PermissionError('generated fault')):
                    with self.assertRaises(PermissionError):
                        finish_report(SimpleNamespace(save=lambda **values:events.append(values)),report,root,[owned])
                self.assertEqual(events[-1]['state'],'failed')
                self.assertIn('cleanup_or_evidence_error',report)
                self.assertFalse(any(row['state']=='completed' for row in events))

    def test_existing_failure_is_not_changed_to_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            events=[];root=Path(directory)
            finish_report(SimpleNamespace(save=lambda **values:events.append(values)),dict(error='reader failure'),root,[])
            self.assertEqual(events,[])
            self.assertEqual(json.loads((root/'benchmark.json').read_text())['error'],'reader failure')

    @unittest.skipUnless(sys.platform.startswith('linux'),'Native research entrypoints run only on Linux')
    def test_preflight_failure_is_tracked_before_any_native_process(self):
        import benchmark_shared_gpu_reader as benchmark
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);binary=root/'neutral-binary';binary.write_bytes(b'non-executable fixture')
            receipt=root/'receipt.json';receipt.write_text(json.dumps(dict(binary_sha256='0'*64)))
            output=root/'result'
            argv=['benchmark','--binary',str(binary),'--receipt',str(receipt),'--output',str(output)]
            with patch.object(sys,'argv',argv),patch.object(benchmark.subprocess,'run') as process:
                with self.assertRaisesRegex(ValueError,'does not match'):benchmark.main()
                process.assert_not_called()
            record=json.loads(next((output/'reports').glob('*/job.json')).read_text())
            self.assertEqual(record['state'],'failed')
            self.assertIn('does not match',json.loads((output/'benchmark.json').read_text())['error'])
            self.assertEqual(binary.read_bytes(),b'non-executable fixture')

    def test_portable_context_is_exclusive_and_checks_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'fixture.py'
            source.write_bytes(b'print("generated control")\r\n')
            archive=root/'context.tar'
            write_context(archive,{'python/fixture.py':source})
            with tarfile.open(archive) as context:
                item=context.getmember('python/fixture.py')
                self.assertEqual(item.uid,0);self.assertEqual(item.mode,0o644)
                payload=context.extractfile(item).read()
                self.assertNotIn(b'\r',payload)
                checks=context.extractfile('context.sha256').read().decode()
                self.assertEqual(checks,hashlib.sha256(payload).hexdigest()+'  python/fixture.py\n')
            with self.assertRaises(FileExistsError):write_context(archive,{'python/fixture.py':source})

    def test_image_does_not_mount_library_or_run_app_service(self):
        root=Path(__file__).resolve().parents[1]
        recipe=(root/'deploy/truenas/Dockerfile.reader-integration').read_text()
        launch=(root/'deploy/truenas/launch-reader-integration.sh').read_text()
        self.assertIn('--installed-profile',recipe)
        self.assertIn('--full-validation',recipe)
        self.assertIn('"/usr/bin/tini", "-s", "--"',recipe)
        self.assertNotIn('app_service',recipe)
        self.assertNotIn('dst=/media',launch)
        self.assertIn('--read-only --network none',launch)
        self.assertIn('--pid=container:muxmender-research',launch)
        self.assertIn('docker tag "$base" "$alias"',launch)
        self.assertIn('research-dependency.json',launch)
        self.assertIn('state.get("state")!="completed"',launch)
        self.assertIn('processes="$(docker top muxmender-research -eo pid,comm)"',launch)
        self.assertNotIn('docker top muxmender-research -eo comm',launch)
