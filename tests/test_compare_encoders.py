import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import compare_encoders as benchmark
from test_auto_optimize import source_data


class EncoderComparisonTests(unittest.TestCase):
    def test_higher_quality_cpu_profile_is_bounded_and_explicit(self):
        rows=benchmark.recipes('higher-quality-cpu')
        self.assertEqual(len(rows),6)
        self.assertEqual([r['id'] for r in rows],[
            'libx265-crf17','libx265-crf18','libx265-crf19',
            'libsvtav1-crf12','libsvtav1-crf16','libsvtav1-crf20'])
        for row in rows:
            self.assertEqual(row['options'][-2:],['-threads:v','4'])
        with self.assertRaises(ValueError):benchmark.recipes('unbounded')

    def test_all_seven_encoder_families_and_copy_safety(self):
        rows=benchmark.recipes()
        self.assertEqual(len(rows),14)
        self.assertEqual(len({r['encoder'] for r in rows}),7)
        for row in rows:
            data=source_data();data['streams'][0]['color_range']='pc'
            cmd=benchmark.command(Path('reference'),Path('output'),row,data['streams'])
            self.assertIn('-n',cmd)
            self.assertNotIn('-y',cmd)
            self.assertNotIn('-vf',cmd)
            self.assertNotIn('-r',cmd)
            self.assertEqual(cmd[cmd.index('-color_range')+1],'pc')
            self.assertEqual(cmd[cmd.index('-c')+1],'copy')

    def test_unavailable_encoders_are_reported_without_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);reference=root/'reference.mkv';reference.write_bytes(b'fixture')
            output=root/'output';output.mkdir()
            data=source_data();data['format']['duration']='10'
            with patch.object(benchmark.os,'sched_getaffinity',return_value=set(range(8)),create=True), \
                 patch.object(benchmark.os,'sched_setaffinity',create=True) as affinity, \
                 patch.object(benchmark.ao.Workflow,'probe',return_value=data), \
                 patch.object(benchmark.ao.Workflow,'frame_file',return_value=root/'frames'), \
                 patch.object(benchmark.ao,'compare_frames',return_value=240), \
                 patch.object(benchmark.ao.Workflow,'quality',return_value=dict(mean=99,p5=98)), \
                 patch.object(benchmark.ao.mm,'ffmpeg_encoder_names',return_value=set()), \
                 patch.object(benchmark.ao.Workflow,'execute') as execute:
                self.assertEqual(benchmark.run(reference,output),0)
            affinity.assert_called_once_with(0,[0,1,2,3])
            execute.assert_not_called()
            report=json.loads(next(output.glob('*/comparison.json')).read_text())
            self.assertEqual(len(report['results']),14)
            self.assertTrue(all(r['status']=='unavailable-in-installed-ffmpeg' for r in report['results']))
            self.assertEqual(reference.read_bytes(),b'fixture')
