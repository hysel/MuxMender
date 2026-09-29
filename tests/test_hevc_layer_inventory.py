import importlib.util
from pathlib import Path
import unittest
import subprocess
import sys
import tempfile
from unittest.mock import patch
import hevc_inventory

spec=importlib.util.spec_from_file_location('hevc_inventory',Path(__file__).parents[1]/'tools/inspect_hevc_layers.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class InventoryTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux','Subprocess reader tests execute remotely on Linux')
    def test_shared_reader_requires_clean_eof_and_can_stop_on_presence(self):
        real_popen=subprocess.Popen
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.bin';source.write_bytes(b'unchanged fixture')
            def process(script):
                return lambda command,**kwargs:real_popen([sys.executable,'-c',script],**kwargs)
            script="import sys;sys.stdout.buffer.write(b'\\x00\\x00\\x01\\x02\\x01payload')"
            with patch('hevc_inventory.subprocess.Popen',side_effect=process(script)):
                evidence=hevc_inventory.inspect_source('ffmpeg',source,root)
            self.assertTrue(hevc_inventory.absent_dv(evidence))
            script+=";sys.stderr.write('decode error')"
            with patch('hevc_inventory.subprocess.Popen',side_effect=process(script)),self.assertRaisesRegex(ValueError,'errors'):
                hevc_inventory.inspect_source('ffmpeg',source,root)
            script="import sys;sys.stdout.buffer.write(b'\\x00\\x00\\x01\\x7c\\x01metadata')"
            with patch('hevc_inventory.subprocess.Popen',side_effect=process(script)):
                evidence=hevc_inventory.inspect_source('ffmpeg',source,root)
            self.assertFalse(evidence['complete_bitstream'])
            self.assertEqual(evidence['rpu_nals'],1)
            self.assertFalse(hevc_inventory.absent_dv(evidence))
            self.assertEqual(source.read_bytes(),b'unchanged fixture')

    def test_every_chunk_boundary_has_identical_counts(self):
        raw=b'\x00\x00\x00\x01\x02\x01payload\x00\x00\x01\x7c\x01rpu\x00\x00\x01\x02\x09enhancement'
        for size in range(1,len(raw)+1):
            inventory=module.Inventory()
            for start in range(0,len(raw),size):inventory.feed(raw[start:start+size])
            result=inventory.finish()
            self.assertEqual(result['rpu_nals'],1)
            self.assertEqual(result['potential_enhancement_nals'],1)
            self.assertEqual(sum(row['count'] for row in result['nal_counts']),3)

    def test_invalid_and_truncated_headers_never_establish_absence(self):
        for raw in (b'',b'\x00\x00\x01\x02',b'\x00\x00\x01\x82\x01',b'\x00\x00\x01\x02\x00'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                inventory=module.Inventory();inventory.feed(raw);inventory.finish()
