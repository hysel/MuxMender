import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from dv_fel_runtime import child_environment,validate_worker


class FelRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.plugin=self.root/'libfelbaker.so'
        self.plugin.write_bytes(b'placeholder fixture, not executable')
        (self.root/'prefix/lib').mkdir(parents=True);(self.root/'prefix/python').mkdir()
        self.data=dict(schema='muxmender-fel-runtime-v1',plugin_sha256=hashlib.sha256(self.plugin.read_bytes()).hexdigest(),
                       library_dir='prefix/lib',python_dir='prefix/python',python_version=list(sys.version_info[:2]),required_cpu_features=['avx2'])
        self.save()

    def save(self):(self.root/'runtime.json').write_text(json.dumps(self.data))

    def test_scoped_environment_keeps_parent_unchanged(self):
        parent={'PATH':'/bin','PYTHONPATH':'/app'}
        result=child_environment(self.plugin,parent)
        self.assertEqual(parent,{'PATH':'/bin','PYTHONPATH':'/app'})
        self.assertTrue(result['PYTHONPATH'].startswith(str(self.root/'prefix/python')))
        self.assertEqual(result['PYTHONNOUSERSITE'],'1')

    def test_escaped_path_and_modified_library_are_rejected(self):
        self.data['library_dir']='..';self.save()
        with self.assertRaisesRegex(ValueError,'escapes'):child_environment(self.plugin,{})
        self.plugin.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'differs'):child_environment(self.plugin,{})

    def test_python_abi_and_cpu_features_checked_before_plugin_load(self):
        with patch('dv_fel_runtime.sys.platform','linux'),patch('dv_fel_runtime.platform.machine',return_value='x86_64'),patch('dv_fel_runtime.cpu_features',return_value={'avx2'}):
            validate_worker(self.plugin)
            self.data['python_version']=[2,7];self.save()
            with self.assertRaisesRegex(RuntimeError,'ABI'):validate_worker(self.plugin)
        self.data['python_version']=list(sys.version_info[:2]);self.save()
        with patch('dv_fel_runtime.sys.platform','linux'),patch('dv_fel_runtime.platform.machine',return_value='x86_64'),patch('dv_fel_runtime.cpu_features',return_value=set()):
            with self.assertRaisesRegex(RuntimeError,'instructions'):validate_worker(self.plugin)

    def test_unmanifested_manual_runtime_remains_explicit(self):
        # A separate location without a manifest must not inherit this manifest.
        directory=self.root/'manual';directory.mkdir();plugin=directory/'plugin.so';plugin.write_bytes(b'fixture')
        self.assertEqual(child_environment(plugin,{'PATH':'/bin'}),{'PATH':'/bin'})
