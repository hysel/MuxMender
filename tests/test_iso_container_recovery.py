import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from media_metadata import iso_data_container,essence_reader_options
from auto_optimize import Workflow
from iso_chapters import verify_track,mapping_options


def metadata(data_tracks=False):
    streams=[dict(index=0,codec_type='video',codec_name='h264'),dict(index=1,codec_type='audio',codec_name='aac')]
    if data_tracks:streams.append(dict(index=2,codec_type='data',codec_name='bin_data',codec_tag_string='text'))
    return dict(format=dict(format_name='mov,mp4,m4a,3gp,3g2,mj2',duration='5'),streams=streams,
                chapters=[dict(start_time='0',end_time='5',tags={'title':'Chapter 1'})])


class ISOContainerRecoveryTests(unittest.TestCase):
    def test_new_worker_reverifies_admission_chapter_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.mp4'
            admission=metadata();admission['chapter_track_semantics']={'method':'verified-fixture'}
            worker=Workflow(SimpleNamespace(timeout=10,encode_best=False),root,lambda:None)
            def inspect_again(path):
                worker.chapter_tracks[str(path.resolve())]=(2,)
                return copy.deepcopy(admission)
            with patch.object(worker,'probe',side_effect=inspect_again) as probe, \
                 patch('auto_optimize.metadata_check') as check, \
                 patch('aac_priming.inspect',return_value={}),patch.object(worker,'preflight_source_audio'):
                worker.preflight_source(source,admission,'hash')
                probe.assert_called_once_with(source)
                check.assert_called_once()
                command=['ffmpeg','-i',str(source),'-map','0','output.mp4']
                self.assertIn('-0:2',mapping_options(command,worker.chapter_tracks))
                worker.preflight_source(source,admission,'hash')
                probe.assert_called_once()

    def test_worker_rejects_changed_or_missing_chapter_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.mp4'
            admission=metadata();admission['chapter_track_semantics']={'method':'verified-fixture'}
            for changed in (True,False):
                worker=Workflow(SimpleNamespace(timeout=10,encode_best=False),root,lambda:None)
                inspected=copy.deepcopy(admission)
                if changed:inspected['chapter_track_semantics']={'method':'different'}
                with patch.object(worker,'probe',return_value=inspected),patch('auto_optimize.metadata_check'), \
                     patch.object(worker,'preflight_source_audio') as audio:
                    with self.assertRaisesRegex(ValueError,'evidence changed|mapping is unavailable'):
                        worker.preflight_source(source,admission,'hash')
                    audio.assert_not_called()

    def test_native_text_data_uses_mp4_without_dropping_track(self):
        data=metadata(True);before=copy.deepcopy(data)
        self.assertEqual(iso_data_container(data),'.mp4')
        self.assertEqual(essence_reader_options(data),[])
        self.assertEqual(data,before)
        data['streams'][-1]['codec_tag_string']='tmcd'
        self.assertEqual(iso_data_container(data),'.mov')
        data['format']['format_name']='matroska,webm'
        self.assertIsNone(iso_data_container(data))

    def test_essence_readers_do_not_change_chapter_metadata(self):
        data=metadata();before=copy.deepcopy(data)
        self.assertEqual(essence_reader_options(data),['-ignore_chapters','1'])
        self.assertEqual(data,before)
        data['format']['format_name']='matroska,webm'
        self.assertEqual(essence_reader_options(data),[])

    def test_shared_preflight_records_reader_policy_and_container(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.mp4'
            workflow=Workflow(SimpleNamespace(timeout=10,encode_best=False),root,lambda:None)
            with patch('aac_priming.inspect',return_value={}),patch.object(workflow,'preflight_source_audio'):
                workflow.preflight_source(source,metadata(),'hash')
                self.assertEqual(workflow.reader_input_options(source),['-ignore_chapters','1'])
                self.assertEqual(workflow.reader_input_options(root/'other.mkv'),[])
                workflow.preflight_source(source,metadata(True),'hash')
                self.assertEqual(workflow.output_suffix,'.mp4')
                self.assertEqual(workflow.reader_input_options(source),[])

    def test_source_audio_decode_retains_strict_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.mp4'
            workflow=Workflow(SimpleNamespace(ffmpeg='ffmpeg'),root,lambda:None)
            workflow.essence_options[str(source.resolve())]=('ignore-placeholder',)
            with patch.object(workflow,'discard_decode',side_effect=RuntimeError('actual decoder error')) as decode:
                with self.assertRaisesRegex(RuntimeError,'actual decoder error'):
                    workflow.preflight_source_audio(source,metadata())
            command=decode.call_args.args[0]
            self.assertIn('-xerror',command)
            self.assertIn('ignore-placeholder',command)

    def test_chapter_translation_requires_complete_identical_payload_and_clock(self):
        data=metadata(True);stream=data['streams'][-1];stream['time_base']='1/1000'
        payload=b'\x00\x09Chapter 1'+bytes.fromhex('0000000c656e636400000100')
        packet=dict(stream_index=2,pts=0,duration=5000,data='00000000: '+payload.hex()+'  fixture')
        proof=verify_track(data,stream,[packet])
        self.assertEqual(proof['chapters'],1)
        for change in ({'pts':1},{'duration':4999},{'stream_index':1},{'data':'00000000: 000143  fixture'}):
            with self.subTest(change=change),self.assertRaises(ValueError):verify_track(data,stream,[dict(packet,**change)])
        with self.assertRaises(ValueError):verify_track(data,stream,[])
        with self.assertRaises(ValueError):verify_track(data,stream,[packet,packet])
        data['streams'][-1]['tags']={'title':'Extra stream title'}
        with self.assertRaises(ValueError):verify_track(data,stream,[packet])

    def test_mapping_only_removes_exact_verified_redundant_track(self):
        command=['ffmpeg','-i','source.mp4','-i','other.mkv','-map','0','-map','1:a','-map_chapters','0','out.mp4']
        tracks={str(Path('source.mp4').resolve()):(2,)}
        changed=mapping_options(command,tracks)
        self.assertIn('-0:2',changed)
        self.assertEqual(changed[changed.index('-map_chapters')+1],'0')
        self.assertEqual(command.count('-map'),2)
        self.assertNotIn('-1:2',changed)
        explicit=['ffmpeg','-i','source.mp4','-map','0:a:0','-f','null','-']
        self.assertEqual(mapping_options(explicit,tracks),explicit)

    def test_only_known_default_chapter_descriptors_are_translated(self):
        data=metadata(True);stream=data['streams'][-1];stream['time_base']='1/1000'
        packet=dict(stream_index=2,pts=0,duration=5000,data='00000000: 0009436861707465722031  fixture')
        descriptor=bytes.fromhex('00000000000000010000000000000000'+'00'*27)
        stream.update(extradata_size=len(descriptor),extradata_hash='SHA256:'+hashlib.sha256(descriptor).hexdigest())
        self.assertEqual(verify_track(data,stream,[packet],descriptor)['descriptor'],'default-chapter-text')
        with self.assertRaises(ValueError):verify_track(data,stream,[packet])
        custom=descriptor[:-1]+b'\x01'
        stream['extradata_hash']='SHA256:'+hashlib.sha256(custom).hexdigest()
        with self.assertRaises(ValueError):verify_track(data,stream,[packet],custom)
