import copy
import json
import math
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import Mock, patch

import auto_optimize as ao
import autonomous_queue as aq
import control_service as cs
from dashboard import Catalog
from test_auto_optimize import source_data


class MetadataReviewTests(unittest.TestCase):
    def pair(self):
        before=source_data();after=copy.deepcopy(before)
        after['streams'][0]['codec_name']='hevc'
        return before,after

    def test_tag_key_case_changes_are_not_language_changes(self):
        before,after=self.pair()
        for index,language in enumerate(['eng','eng','fre','ger','spa','spa'],1):
            track=dict(index=index,codec_type='audio' if index==1 else 'subtitle',codec_name='dts' if index==1 else 'hdmv_pgs_subtitle',disposition={},tags={'LANGUAGE':language})
            before['streams'].append(track)
            after['streams'].append({**track,'tags':{'language':language}})
        ao.metadata_check(before,after,'hevc')
        after['streams'][3]['tags']['language']='eng'
        with self.assertRaisesRegex(ValueError,"Stream 3.*language.*'fre'.*'eng'"):
            ao.metadata_check(before,after,'hevc')

    def test_conflicting_case_aliases_fail_closed(self):
        before,after=self.pair();before['streams'][0]['tags']={'LANGUAGE':'eng','language':'fre'}
        with self.assertRaisesRegex(ValueError,'Conflicting metadata'):ao.metadata_check(before,after,'hevc')
        before['streams'][0]['tags']={'LANGUAGE':'eng','language':'eng'}
        after['streams'][0]['tags']={'language':'eng'}
        ao.metadata_check(before,after,'hevc')

    def test_title_values_and_missing_language_remain_strict(self):
        for old,new in [({'LANGUAGE':'eng'},{}),({'TITLE':'Director commentary'},{'title':'Main audio'})]:
            before,after=self.pair();before['streams'][0]['tags']=old;after['streams'][0]['tags']=new
            with self.assertRaisesRegex(ValueError,'tag changed'):ao.metadata_check(before,after,'hevc')

    def test_chapter_tag_names_normalized_not_chapter_content(self):
        before,after=self.pair();before['chapters']=[dict(id=0,start=0,end=100,time_base='1/1000',tags={'TITLE':'Intro'})]
        after['chapters']=[dict(id=0,start=0,end=100,time_base='1/1000',tags={'title':'Intro'})]
        ao.metadata_check(before,after,'hevc')
        after['chapters'][0]['end']=101
        with self.assertRaisesRegex(ValueError,'Chapters changed'):ao.metadata_check(before,after,'hevc')

    def test_duration_nan_infinity_and_nonpositive_rejected(self):
        for value in ('nan','inf','-inf','0','-1'):
            before,after=self.pair();after['format']['duration']=value
            with self.assertRaisesRegex(ValueError,'Invalid duration'):ao.metadata_check(before,after,'hevc')


class QueueReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);media=self.root/'media';media.mkdir();output=self.root/'output';output.mkdir()
        self.c=cs.Controls(media,output,lambda _:True,['hevc']);self.c.ready=True
        self.source=media/'a.mkv';self.source.write_bytes(b'original')

    def submit(self):
        self.c.submit(self.c.preview(dict(path='a.mkv',mode='test'))['preview_id'])
        return self.c.state['jobs'][-1]

    def test_missing_source_marked_failed_not_left_pending(self):
        job=self.submit();self.source.unlink()
        with patch.object(cs.subprocess,'Popen') as process:
            self.c.worker_step();process.assert_not_called()
        self.assertEqual(job['state'],'failed');self.assertIn('finished',job)
        self.assertEqual(self.c.state['failures'],1);self.assertFalse(self.c.assignments)

    def test_changed_source_counts_as_failure_without_encoding(self):
        job=self.submit();self.source.write_bytes(b'changed original')
        with patch.object(cs.subprocess,'Popen') as process:
            self.c.worker_step();process.assert_not_called()
        self.assertEqual(job['state'],'failed');self.assertIn('Source changed',job['reason'])
        self.assertEqual(self.c.state['failures'],1)

    def test_recorded_worker_error_reaches_results(self):
        job=self.submit()
        def worker(command,**kwargs):
            folder=Path(command[command.index('--output-dir')+1])/'auto-test';folder.mkdir()
            aq.write(folder/'status.json',dict(state='stopped-original-retained',error='Stream 3 tag changed: language'))
            return Mock(wait=lambda:1)
        with patch.object(cs.subprocess,'Popen',side_effect=worker):self.c.worker_step()
        self.assertEqual(job['state'],'failed');self.assertEqual(job['reason'],'Stream 3 tag changed: language')

    def test_profile_write_requires_ready_worker(self):
        self.c.ready=False
        with self.assertRaises(ValueError):self.c.action(dict(action='resource-profile',profile='quiet'))
        self.assertNotIn('resource_profile',self.c.state)

    def test_incomplete_validated_record_cannot_become_ready(self):
        job=self.submit()
        def worker(command,**kwargs):
            folder=Path(command[command.index('--output-dir')+1])/'auto-test';folder.mkdir()
            aq.write(folder/'status.json',dict(state='validated-copy-awaiting-playback'))
            return Mock(wait=lambda:0)
        with patch.object(cs.subprocess,'Popen',side_effect=worker):self.c.worker_step()
        self.assertEqual(job['state'],'failed');self.assertIn('incomplete',job['reason'])

    def test_atomic_write_preserves_previous_record_on_failure(self):
        path=self.root/'state.json';aq.write(path,{'old':True})
        with patch.object(Path,'replace',side_effect=OSError('disk error')):
            with self.assertRaises(OSError):aq.write(path,{'new':True})
        self.assertEqual(aq.read(path),{'old':True});self.assertFalse(list(self.root.glob('*.tmp')))

    def test_unreadable_artifact_root_does_not_break_dashboard(self):
        catalog=Catalog(self.root)
        real=Path.is_dir
        def is_dir(path):
            if path.name=='reports':raise PermissionError('denied')
            return real(path)
        with patch.object(Path,'is_dir',is_dir):self.assertEqual(catalog.snapshot(),[])


class ReleaseReviewTests(unittest.TestCase):
    def test_archive_permissions_and_exclusive_creation(self):
        from tools.build_app_release import create_release
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'repo';root.mkdir();archive=Path(folder)/'release.tar'
            for name in ['python/ui/app.py','python/__pycache__/bad.pyc','tests/test.py',
                         'deploy/truenas/Dockerfile.app','docs/note.md',
                         'docs/per-video-codec-selection.md','tools/build_app_release.py',
                         'tools/compare_encoders.py','tools/run_truenas_sample_batch.py',
                         'tools/smoke_auto_optimize.py','tools/smoke_hdr_auto.py','tools/smoke_hdr_dynamic.py','tools/smoke_timestamp.py','tools/monitor_queue.py','tools/qualify_frame_reader.py',
                         'tools/benchmark_frame_threads.py','tools/benchmark_packet_validation.py',
                         'tools/benchmark_validation_pipeline.py','tools/benchmark_gpu_decode.py']:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
            result=create_release(root,archive,'docs/note.md')
            self.assertEqual(len(result['files']),18)
            with tarfile.open(archive) as tar:
                for member in tar:
                    self.assertEqual(member.mode,0o755 if member.isdir() else 0o644)
                    self.assertNotIn('__pycache__',member.name)
            with self.assertRaises(FileExistsError):create_release(root,archive,'docs/note.md')


if __name__=='__main__':unittest.main()
