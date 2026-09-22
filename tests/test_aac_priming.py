from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from aac_priming import priming_tracks,finalize,inspect
from packet_validation import aac_terminal_duration_case
from auto_optimize import compare_packets,Workflow

class AACPrimingTests(unittest.TestCase):
    def test_other_containers_do_not_run_mp4_priming_probe(self):
        with patch('aac_priming.run_probe') as probe:
            self.assertEqual(inspect(None,None,{'format':{'format_name':'matroska'},'streams':[]},'test'),{})
            probe.assert_not_called()

    def test_finalizer_never_overwrites_source_or_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4';source.write_bytes(b'original')
            encoded=Path(folder)/'encoded.mkv';encoded.write_bytes(b'encoded')
            for output in (source,encoded):
                with self.assertRaises(ValueError):finalize(None,source,encoded,output,{}, {},'test',1)
            self.assertEqual(source.read_bytes(),b'original')

    def test_shared_encoder_records_priming_only_after_successful_finalization(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'out.mkv';source=root/'input.mp4'
            w=Workflow(SimpleNamespace(),root,lambda:None)
            with patch('aac_priming.inspect',return_value={1:{}}),patch.object(w,'_encode_preserving_color') as encode,patch('aac_priming.finalize') as finish:
                finish.side_effect=ValueError('failed mux')
                with self.assertRaises(ValueError):w.encode_preserving_color(source,output,{},None,{},'test',1)
                self.assertEqual(w.aac_priming_outputs,{})
                finish.side_effect=None
                w.encode_preserving_color(source,output,{},None,{},'test',1)
                self.assertEqual(w.aac_priming_outputs[output.resolve()],{1})
                self.assertNotEqual(encode.call_args.args[1],source)

    def test_explicit_skip_requires_matching_timestamp(self):
        data={'streams':[dict(index=1,codec_name='aac',codec_type='audio',sample_rate='48000')]}
        p=dict(stream_index=1,pts_time='-0.042667',side_data_list=[dict(side_data_type='Skip Samples',skip_samples=2048,discard_padding=0)])
        self.assertEqual(priming_tracks(data,[p])[1]['seconds'],Fraction(2048,48000))
        self.assertEqual(priming_tracks(data,[]),{})
        p['pts_time']='0'
        with self.assertRaises(ValueError):priming_tracks(data,[p])

    def test_finalizer_copies_without_audio_reencode_and_sets_delay(self):
        class Args:ffmpeg='ffmpeg'
        class W:
            args=Args()
            def __init__(self):self.commands=[]
            def execute(self,c,*args):self.commands.append(c)
        w=W();before={'streams':[dict(index=0,codec_type='video'),dict(index=1,codec_type='audio')]}
        finalize(w,Path('source.mp4'),Path('encoded.mkv'),Path('fixed.mkv'),before,{1:dict(seconds=Fraction(2048,48000))},'test',5)
        cmd,edit=w.commands
        self.assertIn('-n',cmd);self.assertIn('1:1',cmd)
        self.assertEqual(cmd[cmd.index('-c')+1],'copy')
        self.assertIn('codec-delay=42666667',edit)
        self.assertNotIn('source.mp4',edit)

    def test_terminal_packet_is_only_accepted_after_explicit_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b=Path(folder)/'a',Path(folder)/'b'
            def rows(duration,hashvalue='a',count=3):
                return ''.join(f'pts_time={i*.021333:.6f}|dts_time={i*.021333:.6f}|duration_time={duration if i==count-1 else "0.021333"}|data_hash=SHA256:{hashvalue*64}\n' for i in range(count))
            a.write_text(rows('0.015333'));b.write_text(rows('0.021000'))
            self.assertEqual(aac_terminal_duration_case(a,b),3)
            with self.assertRaises(ValueError):compare_packets(a,b)
            compare_packets(a,b,aac_terminal_verified=3)
            b.write_text(rows('0.021000').replace('duration_time=0.021333','duration_time=N/A',1))
            self.assertIsNone(aac_terminal_duration_case(a,b))
            self.assertEqual(aac_terminal_duration_case(a,b,preserved_priming=True),3)
            compare_packets(a,b,aac_terminal_verified=3,aac_priming_verified=True)
            with self.assertRaises(ValueError):compare_packets(a,b,aac_terminal_verified=3)
            b.write_text(b.read_text().replace('pts_time=0.000000','pts_time=0.050000'))
            with self.assertRaises(ValueError):compare_packets(a,b,aac_terminal_verified=3,aac_priming_verified=True)
            b.write_text(rows('0.021000'))
            with self.assertRaises(ValueError):compare_packets(a,b,aac_terminal_verified=2)
            b.write_text(rows('0.021000','b'));self.assertIsNone(aac_terminal_duration_case(a,b))
            b.write_text(rows('0.021000',count=4));self.assertIsNone(aac_terminal_duration_case(a,b))
            b.write_text(rows('0.021000').replace('pts_time=0.021333','pts_time=0.1'));self.assertIsNone(aac_terminal_duration_case(a,b))
            b.write_text(rows('0.021000').replace('duration_time=0.021333','duration_time=0.009',1));self.assertIsNone(aac_terminal_duration_case(a,b))

if __name__=='__main__':unittest.main()
