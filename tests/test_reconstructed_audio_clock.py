import tempfile
import unittest
from pathlib import Path
from packet_validation import reconstructed_audio_timestamp_case
from auto_optimize import Workflow
from types import SimpleNamespace
from unittest.mock import patch,Mock


class ReconstructedClockTests(unittest.TestCase):
    def test_workflow_requires_independent_pcm_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'source-packets';b=root/'output-packets'
            (root/'source.mkv').write_bytes(b'source fixture')
            (root/'copy.mkv').write_bytes(b'output fixture')
            def row(i,pts):return f'pts_time={pts}|dts_time={pts}|data_hash=SHA256:{str(i)*64}\n'
            a.write_text(row(1,'0')+row(2,'N/A')+row(3,'0.002'))
            b.write_text(row(1,'0')+row(2,'0.001')+row(3,'0.002'))
            info={'streams':[{'index':0,'codec_type':'video','codec_name':'hevc'},
                             {'index':1,'codec_type':'audio','codec_name':'truehd'}],
                  'format':{'duration':'1'}}
            work=Workflow(SimpleNamespace(ffmpeg='ffmpeg'),root,lambda:None)
            work.copied_packets=Mock(side_effect=[{1:a},{1:b}])
            work.execute=Mock()
            with patch('packet_validation.compare_decoded_audio',side_effect=ValueError('PCM changed')):
                with self.assertRaisesRegex(ValueError,'PCM changed'):
                    work.validate_copied_tracks(root/'source.mkv',root/'copy.mkv',info,info,'test')
            self.assertEqual(work.execute.call_count,2)
            self.assertEqual(work.audited_audio_indices(root/'source.mkv',root/'copy.mkv'),set())
            work.copied_packets=Mock(side_effect=[{1:a},{1:b}])
            with patch('packet_validation.compare_decoded_audio',return_value={'pcm_identical':True}) as proof:
                work.validate_copied_tracks(root/'source.mkv',root/'copy.mkv',info,info,'verified')
                proof.assert_called_once()
            self.assertEqual(work.audited_audio_indices(root/'source.mkv',root/'copy.mkv'),{1})
            info['streams'][1]['codec_name']='ac3'
            work.copied_packets=Mock(side_effect=[{1:a},{1:b}])
            with self.assertRaisesRegex(ValueError,'Copied packet timing changed'):
                work.validate_copied_tracks(root/'source.mkv',root/'copy.mkv',info,info,'other-codec')

    def test_only_bounded_missing_source_timestamps_with_identical_payloads(self):
        def row(i,pts):
            return f'pts_time={pts}|dts_time={pts}|data_hash=SHA256:{str(i)*64}\n'
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'source';b=Path(tmp)/'output'
            source=row(1,'0')+row(2,'N/A')+row(3,'0.002')
            output=row(1,'0')+row(2,'0.001')+row(3,'0.002')
            a.write_text(source);b.write_text(output)
            self.assertEqual(reconstructed_audio_timestamp_case(a,b),3)
            for invalid in (output.replace('0.001','0.5'),output.replace('2'*64,'4'*64),output+row(4,'0.003'),output.replace('0.002','N/A')):
                b.write_text(invalid)
                self.assertIsNone(reconstructed_audio_timestamp_case(a,b))
            b.write_text(output);a.write_text(source.replace('0.002','N/A'))
            self.assertIsNone(reconstructed_audio_timestamp_case(a,b))
