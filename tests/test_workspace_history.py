import os
from pathlib import Path
import tempfile
import unittest
from autonomous_queue import write
from control_service import Controls, decision_evidence
from app_version import VERSION


class WorkspaceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.media=self.root/'media';self.output=self.root/'output'
        self.media.mkdir();self.output.mkdir();self.source=self.media/'a.mkv';self.source.write_bytes(b'original')
        self.c=Controls(self.media,self.output,lambda _:True,['hevc','av1']);self.c.ready=True

    def job(self, state='failed'):
        draft=self.c.preview(dict(path='a.mkv',mode='test',recheck=True))
        self.c.submit(draft['preview_id']);job=self.c.state['jobs'][-1];job.update(state=state,finished=12)
        return job

    def test_archive_undo_never_changes_processing_or_media(self):
        old=self.job();active=self.job('running');before=[dict(j) for j in self.c.state['jobs']]
        self.c.action(dict(action='archive-results'))
        self.assertEqual(self.c.state['view']['archived_ids'],[old['id']])
        self.assertEqual(self.c.state['jobs'],before)
        self.assertEqual(self.source.read_bytes(),b'original')
        self.c.action(dict(action='undo-archive'));self.assertEqual(self.c.state['view']['archived_ids'],[])
        self.assertEqual(self.c.state['jobs'],before)

    def test_archive_does_not_hide_jobs_that_finish_later(self):
        old=self.job();active=self.job('running');self.c.action(dict(action='archive-results'))
        active['state']='tested'
        self.assertNotIn(active['id'],self.c.state['view']['archived_ids'])
        self.c.action(dict(action='archive-results'));self.c.action(dict(action='undo-archive'))
        self.assertEqual(self.c.state['view']['archived_ids'],[old['id']])

    def test_migration_preferences_versions_and_batches(self):
        job=self.job();self.assertEqual(job['app_version'],VERSION);self.assertTrue(job['batch_id'])
        job.pop('app_version');self.c.state['extension_field']='preserved'
        self.c.action(dict(action='view-preferences',preferences=dict(sort='oldest',theme='dark',show_archived=True)))
        fresh=Controls(self.media,self.output,lambda _:True,['hevc','av1'])
        self.assertEqual(fresh.state['view']['theme'],'dark')
        self.assertNotIn('app_version',fresh.state['jobs'][0])
        self.assertEqual(fresh.state['extension_field'],'preserved')
        self.assertEqual(fresh.snapshot()['app_version'],VERSION)
        for prefs in ({'sort':'bad'},{'show_archived':1},{'delete_media':True}):
            with self.assertRaises(ValueError):self.c.action(dict(action='view-preferences',preferences=prefs))

    def test_retry_is_previewed_deduplicated_and_source_checked(self):
        job=self.job();preview=self.c.action(dict(action='retry-preview',job_id=job['id']))
        self.assertEqual(len(self.c.state['jobs']),1)
        self.assertEqual(self.c.submit(preview['preview_id'])['queued'],1)
        second=self.c.action(dict(action='retry-preview',job_id=job['id']))
        self.assertEqual(self.c.submit(second['preview_id'])['queued'],0)
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.c.action(dict(action='retry-preview',job_id=job['id']))

    def test_success_and_recovery_records_block_retry_and_cleanup(self):
        for state in ('replaced','awaiting-playback','pending','running','kept-original'):
            self.c.state['jobs']=[];job=self.job(state)
            with self.assertRaises(ValueError):self.c.action(dict(action='retry-preview',job_id=job['id']))
        self.c.state['jobs']=[];job=self.job();folder=self.c.request_folder(job)/'auto-test';folder.mkdir(parents=True)
        write(folder/'replacement.json',dict(state='published-verifying',backup=str(self.source)))
        info=self.c.action(dict(action='inspect-recovery',job_id=job['id']))
        self.assertFalse(info['retry_allowed']);self.assertFalse(info['cleanup_allowed'])
        for action in ('retry-preview','cleanup-preview'):
            with self.assertRaises(ValueError):self.c.action(dict(action=action,job_id=job['id']))
        self.assertTrue(self.source.exists())

    def test_publication_appearing_after_preview_blocks_submit(self):
        job=self.job();draft=self.c.action(dict(action='retry-preview',job_id=job['id']))
        folder=self.c.request_folder(job)/'auto-test';folder.mkdir(parents=True)
        write(folder/'replacement.json',dict(state='ready'))
        with self.assertRaises(ValueError):self.c.submit(draft['preview_id'])

    def test_cleanup_only_confirmed_generated_media_and_preserves_history(self):
        job=self.job('interrupted');folder=self.c.request_folder(job);folder.mkdir()
        video=folder/'partial.mkv';video.write_bytes(b'copy');report=folder/'job.json';report.write_text('{}')
        backup=folder/'keep.mkv.original';backup.write_bytes(b'backup')
        preview=self.c.action(dict(action='cleanup-preview',job_id=job['id']))
        self.assertTrue(video.exists());self.assertEqual(preview['bytes'],4)
        with self.assertRaises(ValueError):self.c.action(dict(action='cleanup-confirm',job_id=job['id'],cleanup_id=preview['cleanup_id']))
        result=self.c.action(dict(action='cleanup-confirm',job_id=job['id'],cleanup_id=preview['cleanup_id'],confirm=True))
        self.assertEqual(result['removed'],[str(video)])
        self.assertTrue(report.exists());self.assertTrue(backup.exists());self.assertTrue(self.source.exists())
        self.assertEqual(job['state'],'interrupted');self.assertEqual(len(job['cleanup_history']),1)
        with self.assertRaises(ValueError):self.c.action(dict(action='cleanup-confirm',job_id=job['id'],cleanup_id=preview['cleanup_id'],confirm=True))

    def test_cleanup_changed_linked_and_active_files_rejected(self):
        job=self.job();folder=self.c.request_folder(job);folder.mkdir();video=folder/'test.mkv';video.write_bytes(b'copy')
        draft=self.c.action(dict(action='cleanup-preview',job_id=job['id']));video.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.c.action(dict(action='cleanup-confirm',job_id=job['id'],cleanup_id=draft['cleanup_id'],confirm=True))
        self.assertTrue(video.exists())
        os.link(self.source,folder/'linked.mkv')
        with self.assertRaises(ValueError):self.c.action(dict(action='cleanup-preview',job_id=job['id']))
        job['state']='running'
        with self.assertRaises(ValueError):self.c.action(dict(action='cleanup-preview',job_id=job['id']))

    def test_all_history_remains_available_after_upgrade(self):
        base=self.job();self.c.state['jobs']=[dict(base,id=f'{i:032x}') for i in range(130)]
        self.assertEqual(len(self.c.snapshot()['jobs']),130)

    def test_retry_replacement_requires_fresh_explicit_confirmation(self):
        self.c.readonly=lambda _:False;self.c.replacement_root=self.media
        draft=self.c.preview(dict(path='a.mkv',mode='replace'))
        self.c.submit(draft['preview_id'],True);job=self.c.state['jobs'][0];job['state']='failed'
        retry=self.c.action(dict(action='retry-preview',job_id=job['id']))
        with self.assertRaises(ValueError):self.c.submit(retry['preview_id'])
        self.assertEqual(self.c.submit(retry['preview_id'],True)['queued'],1)
        self.assertEqual(self.source.read_bytes(),b'original')

    def test_no_history_writes_without_worker_ownership(self):
        job=self.job();self.c.ready=False
        for action in ('archive-results','undo-archive','cleanup-preview','retry-preview'):
            with self.assertRaises(ValueError):self.c.action(dict(action=action,job_id=job['id']))
        self.assertEqual(self.c.action(dict(action='inspect-recovery',job_id=job['id']))['job_id'],job['id'])

    def test_orphan_source_backup_blocks_recovery_actions(self):
        job=self.job();backup=self.source.with_name(self.source.name+'.muxmender-'+job['id']+'.original')
        backup.write_bytes(b'original')
        info=self.c.action(dict(action='inspect-recovery',job_id=job['id']))
        self.assertEqual(info['recovery_files'],[str(backup)])
        self.assertFalse(info['cleanup_allowed']);self.assertFalse(info['retry_allowed'])

    def test_evidence_does_not_invent_missing_quality(self):
        write(self.output/'trials.json',dict(trials=[dict(id='test',samples=[dict(quality=dict(mean=96,p5=92,passed=True)),dict(quality=dict(mean=float('nan'),p5=93))])]))
        result=decision_evidence(self.output,dict(estimated_savings_percent=12))
        self.assertEqual(len(result['quality'][0]['samples']),1)
        self.assertEqual(result['quality'][0]['samples'][0]['mean'],96)
        self.assertEqual(result['estimated_savings_percent'],12)


if __name__=='__main__':unittest.main()
