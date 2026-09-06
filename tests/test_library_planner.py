import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from library_planner import classify,enumerate_media,scan,probe_with_frame_color
from test_muxmender import sample


class PlannerTests(unittest.TestCase):
    def test_conservative_classification(self):
        info=sample(hdr=False,color_primaries='bt709',color_transfer='bt709',color_space='bt709')
        self.assertEqual(classify(info)[0],'preview-candidate')
        for field in ('color_range','color_space','color_transfer','color_primaries'):
            copy=SimpleNamespace(**info.__dict__);setattr(copy,field,'unknown')
            self.assertEqual(classify(copy)[0],'needs-review')
        info.video_codec='hevc';self.assertEqual(classify(info)[0],'keep-as-is')
        info.hdr=True;self.assertEqual(classify(info)[0],'needs-review')

    def test_scan_writes_only_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'media';source.mkdir();media=source/'fixture.mkv';media.write_bytes(b'unchanged')
            output=root/'report';output.mkdir()
            info=sample(path=str(media),hdr=False)
            with patch('library_planner.mm.probe',return_value=info):
                result=scan(source,output)
            self.assertEqual(result['files'],1)
            self.assertEqual(media.read_bytes(),b'unchanged')
            self.assertEqual(len(list(source.iterdir())),1)
            row=json.loads((output/'files.jsonl').read_text())
            self.assertIsNone(row['savings_estimate'])

    def test_exclude_output_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'reports';output.mkdir();(output/'fixture.mkv').touch();(root/'source.mkv').touch()
            self.assertEqual(enumerate_media(root,(output.resolve(),)),[root/'source.mkv'])

    def test_scan_reports_probe_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.mkv';source.touch();output=root/'out';output.mkdir()
            with patch('library_planner.mm.probe',side_effect=RuntimeError('invalid')):
                self.assertEqual(scan(source,output)['actions'],{'probe-error':1})

    def test_frame_color_evidence_requires_consensus(self):
        for frames,expected in (([{'color_range':'tv'},{'color_range':'tv'}],'tv'),
                                ([{'color_range':'tv'},{}],'unknown'),
                                ([{'color_range':'tv'},{'color_range':'pc'}],'unknown'),
                                ([{'color_range':'tv'}],'unknown')):
            with patch('library_planner.mm.probe',return_value=sample(color_range='unknown')), \
                 patch('library_planner.mm.run_json',return_value={'frames':frames}):
                self.assertEqual(probe_with_frame_color('fixture','ffprobe').color_range,expected)
