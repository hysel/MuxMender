from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import research_hdr_sdr as research


class HDRSDRResearchTests(unittest.TestCase):
    def test_renderer_uses_real_tone_mapping_and_shared_geometry(self):
        video=dict(width=3840,height=2160,sample_aspect_ratio='1:1')
        for tone in research.TONES:
            graph=research.render_filter(video,'tv1080',tone)
            self.assertIn('zscale=t=linear',graph)
            self.assertIn('tonemap=tonemap='+tone,graph)
            self.assertIn('sidedata=mode=delete',graph)
            self.assertIn('scale=1920:1080',graph)
        with self.assertRaises(ValueError):research.render_filter(video,'tv1080','unknown')

    def test_failure_cleans_only_own_lossless_scratch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            reference=root/'scene-1-tv1080-hable-reference.mkv'
            output=root/'scene-1-tv1080-hable.mkv'
            other=root/'unrelated-reference.mkv'
            for path in (reference,output,other):path.write_bytes(b'fixture')
            with patch.object(research,'run',side_effect=RuntimeError('fixture')):
                with self.assertRaises(RuntimeError):research.run_with_cleanup(root)
            self.assertFalse(reference.exists())
            self.assertTrue(output.exists());self.assertTrue(other.exists())
