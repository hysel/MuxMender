import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('full_input',Path(__file__).resolve().parents[1]/'tools/qualify_full_encode_input.py')
module=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class IdleProofTests(unittest.TestCase):
    def test_windows_never_launches_native_research(self):
        with patch.object(module.sys,'platform','win32'):
            with self.assertRaisesRegex(RuntimeError,'only on Linux'):module.main()

    def test_only_full_encode_uses_production_recovery_label(self):
        self.assertEqual(module.full_encode_label('research-full-encode'),'full-encode')
        for label in ('reference-0','sample-encode','full-encode-audio-recovery-video'):
            self.assertEqual(module.full_encode_label(label),label)

    def test_only_fresh_idle_proof_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'idle.json'
            for state,valid in [
                (dict(ready=True,updated=time.time(),counts={}),True),
                (dict(ready=True,updated=time.time()-20,counts={}),False),
                (dict(ready=True,updated=time.time(),counts={'running':1}),False),
                (dict(ready=True,updated=time.time(),counts={'pending':1}),False),
                (dict(ready=False,updated=time.time(),counts={}),False),
            ]:
                path.write_text(json.dumps(state))
                if valid:module.idle_guard(path)
                else:
                    with self.assertRaises(RuntimeError):module.idle_guard(path)


if __name__=='__main__':unittest.main()
