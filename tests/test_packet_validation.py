from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from packet_validation import split_packet_evidence, collect_packets
from auto_optimize import compare_packets, Workflow


def row(index,payload='a',pts='1.0'):
    return f'stream_index={index}|pts_time={pts}|dts_time={pts}|duration_time=0.04|data_hash=SHA256:{payload*64}\n'


class PacketValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def split(self,label,text,indices=(1,2)):
        path=self.root/(label+'.txt');path.write_text(text)
        return split_packet_evidence(path,self.root,label,indices)

    def test_interleaving_and_video_payload_can_change(self):
        a=self.split('before',row(0)+row(1)+row(2,'b')+row(1,'c','2'))
        b=self.split('after',row(2,'b')+row(0,'d')+row(1)+row(1,'c','2'))
        for index in (1,2):compare_packets(a[index],b[index])
        self.assertNotIn(0,a)

    def test_changed_dropped_reordered_and_retimed_packets_fail(self):
        a=self.split('before',row(1)+row(1,'b','2'))
        for n,text in enumerate([row(1,'c')+row(1,'b','2'),row(1),row(1,'b','2')+row(1),row(1,pts='1.1')+row(1,'b','2')]):
            b=self.split('bad'+str(n),text)
            with self.assertRaises(ValueError):compare_packets(a[1],b[1])

    def test_empty_subtitle_tracks_remain_comparable(self):
        a=self.split('a',row(0)+row(1));b=self.split('b',row(0)+row(1))
        compare_packets(a[2],b[2])

    def test_missing_hash_or_stream_identity_rejected(self):
        for n,text in enumerate(['stream_index=1|pts_time=1\n',row(1).replace('stream_index=1|',''),row(1).replace('SHA256:','truncated:')]):
            with self.assertRaises(ValueError):self.split('bad'+str(n),text)

    def test_nonfinite_timestamps_rejected_even_when_equal(self):
        for n,value in enumerate(['nan','inf','-inf']):
            a=self.split('a'+str(n),row(1,pts=value))
            with self.assertRaises(ValueError):compare_packets(a[1],a[1])

    def test_one_probe_for_all_tracks_with_duration_progress(self):
        def probe(command,path,label,timeout,guard,duration,start):
            self.assertNotIn('-select_streams',command);self.assertEqual(duration,60)
            path.write_text(row(1)+row(2))
        with patch('packet_validation.run_probe',side_effect=probe) as call:
            paths=collect_packets('ffprobe',Path('source'),self.root,'all',[1,2],60,lambda:None,60)
        self.assertEqual(call.call_count,1);self.assertEqual(set(paths),{1,2})

    def test_video_only_requires_no_packet_probe(self):
        with patch('packet_validation.run_probe') as call:
            self.assertEqual(collect_packets('ffprobe',Path('source'),self.root,'none',[],60,lambda:None),{})
        call.assert_not_called()

    def test_guard_interrupts_split(self):
        source=self.root/'data';source.write_text(row(1))
        with self.assertRaises(KeyboardInterrupt):split_packet_evidence(source,self.root,'stopped',[1],lambda:(_ for _ in ()).throw(KeyboardInterrupt()))

    def test_sample_cache_rechecks_source_and_evidence_content(self):
        source=self.root/'reference-0.mkv';source.write_bytes(b'generated source')
        workflow=Workflow(SimpleNamespace(ffprobe='ffprobe',timeout=60),self.root,lambda:None)
        def collect(ffprobe,source,directory,label,*args):
            evidence=directory/(label+'.txt');evidence.write_text(row(1));return {1:evidence}
        with patch('auto_optimize.collect_packets',side_effect=collect) as call:
            first=workflow.copied_packets(source,'one',[1],{'duration':60},True)
            second=workflow.copied_packets(source,'two',[1],{'duration':60},True)
            self.assertEqual(first,second);self.assertEqual(call.call_count,1)
            first[1].write_text(row(1,'b'))
            third=workflow.copied_packets(source,'three',[1],{'duration':60},True)
            self.assertEqual(call.call_count,2);self.assertNotEqual(first,third)
            source.write_bytes(b'changed reference')
            workflow.copied_packets(source,'four',[1],{'duration':60},True)
            self.assertEqual(call.call_count,3)

    def test_library_sources_never_use_sample_cache(self):
        source=self.root/'movie.mkv';source.write_bytes(b'source')
        workflow=Workflow(SimpleNamespace(ffprobe='ffprobe',timeout=60),self.root,lambda:None)
        with patch('auto_optimize.collect_packets',return_value={}) as call:
            for label in ('one','two'):workflow.copied_packets(source,label,[1],{'duration':60},True)
        self.assertEqual(call.call_count,2)


if __name__=='__main__':unittest.main()
