import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from dv_single import encode_candidate


class SingleLayerTests(unittest.TestCase):
    def test_bad_labels_or_codec_never_probe_or_encode(self):
        work=SimpleNamespace(probe=Mock())
        for label,codec in [('../escape','hevc'),('candidate','av1'),('','hevc')]:
            with self.assertRaises(ValueError):encode_candidate(work,'absent.mkv',dict(codec=codec),label)
        work.probe.assert_not_called()
