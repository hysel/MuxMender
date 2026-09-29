import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import dv_full_file as full
from dv_workflow import whole_source_sample


class ShortDVTests(unittest.TestCase):
    def test_preflight_uses_actual_short_source_not_thirty_seconds(self):
        for duration in (.5,4.5,29,60):
            with self.subTest(duration=duration),tempfile.TemporaryDirectory() as tmp:
                args=SimpleNamespace(work_dir=Path(tmp),source=Path('generated.mkv'),
                    ffmpeg='ffmpeg',ffprobe='ffprobe',dovi_tool='dovi_tool',min_savings=0)
                def sample(options):
                    self.assertEqual(options.seconds,min(duration,30))
                    self.assertEqual(options.whole_source,duration<30)
                    if duration<30:self.assertEqual(options.start,0)
                    output=options.work_dir/'dv81-generated';output.mkdir()
                    (output/'validation.json').write_text(json.dumps(dict(
                        status='verified-structure-awaiting-visual-review',original_stat_unchanged=True,
                        original_video_bytes=100,output_video_bytes=50,quality={'candidate':{'passed':True}})))
                    return 0
                with patch.object(full.dv,'run',side_effect=sample):
                    self.assertTrue(full.nvidia_savings_preflight(args,duration)['eligible'])

    def test_whole_reference_requires_hash_size_and_all_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene=Path(tmp);output=scene/'generated.mkv';output.write_bytes(b'fixture')
            evidence=dict(frames=24,output=str(output),whole_source_reference=dict(sha256='a'*64,bytes=100,frames=24))
            sample={}
            self.assertEqual(whole_source_sample(evidence,'a'*64,100,scene,sample),('a'*64,100,24))
            self.assertEqual(sample['bytes'],7)
            for key,value in [('sha256','b'*64),('bytes',99),('frames',23),('frames',True)]:
                original=evidence['whole_source_reference'][key]
                evidence['whole_source_reference'][key]=value
                with self.assertRaises(ValueError):whole_source_sample(evidence,'a'*64,100,scene,{})
                evidence['whole_source_reference'][key]=original

    def test_output_must_belong_to_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);scene=root/'scene';scene.mkdir()
            output=root/'outside.mkv';output.write_bytes(b'fixture')
            e=dict(frames=24,output=str(output),whole_source_reference=dict(sha256='a'*64,bytes=100,frames=24))
            with self.assertRaisesRegex(ValueError,'escapes'):whole_source_sample(e,'a'*64,100,scene,{})
