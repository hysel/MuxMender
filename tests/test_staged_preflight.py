import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from auto_optimize import Workflow
from media_metadata import preflight_metadata


class StagedPreflightTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg integration dependencies unavailable')
    def test_generated_audio_subtitle_file_through_real_preflight(self):
        ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
        subtitles=self.root/'generated.srt'
        subtitles.write_text('1\n00:00:00,000 --> 00:00:00,200\nGenerated test\n')
        source=self.root/'generated.mkv'
        subprocess.run([ffmpeg,'-v','error','-nostdin','-n','-f','lavfi','-i','color=size=64x64:rate=24',
                        '-f','lavfi','-i','sine=sample_rate=48000','-i',str(subtitles),'-t','0.25',
                        '-map','0:v','-map','1:a','-map','2:s','-c:v','mpeg4','-c:a','ac3','-c:s','srt',str(source)],
                       check=True,capture_output=True,timeout=30)
        args=SimpleNamespace(ffmpeg=ffmpeg,ffprobe=ffprobe,timeout=60,encode_best=True)
        workflow=Workflow(args,self.root,lambda:None)
        metadata=workflow.probe(source);original=source.read_bytes()
        workflow.preflight_source(source,metadata,hashlib.sha256(original).hexdigest())
        with patch('auto_optimize.collect_packets') as collect:
            evidence=workflow.copied_packets(source,'full-reference',[1,2],metadata['format'])
        collect.assert_not_called();self.assertEqual(set(evidence),{1,2})
        self.assertEqual(source.read_bytes(),original)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'original.avi';self.source.write_bytes(b'original')
        self.w=Workflow(SimpleNamespace(ffprobe='ffprobe',timeout=30,encode_best=True),self.root,lambda:None)
        self.data=dict(format={'duration':'10'},streams=[dict(index=0,codec_type='video'),dict(index=1,codec_type='audio'),dict(index=2,codec_type='subtitle')])
        self.hash=hashlib.sha256(self.source.read_bytes()).hexdigest()

    def collect(self,ffprobe,source,directory,label,indices,*args):
        result={}
        for i in indices:
            p=directory/(label+f'-{i}.txt');p.write_text('evidence');result[i]=p
        return result

    def preflight(self):
        with patch('aac_priming.inspect',return_value={}),patch.object(self.w,'preflight_source_audio') as audio,patch('auto_optimize.collect_packets',side_effect=self.collect) as collect:
            self.w.preflight_source(self.source,self.data,self.hash)
            audio.assert_called_once();collect.assert_called_once()

    def test_metadata_is_geometry_and_container_agnostic(self):
        for codec,width in [('h264',720),('av1',4096),('mpeg4',638)]:
            data=copy.deepcopy(self.data);data['streams'][0].update(codec_name=codec,width=width)
            self.assertTrue(preflight_metadata(data)['metadata_structure_checked'])

    def test_bad_structure_stops_before_audio_or_packet_work(self):
        self.data['streams'][1]['index']=0
        with patch.object(self.w,'preflight_source_audio') as audio,patch('auto_optimize.collect_packets') as packets:
            with self.assertRaisesRegex(ValueError,'stream identities'):self.w.preflight_source(self.source,self.data,self.hash)
        audio.assert_not_called();packets.assert_not_called()
        self.assertEqual(json.loads((self.root/'source-preflight.json').read_text())['stage'],'metadata')

    def test_metadata_conflicts_and_invalid_chapters_are_early_errors(self):
        self.data['streams'][1]['tags']={'language':'eng','LANGUAGE':'fra'}
        with self.assertRaisesRegex(ValueError,'Conflicting'):preflight_metadata(self.data)
        self.data['streams'][1].pop('tags')
        self.data['chapters']=[{'start_time':'2','end_time':'1'}]
        with self.assertRaisesRegex(ValueError,'chapter'):preflight_metadata(self.data)
        self.data['chapters']=[];self.data['format']['duration']='nan'
        with self.assertRaisesRegex(ValueError,'duration'):preflight_metadata(self.data)

    def test_verified_same_run_source_evidence_is_reused(self):
        self.preflight()
        with patch('auto_optimize.collect_packets') as collect:
            result=self.w.copied_packets(self.source,'full-reference',[1,2],self.data['format'])
        collect.assert_not_called();self.assertEqual(set(result),{1,2})
        self.assertEqual(json.loads((self.root/'source-preflight.json').read_text())['state'],'passed')

    def test_no_copied_tracks_never_reads_source_again(self):
        with patch('auto_optimize.digest') as digest,patch('auto_optimize.collect_packets') as collect:
            self.assertEqual(self.w.copied_packets(self.source,'empty',[],self.data['format']),{})
        digest.assert_not_called();collect.assert_not_called()

    def test_source_content_change_rejects_even_if_size_unchanged(self):
        self.preflight();self.source.write_bytes(b'changed!')
        with self.assertRaisesRegex(RuntimeError,'Source changed since preflight'):
            self.w.copied_packets(self.source,'full-reference',[1,2],self.data['format'])

    def test_changed_evidence_is_collected_again(self):
        self.preflight();self.w.source_packet_cache['evidence'][1][0].write_text('tampered')
        with patch('auto_optimize.collect_packets',side_effect=self.collect) as collect:
            self.w.copied_packets(self.source,'full-reference',[1,2],self.data['format'])
        collect.assert_called_once()

    def test_new_workflow_never_reuses_old_run_evidence(self):
        self.preflight();fresh=Workflow(self.w.args,self.root,lambda:None)
        with patch('auto_optimize.collect_packets',side_effect=self.collect) as collect:
            fresh.copied_packets(self.source,'fresh',[1,2],self.data['format'])
        collect.assert_called_once()

    def test_source_reader_errors_do_not_cache_partial_evidence(self):
        (self.root/'preflight-source-all-packets.txt.stderr').write_text('invalid packet')
        with patch('aac_priming.inspect',return_value={}),patch.object(self.w,'preflight_source_audio'),patch('auto_optimize.collect_packets',side_effect=self.collect):
            with self.assertRaisesRegex(ValueError,'reader reported errors'):
                self.w.preflight_source(self.source,self.data,self.hash)
        self.assertIsNone(self.w.source_packet_cache)

    def test_sample_only_run_avoids_full_source_packet_pass(self):
        self.w.args.encode_best=False
        with patch('aac_priming.inspect',return_value={}),patch.object(self.w,'preflight_source_audio'),patch('auto_optimize.collect_packets') as collect:
            self.w.preflight_source(self.source,self.data,self.hash)
        collect.assert_not_called()


if __name__=='__main__':unittest.main()
