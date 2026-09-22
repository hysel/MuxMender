import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import validated_replace as vr


class ReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.media=self.root/'media';self.media.mkdir()
        self.run=self.root/'run';self.run.mkdir()
        self.source=self.media/'video.mkv';self.source.write_bytes(b'original'*100)
        self.output=self.run/'full-av1.mkv';self.output.write_bytes(b'copy'*50)
        self.status=dict(state='validated-copy-awaiting-playback',source=str(self.source),output=str(self.output),source_sha256=vr.digest(self.source),output_sha256=vr.digest(self.output))
        self.save()
        (self.run/'selection.json').write_text(json.dumps(dict(action='encode_copy',selected=dict(id='winner'),candidates=[dict(id='winner',rejected_reasons=[])])))
    def save(self):(self.run/'status.json').write_text(json.dumps(self.status))
    def run_replace(self):return vr.replace_validated(self.source,self.media,self.media,self.run,10,'test')
    def test_verified_replacement(self):
        result=self.run_replace()
        self.assertEqual(result['state'],'replaced')
        self.assertEqual(vr.digest(self.source),self.status['output_sha256'])
        self.assertEqual(result['saved_bytes'],600)
        self.assertFalse(Path(result['backup']).exists())
        self.assertFalse(self.output.exists())
        self.assertEqual(result['artifact_cleanup']['state'],'cleaned')
    def test_cryptic_movie_is_named_after_folder_after_verified_publication(self):
        folder=self.media/'Example Film';folder.mkdir()
        new=folder/'sample-ab1.1080p.mkv';self.source.rename(new);self.source=new
        self.status['source']=str(new);self.save()
        result=self.run_replace()
        self.assertEqual(Path(result['target']),folder/'Example Film.mkv')
        self.assertEqual(vr.digest(Path(result['target'])),self.status['output_sha256'])
        self.assertFalse(new.exists())
        self.assertEqual(result['source'],str(new))

    def test_readable_naming_preserves_ambiguous_and_episode_names(self):
        folder=self.media/'Example Film';folder.mkdir()
        source=folder/'sample-ab1.1080p.mkv';source.write_bytes(b'source')
        self.assertEqual(vr.readable_destination(source).name,'Example Film.mkv')
        other=folder/'other.mp4';other.write_bytes(b'other')
        self.assertEqual(vr.readable_destination(source),source)
        self.assertEqual(vr.readable_destination(folder/'Show.S01E01.mkv').name,'Show.S01E01.mkv')

    def test_naming_does_not_overwrite_existing_title(self):
        folder=self.media/'Example Film';folder.mkdir()
        source=folder/'sample-ab1.1080p.mkv';source.write_bytes(b'source')
        target=folder/'Example Film.mkv';target.write_bytes(b'existing')
        self.assertEqual(vr.destination_for(source),source)
        self.assertEqual(target.read_bytes(),b'existing')

    def test_naming_preserves_external_subtitle_association(self):
        folder=self.media/'Example Film';folder.mkdir()
        source=folder/'sample-ab1.1080p.mkv';source.write_bytes(b'source')
        (folder/'sample-ab1.1080p.en.srt').write_text('subtitle')
        self.assertEqual(vr.readable_destination(source),source)
    def test_zero_threshold_cannot_publish_equal_size(self):
        self.output.write_bytes(b'x'*self.source.stat().st_size)
        self.status['output_sha256']=vr.digest(self.output);self.save()
        with self.assertRaisesRegex(ValueError,'minimum savings'):
            vr.replace_validated(self.source,self.media,self.media,self.run,0,'test')
        self.assertEqual(vr.digest(self.source),self.status['source_sha256'])
    def test_invalid_threshold_and_job_identifier_fail_before_publication(self):
        for minimum,identifier in [(float('nan'),'test'),(float('inf'),'test'),(-1,'test'),(100,'test'),(10,'../escape')]:
            with self.assertRaises(ValueError):vr.replace_validated(self.source,self.media,self.media,self.run,minimum,identifier)
        self.assertEqual(vr.digest(self.source),self.status['source_sha256'])
        self.assertFalse((self.run/'replacement.json').exists())
    def test_source_change_retains_original(self):
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.run_replace()
        self.assertEqual(self.source.read_bytes(),b'changed')
    def test_output_change_retains_original(self):
        self.output.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.run_replace()
        self.assertEqual(vr.digest(self.source),self.status['source_sha256'])
    def test_samples_cannot_replace(self):
        self.status['state']='trials-completed';self.save()
        with self.assertRaises(ValueError):self.run_replace()
    def test_wrong_mount(self):
        wrong=self.root/'wrong';wrong.mkdir();(wrong/'video.mkv').write_bytes(self.source.read_bytes())
        with self.assertRaises(ValueError):vr.target_for(self.source,self.media,wrong)
    def test_disabled(self):
        with self.assertRaises(ValueError):vr.target_for(self.source,self.media,None)
    def change_extension(self, extension):
        renamed=self.source.with_suffix(extension);self.source.rename(renamed);self.source=renamed
        self.status['source']=str(renamed);self.save()
    def test_mp4_replacement_has_mkv_extension(self):
        self.change_extension('.mp4');result=self.run_replace()
        self.assertFalse(self.source.exists())
        self.assertEqual(Path(result['target']).suffix,'.mkv')
        self.assertEqual(vr.digest(Path(result['target'])),self.status['output_sha256'])
    def test_avi_replacement_has_mkv_extension(self):
        self.change_extension('.AVI');result=self.run_replace()
        self.assertFalse(self.source.exists())
        self.assertEqual(vr.digest(Path(result['target'])),self.status['output_sha256'])
    def test_destination_conflict_retains_both(self):
        self.change_extension('.mp4');other=self.source.with_suffix('.MKV');other.write_bytes(b'unrelated')
        with self.assertRaises(vr.DestinationConflict):self.run_replace()
        self.assertEqual(other.read_bytes(),b'unrelated')
        self.assertEqual(vr.digest(self.source),self.status['source_sha256'])
    def test_late_conflict_never_clobbered(self):
        self.change_extension('.avi');original_link=vr.os.link
        def race(src,dst):
            if str(src).endswith('.staging'):Path(dst).write_bytes(b'concurrent')
            return original_link(src,dst)
        with patch.object(vr.os,'link',side_effect=race):
            with self.assertRaises(vr.DestinationConflict):self.run_replace()
        self.assertEqual(self.source.with_suffix('.mkv').read_bytes(),b'concurrent')
        self.assertEqual(vr.digest(self.source),self.status['source_sha256'])
    def test_existing_recovery_files_not_overwritten(self):
        backup=self.source.with_name(self.source.name+'.muxmender-test.original');backup.write_bytes(b'recovery')
        with self.assertRaises(ValueError):self.run_replace()
        self.assertEqual(backup.read_bytes(),b'recovery')
    def test_publication_failure_keeps_original(self):
        original_replace=vr.os.replace
        def fail_stage(src,dst):
            if str(src).endswith('.staging'):raise OSError('simulated interruption')
            return original_replace(src,dst)
        with patch.object(vr.os,'replace',side_effect=fail_stage):
            with self.assertRaises(OSError):self.run_replace()
        self.assertEqual(vr.digest(self.source),self.status['source_sha256'])
