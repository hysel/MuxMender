import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from library_planner import classify,enumerate_media,scan,probe_with_frame_color
from tests.test_muxmender import sample
from library_planner import create_cleanup_plan, apply_cleanup_plan
import muxmender as mm
import copy
import os


class CleanupTests(unittest.TestCase):
    def fixture(self, root):
        (root/'Sample').mkdir(); (root/'Subtitles').mkdir()
        for name in ('movie.mkv','movie.NFO','movie.srt','Sample/clip.mkv','Sample/clip.ass',
                     'Subtitles/movie.en.srt','movie.sample.mp4','Sample Film (2020).mkv'):
            (root/name).write_bytes(b'fixture: '+name.encode())
        return root/'movie.mkv'

    def test_preview_is_read_only_and_protects_subtitles_at_every_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);primary=self.fixture(root)
            before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            basic=create_cleanup_plan(primary)
            self.assertEqual([Path(e['source']).name for e in basic['entries']],['movie.NFO'])
            plan=create_cleanup_plan(primary,True)
            self.assertEqual({Path(e['source']).relative_to(root).as_posix() for e in plan['entries']},
                             {'movie.NFO','movie.sample.mp4','Sample/clip.mkv'})
            self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            os.link(primary,root/'feature.sample.mkv')
            self.assertNotIn(str(root/'feature.sample.mkv'),[e['source'] for e in create_cleanup_plan(primary,True)['entries']])

    def test_apply_requires_explicit_confirmation_and_preserves_main_and_subtitles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);primary=self.fixture(root);plan=root/'cleanup.json'
            self.assertEqual(mm.main([str(primary),'--cleanup-plan',str(plan),'--cleanup-samples']),0)
            self.assertEqual(mm.main(['--apply-cleanup-plan',str(plan),'--execute']),2)
            self.assertTrue((root/'movie.NFO').exists())
            self.assertEqual(mm.main(['--apply-cleanup-plan',str(plan),'--execute','--confirm-cleanup','CLEANUP']),0)
            self.assertFalse((root/'movie.NFO').exists())
            self.assertFalse((root/'Sample/clip.mkv').exists())
            for name in ('movie.mkv','movie.srt','Sample/clip.ass','Subtitles/movie.en.srt','Sample Film (2020).mkv'):
                self.assertTrue((root/name).exists())
            journal=next(root.glob('cleanup.cleanup-*.jsonl'))
            self.assertEqual(sum(json.loads(line)['status']=='deleted' for line in journal.read_text().splitlines()),3)

    def test_stale_plan_refuses_entire_batch_before_any_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);primary=self.fixture(root)
            plan=create_cleanup_plan(primary,True)
            (root/'Sample/clip.mkv').write_bytes(b'changed since preview')
            path=root/'plan.json';path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'changed since preview'):
                apply_cleanup_plan(path)
            self.assertTrue((root/'movie.NFO').exists())
            self.assertTrue((root/'movie.sample.mp4').exists())

    def test_mid_apply_change_stops_and_records_partial_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);primary=self.fixture(root);plan=create_cleanup_plan(primary,True)
            path=root/'plan.json';path.write_text(json.dumps(plan))
            first,second=[Path(e['source']) for e in plan['entries'][:2]]
            original_unlink=Path.unlink
            def unlink(candidate,*args,**kwargs):
                original_unlink(candidate,*args,**kwargs)
                if candidate==first:second.write_bytes(b'externally changed after first deletion')
            with patch.object(Path,'unlink',unlink), self.assertRaisesRegex(RuntimeError,'earlier deletions remain'):
                apply_cleanup_plan(path)
            rows=[json.loads(line) for line in next(root.glob('plan.cleanup-*.jsonl')).read_text().splitlines()]
            self.assertEqual([row['status'] for row in rows],['starting','deleted','failed'])
            self.assertFalse(first.exists());self.assertTrue(second.exists())
            self.assertTrue((root/'Sample/clip.mkv').exists());self.assertTrue(primary.exists())

    def test_edited_plan_cannot_add_subtitles_primary_outside_or_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root=Path(tmp);primary=self.fixture(root);base=create_cleanup_plan(primary,True)
            external=Path(outside)/'outside.nfo';external.write_bytes(b'outside')
            for target in (primary,root/'movie.srt',root/'Subtitles/movie.en.srt',external):
                plan=copy.deepcopy(base)
                plan['entries'].append(dict(source=str(target),identity=mm.rename_identity(target),status='ready'))
                path=root/'plan.json';path.write_text(json.dumps(plan))
                with self.assertRaises(ValueError):apply_cleanup_plan(path)
                self.assertTrue((root/'movie.NFO').exists())
            plan=copy.deepcopy(base);plan['entries'].append(plan['entries'][0])
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'Duplicate'):apply_cleanup_plan(path)


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
