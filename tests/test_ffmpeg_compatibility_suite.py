import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('compatibility',ROOT/'tools/ffmpeg_compatibility_suite.py')
suite=importlib.util.module_from_spec(spec);spec.loader.exec_module(suite)


class CompatibilitySuiteTests(unittest.TestCase):
    def ledger(self):
        return {'schema':1,'fixes':[{'id':'FF-001','tests':['test_ffmpeg_compatibility_suite.py']}]}

    def test_explicit_external_ledger_loads(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.json'
            path.write_text(json.dumps(self.ledger()))
            self.assertEqual(suite.load_ledger(path),self.ledger())

    def test_no_reproducer_or_missing_regressions_cannot_retire_workaround(self):
        fix={'kind':'upstream-workaround','raw_scenario':'fixture'}
        self.assertIn('full-file',suite.disposition(fix,{'passed':False},{'passed':True,'negative_controls_passed':True},True))
        self.assertIn('negative-control',suite.disposition(fix,{'passed':False},{'passed':True},True))
        self.assertIn('retain',suite.disposition(fix,{'passed':False},{'passed':True},False))
        self.assertIn('baseline did not reproduce',suite.disposition(fix,{'passed':True},{'passed':True},True))
        self.assertIn('coverage gap',suite.disposition(fix,None,{'passed':True},True))
        self.assertIn('execution unavailable',suite.disposition(fix,{'error':'missing codec'},{'passed':True},True))
        self.assertIn('retain',suite.disposition(fix,{'passed':False},{'passed':False},True))

    def test_protections_and_application_fixes_are_never_upstream_removal_candidates(self):
        for kind in ('permanent-protection','application-fix','application-performance','withdrawn-experiment'):
            self.assertEqual(suite.disposition({'kind':kind},{'passed':False},{'passed':True},True),
                             'application-or-protection: retain')

    def test_unsafe_manifest_patterns_and_duplicate_ids_are_rejected(self):
        ledger=self.ledger()
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'ledger.json'
            ledger['fixes'][0]['tests']=['../../private.py'];path.write_text(json.dumps(ledger))
            with self.assertRaisesRegex(ValueError,'Unsafe'):suite.load_ledger(path)
            ledger=self.ledger();ledger['fixes'].append(ledger['fixes'][0])
            path.write_text(json.dumps(ledger))
            with self.assertRaisesRegex(ValueError,'duplicate'):suite.load_ledger(path)

    def test_native_execution_is_blocked_on_windows(self):
        with patch.object(suite.sys,'platform','win32'),patch.object(suite.subprocess,'run') as execute:
            with self.assertRaisesRegex(RuntimeError,'Linux-only'):suite.main()
            execute.assert_not_called()

    def test_pcm_negative_controls_reject_empty_changed_and_truncated_audio(self):
        self.assertTrue(suite.pcm_equal(b'\x01\x02',b'\x01\x02'))
        for before,after in ((b'',b''),(b'\x01\x02',b'\x01'),(b'\x01\x02',b'\x02\x02')):
            self.assertFalse(suite.pcm_equal(before,after))
