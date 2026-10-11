import hashlib
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
from autonomous_queue import signature,write,read
from control_service import Controls,source_identity


class CopyApprovalTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);self.media=root/'media';self.output=root/'output';self.media.mkdir();self.output.mkdir()
        self.source=self.media/'example.mkv';self.source.write_bytes(b'source'*100)
        self.controls=Controls(self.media,self.output,lambda _:False,['hevc','av1'],replacement_root=self.media);self.controls.ready=True
        self.identifier='1'*32;self.folder=self.controls.root/('request-'+self.identifier);self.result=self.folder/'auto-fixture';self.result.mkdir(parents=True)
        self.copy=self.result/'output.mkv';self.copy.write_bytes(b'copy'*50)
        self.status=dict(state='validated-copy-awaiting-playback',source=str(self.source),output=str(self.copy),
            publication_authorized=True,source_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
            output_sha256=hashlib.sha256(self.copy.read_bytes()).hexdigest())
        write(self.result/'status.json',self.status)
        write(self.result/'selection.json',dict(action='encode_copy',selected=dict(id='winner'),candidates=[dict(id='winner',rejected_reasons=[])]))
        self.job=dict(id=self.identifier,source=str(self.source),signature=signature(self.source),source_identity=source_identity(self.source),
            state='awaiting-playback',settings=dict(mode='encode',minimum_savings=25,savings_mode='fixed'),output=str(self.folder),finished=1,created=1)
        self.controls.state['jobs'].append(self.job)

    def preview(self):return self.controls.action(dict(action='approve-copy-preview',job_id=self.identifier))
    def confirm(self,preview,**extra):return self.controls.action(dict(action='approve-copy-confirm',confirmation_id=preview['confirmation_id'],confirm=True,**extra))

    def test_preview_is_read_only_and_confirmation_queues_no_reencode(self):
        preview=self.preview();self.assertEqual(preview['copy_bytes'],200);self.assertEqual(self.job['state'],'awaiting-playback')
        self.controls.state['paused']=True
        result=self.confirm(preview);self.assertTrue(result['auto_started']);self.assertTrue(self.job['publication_only'])
        self.assertEqual(self.job['state'],'pending');self.assertEqual(self.job['output'],str(self.folder))
        with patch.object(self.controls,'build_command',side_effect=AssertionError('must not encode')),patch.object(self.controls,'publish_result',return_value=('replaced','Published')) as publish:
            self.controls.step()
        self.assertEqual(publish.call_args.args[-1],self.result);self.assertEqual(self.job['state'],'replaced')
        self.assertEqual(self.source.read_bytes(),b'source'*100);self.assertEqual(self.copy.read_bytes(),b'copy'*50)
        with self.assertRaises(ValueError):self.confirm(preview)

    def test_changed_inputs_block_confirm_and_worker(self):
        preview=self.preview();self.copy.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):self.confirm(preview)
        self.assertEqual(self.job['state'],'awaiting-playback')
        preview=self.preview();self.confirm(preview);self.copy.write_bytes(b'changed again')
        with patch.object(self.controls,'publish_result') as publish:
            with self.assertRaisesRegex(ValueError,'changed'):self.controls.step()
            publish.assert_not_called()

    def test_missing_copy_or_nonqualified_result_is_rejected(self):
        for key,value in (('publication_authorized',False),('state','trials-completed'),('source_sha256',None)):
            with self.subTest(key=key):
                write(self.result/'status.json',dict(self.status,**{key:value}))
                with self.assertRaises(ValueError):self.preview()
        write(self.result/'status.json',self.status);self.copy.unlink()
        with self.assertRaises(ValueError):self.preview()

    def test_original_change_readonly_mount_and_custom_output_are_rejected(self):
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Original changed'):self.preview()
        self.job.update(signature=signature(self.source),source_identity=source_identity(self.source))
        self.controls.readonly=lambda _:True
        with self.assertRaisesRegex(ValueError,'writable'):self.preview()
        self.controls.readonly=lambda _:False
        write(self.result/'status.json',dict(self.status,output=str(self.source)))
        with self.assertRaisesRegex(ValueError,'unsafe'):self.preview()

    def test_journals_failed_quality_or_active_source_block_approval(self):
        write(self.result/'replacement.json',dict(state='published-verifying'))
        with self.assertRaisesRegex(ValueError,'journal'):self.preview()
        (self.result/'replacement.json').unlink()
        write(self.result/'selection.json',dict(action='encode_copy',selected=dict(id='winner'),candidates=[dict(id='winner',rejected_reasons=['quality'])]))
        with self.assertRaisesRegex(ValueError,'passing'):self.preview()
        self.controls.state['jobs'].append(dict(id='2'*32,source=str(self.source),state='running'))
        with self.assertRaisesRegex(ValueError,'already'):self.preview()

    def test_explicit_confirmation_expiry_and_persistence_failure(self):
        preview=self.preview()
        with self.assertRaisesRegex(ValueError,'Explicit'):self.controls.action(dict(action='approve-copy-confirm',confirmation_id=preview['confirmation_id']))
        self.controls.copy_drafts[preview['confirmation_id']]['expires']=0
        with self.assertRaisesRegex(ValueError,'expired'):self.confirm(preview)
        preview=self.preview()
        with patch.object(self.controls,'save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.confirm(preview)
        self.assertEqual(self.job['state'],'awaiting-playback');self.assertNotIn('publication_only',self.job)

    def test_pending_approval_survives_restart_and_manual_pause_is_preserved(self):
        other=dict(id='2'*32,source=str(self.media/'other.mkv'),state='pending')
        self.controls.state['jobs'].append(other);self.controls.state.update(paused=True,pause_origin='manual')
        self.confirm(self.preview());self.assertTrue(self.controls.state['paused'])
        loaded=read(self.controls.file)['jobs'][0];self.assertTrue(loaded['publication_only']);self.assertEqual(loaded['approved_copy']['result'],str(self.result))

    def test_profile_is_immediately_visible_without_expensive_snapshot(self):
        result=self.controls.action(dict(action='resource-profile',profile='faster'));self.assertEqual(result['profile'],'faster')
        with patch.object(self.controls,'_refresh_poll'):
            self.controls.poll_checked=float('inf')
            self.assertEqual(self.controls.poll()['resource_profile'],'faster')

    def test_shared_publication_updates_receipt_savings_and_cleans_generated_copy(self):
        self.confirm(self.preview())
        def publisher(command,**kwargs):
            from validated_replace import replace_validated
            self.assertIn('publish_worker',command);self.assertNotIn('auto_optimize',command)
            record=replace_validated(self.source,self.media,self.media,self.result,25,self.identifier)
            class Child:
                def wait(self):return 0
            return Child()
        with patch('control_service.subprocess.Popen',side_effect=publisher),patch.object(self.controls,'build_command',side_effect=AssertionError('No encoding')):
            self.controls.step()
        self.assertEqual(self.source.read_bytes(),b'copy'*50)
        self.assertEqual(self.job['state'],'replaced');self.assertEqual(self.job['saved_bytes'],400)
        self.assertEqual(self.job['published_path'],str(self.source));self.assertFalse(self.copy.exists())
        self.assertEqual(read(self.result/'replacement.json')['state'],'replaced')

    @unittest.skipUnless(sys.platform.startswith('linux'),'Native publication worker runs on Linux only')
    def test_linux_actual_publication_worker_reuses_copy(self):
        self.confirm(self.preview())
        with patch.object(self.controls,'build_command',side_effect=AssertionError('No encoding')):
            self.controls.step()
        self.assertEqual(self.job['state'],'replaced',self.job.get('reason'))
        self.assertEqual(self.source.read_bytes(),b'copy'*50)
        self.assertFalse(self.copy.exists());self.assertTrue((self.folder/'publication.log').exists())
        self.assertTrue(list(self.folder.glob('job-*/job.json')))


if __name__=='__main__':unittest.main()
