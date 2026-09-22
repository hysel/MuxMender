import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('coverage_audit', Path(__file__).parents[1]/'tools/research_coverage.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CoverageTests(unittest.TestCase):
    def test_explicit_keep_is_an_accounted_retention_decision(self):
        jobs=[dict(source='/media/a.mkv',signature=[100,1],state='kept-original',created=1)]
        self.assertEqual(audit.classify('/media/a.mkv',[100,1],jobs)['category'],'retained_decision')

    def test_skipped_symlink_directory_is_not_reported_as_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            with patch.object(audit.os,'walk',return_value=[(str(root),['external'],[])]), \
                 patch.object(Path,'is_symlink',lambda path:path.name=='external'):
                report=audit.audit(root,[])
            self.assertFalse(report['inventory_complete'])
            self.assertEqual(report['excluded_symlink_directories'],[str(root/'external')])

    def test_queued_retry_retains_last_failure_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'a.mkv';path.write_bytes(b'fixture')
            stamp=audit.signature(path)
            jobs=[dict(source=str(path),signature=stamp,state=state,reason=reason,created=i)
                  for i,(state,reason) in enumerate((('failed','Track timing mismatch'),('pending',None)))]
            report=audit.audit(Path(folder),jobs)
            self.assertEqual(report['historical_failures'][0]['latest_failure_reason'],'Track timing mismatch')
            self.assertEqual(report['files'][0]['category'],'queued')

    def test_replacement_alias_and_stale_history(self):
        jobs = [dict(source='/media/a.mp4', published_path='/media/a.mkv', state='replaced',
                     signature=[100, 1], published_signature=[50, 2], created=1)]
        self.assertEqual(audit.classify('/media/a.mkv', [50, 2], jobs)['category'], 'converted')
        self.assertEqual(audit.classify('/media/a.mkv', [51, 3], jobs)['category'], 'stale_history')
        self.assertEqual(audit.classify('/media/b.mkv', [50, 2], jobs)['category'], 'never_processed')

    def test_new_failed_attempt_not_hidden_by_old_skip(self):
        jobs = [dict(source='/media/a.mkv', signature=[100, 1], state=state, created=i)
                for i, state in enumerate(('skipped', 'failed'))]
        self.assertEqual(audit.classify('/media/a.mkv', [100, 1], jobs)['category'], 'unresolved_failure')
