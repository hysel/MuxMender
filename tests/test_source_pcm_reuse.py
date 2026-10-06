from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from auto_optimize import Workflow


class SourcePcmReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source.mkv';self.source.write_bytes(b'generated source')
        self.workflow=Workflow(SimpleNamespace(ffmpeg='ffmpeg'),self.root,lambda:None)
        def execute(command,*args,**kwargs):
            self.assertTrue(kwargs['strict_decode']);Path(command[-1]).write_text('Complete fixture evidence\n')
        self.workflow.execute=Mock(side_effect=execute)

    def decode(self,name,**kwargs):
        return self.workflow.decoded_audio_evidence(self.source,0,'pcm_f64le',self.root/(name+'.framehash'),name,1,**kwargs)

    def test_only_unchanged_source_can_reuse_complete_evidence(self):
        a=self.decode('first',reuse_source=True);b=self.decode('second',reuse_source=True)
        self.assertEqual(a,b);self.assertEqual(self.workflow.execute.call_count,1)
        self.source.write_bytes(b'changed source')
        self.decode('changed',reuse_source=True);self.assertEqual(self.workflow.execute.call_count,2)
        self.decode('output-1');self.decode('output-2')
        self.assertEqual(self.workflow.execute.call_count,4,'Output PCM decoding must never be cached')

    def test_corrupt_cached_evidence_is_not_accepted(self):
        a=self.decode('first',reuse_source=True);a.write_text('tampered')
        b=self.decode('second',reuse_source=True)
        self.assertNotEqual(a,b);self.assertEqual(self.workflow.execute.call_count,2)

    def test_decode_failure_does_not_create_reusable_proof(self):
        self.workflow.execute.side_effect=ValueError('Decoder corruption')
        with self.assertRaises(ValueError):self.decode('failed',reuse_source=True)
        self.assertFalse(self.workflow.source_pcm_cache)

    def test_source_mutation_during_decode_is_rejected(self):
        def changed(command,*args,**kwargs):
            self.source.write_bytes(b'mutation');Path(command[-1]).write_text('fixture')
        self.workflow.execute.side_effect=changed
        with self.assertRaisesRegex(ValueError,'Source changed'):self.decode('changed',reuse_source=True)
        self.assertFalse(self.workflow.source_pcm_cache)

    def test_pcm_format_and_track_are_part_of_cache_key(self):
        self.decode('first',reuse_source=True)
        self.workflow.decoded_audio_evidence(self.source,0,'pcm_f32le',self.root/'other.framehash','other',1,reuse_source=True)
        self.workflow.decoded_audio_evidence(self.source,1,'pcm_f64le',self.root/'track.framehash','track',1,reuse_source=True)
        self.assertEqual(self.workflow.execute.call_count,3)
