import tempfile
import unittest
from pathlib import Path
from fractions import Fraction
from hdr10plus_preserve import write_decoded_timestamps

class DecodedHDRTimestampTests(unittest.TestCase):
    def test_preserves_decoded_start_and_vfr_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'timestamps.txt'
            frames=[{'pts_time':v} for v in ('0.200','0.242','0.283','2.700','2.867')]
            self.assertEqual(write_decoded_timestamps(frames,p),5)
            values=[Fraction(v)/1000 for v in p.read_text().splitlines()[1:]]
            self.assertEqual(values,[Fraction(f['pts_time']) for f in frames])

    def test_rejects_missing_nonfinite_duplicate_and_reversed(self):
        for frames in ([],[{}],[{'pts_time':'NaN'}],[{'pts_time':'inf'}],
                       [{'pts_time':'1'},{'pts_time':'1'}],
                       [{'pts_time':'1'},{'pts_time':'0'}]):
            with self.subTest(frames=frames),tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    write_decoded_timestamps(frames,Path(folder)/'timestamps.txt')

    def test_never_overwrites_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'timestamps.txt';p.write_text('original')
            with self.assertRaises(FileExistsError):write_decoded_timestamps([{'pts_time':'0'}],p)
            self.assertEqual(p.read_text(),'original')
