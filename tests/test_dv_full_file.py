import json
import tempfile
import unittest
from pathlib import Path
from dv_full_file import rpu_digest, mux_command


class FullDVTests(unittest.TestCase):
    def test_rpu_streamed_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'rpu.json'
            p.write_text(json.dumps([{'x': 'a'*70000, 'rpu_data_crc32': 1}, {'x':2}]))
            first = rpu_digest(p)
            self.assertEqual(first[0],2)
            p.write_text(json.dumps([{'x': 'a'*70000, 'rpu_data_crc32': 9}, {'x':2}]))
            self.assertEqual(first,rpu_digest(p))
            p.write_text(json.dumps([{'x':2}, {'x':'a'*70000}]))
            self.assertNotEqual(first,rpu_digest(p))

    def test_bad_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'rpu.json'
            for value in ('{}','[{},]','[{} {}]','[{}]oops','[{','[1]'):
                p.write_text(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    rpu_digest(p)

    def test_full_mux_does_not_trim_or_overwrite(self):
        cmd = mux_command('ffmpeg','original','injected','fresh','24000/1001')
        for flag in ('-t','-ss','-shortest','-y'):
            self.assertNotIn(flag,cmd)
        self.assertIn('-n',cmd)
        self.assertEqual(cmd[cmd.index('-map_chapters')+1],'1')
