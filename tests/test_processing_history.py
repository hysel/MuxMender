"""History is persistent, operation-aware, and never authorizes replacement."""
from pathlib import Path
import tempfile
import unittest

from autonomous_queue import signature, write
from control_service import Controls
from codec_selection import EVALUATION_POLICY


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.media=root/'media';self.media.mkdir()
        self.output=root/'output';self.output.mkdir()
        self.source=self.media/'movie.mp4';self.source.write_bytes(b'original')
        self.controls=self.open()

    def open(self):
        controls=Controls(self.media,self.output,lambda _:False,['hevc','av1'],replacement_root=self.media)
        controls.ready=True
        return controls

    def submit(self, **settings):
        draft=self.controls.preview(dict(path='.',mode='encode',**settings))
        return self.controls.submit(draft['preview_id'],confirm_replace=True)

    def record(self,state,mode='encode',**extra):
        job=dict(id='old',source=str(self.source),signature=signature(self.source),
                 settings=self.controls.settings(dict(mode=mode)),state=state,**extra)
        self.controls.state['jobs'].append(job);self.controls.save()
        return job

    def test_keep_survives_restart_and_settings_changes(self):
        self.record('kept-original',mode='keep')
        self.controls=self.open()
        result=self.submit(codec='hevc')
        self.assertEqual(result['queued'],0)
        self.assertEqual(result['history_skipped'][0]['job_id'],'old')
        self.assertEqual(self.source.read_bytes(),b'original')

    def test_efficient_decision_reused_after_restart_for_same_policy(self):
        self.record('skipped',history_decision=True,decision_code='already_efficient_for_settings',
                    reason='Already efficient for current settings',evaluation_policy=EVALUATION_POLICY)
        self.controls=self.open()
        self.assertEqual(self.submit()['queued'],0)

    def test_obsolete_evaluation_does_not_block_new_search_policy(self):
        for policy in (None,'old-search'):
            self.controls.state['jobs']=[]
            self.record('skipped',history_decision=True,decision_code='already_efficient_for_settings',evaluation_policy=policy)
            self.assertEqual(self.submit()['queued'],1)

    def test_active_claim_wins_even_with_obsolete_decision_fields(self):
        self.record('running',decision_code='already_efficient_for_settings',evaluation_policy='old-search')
        self.assertEqual(self.submit(codec='hevc')['queued'],0)

    def test_efficient_decision_retested_for_changed_policy_or_file(self):
        for settings in (dict(codec='hevc'),dict(hardware='nvidia'),dict(quality='compact'),
                         dict(minimum_savings=20),dict(recheck=True),dict(history_mode='retry')):
            self.controls.state['jobs']=[]
            self.record('skipped',history_decision=True,decision_code='already_efficient_for_settings',evaluation_policy=EVALUATION_POLICY)
            self.assertEqual(self.submit(**settings)['queued'],1,settings)
        self.controls.state['jobs']=[]
        self.record('skipped',history_decision=True,decision_code='already_efficient_for_settings')
        self.source.write_bytes(b'changed media')
        self.assertEqual(self.submit()['queued'],1)

    def test_changed_source_is_not_skipped(self):
        self.record('kept-original')
        self.source.write_bytes(b'new version')
        self.assertEqual(self.submit()['queued'],1)

    def test_recheck_overrides_terminal_not_active(self):
        self.record('kept-original')
        self.assertEqual(self.submit(recheck=True)['queued'],1)
        self.assertEqual(self.submit(recheck=True)['queued'],0)

    def test_failed_and_interrupted_are_retryable(self):
        for state in ('failed','interrupted'):
            self.controls.state['jobs']=[]
            self.record(state)
            self.assertEqual(self.submit()['queued'],1)

    def test_inspection_and_sample_success_allow_full_conversion(self):
        for state,mode in [('analyzed','analyze'),('tested','test')]:
            self.controls.state['jobs']=[]
            self.record(state,mode=mode)
            self.assertEqual(self.submit()['queued'],1)

    def test_decisions_skip_but_conflicts_can_be_retried(self):
        self.record('skipped',history_decision=True,reason='Quality threshold not met',evaluation_policy=EVALUATION_POLICY)
        self.assertEqual(self.submit()['queued'],0)
        self.controls.state['jobs']=[]
        self.record('skipped',reason='Destination already exists')
        self.assertEqual(self.submit()['queued'],1)

    def test_published_mkv_fingerprint_prevents_second_generation(self):
        published=self.media/'movie.mkv';published.write_bytes(b'converted')
        self.record('replaced',published_path=str(published),published_signature=signature(published))
        self.source.unlink()  # Temporary fixture only: emulate completed publication.
        self.controls=self.open()
        self.assertEqual(self.submit()['queued'],0)
        self.assertEqual(self.submit(recheck=True)['queued'],1)

    def test_safe_copy_does_not_block_explicit_replacement(self):
        self.record('awaiting-playback')
        self.assertEqual(self.submit()['queued'],0)
        draft=self.controls.preview(dict(path='.',mode='replace'))
        self.assertEqual(self.controls.submit(draft['preview_id'],True)['queued'],1)

    def test_legacy_trial_decision_is_recognized(self):
        self.record('skipped')
        folder=self.controls.root/'request-old'/'auto-old';folder.mkdir(parents=True)
        write(folder/'status.json',dict(state='trials-completed',decision=dict(action='keep_original',cacheable=True)))
        write(folder/'plan.json',dict(evaluation_policy=EVALUATION_POLICY))
        self.assertEqual(self.submit()['queued'],0)

    def test_full_size_rejection_retries_after_settings_change(self):
        self.record('skipped',history_decision=True,reason='Full output did not save enough space',evaluation_policy=EVALUATION_POLICY)
        self.assertEqual(self.submit()['queued'],0)
        self.assertEqual(self.submit(codec='hevc')['queued'],1)

    def test_unversioned_legacy_trial_is_not_a_current_policy_decision(self):
        self.record('skipped')
        folder=self.controls.root/'request-old'/'auto-old';folder.mkdir(parents=True)
        write(folder/'status.json',dict(state='trials-completed',decision=dict(action='keep_original',cacheable=True)))
        self.assertEqual(self.submit()['queued'],1)

    def test_preview_explains_skip_and_recheck_is_typed(self):
        self.record('kept-original',reason='User chose to keep')
        draft=self.controls.preview(dict(path='.'))
        self.assertIn('User chose to keep',draft['files'][0]['history_reason'])
        with self.assertRaises(ValueError):self.controls.settings(dict(recheck='yes'))

    def test_retry_only_retries_skips_failures_and_interruptions(self):
        for state in ('skipped','failed','interrupted'):
            self.controls.state['jobs']=[]
            self.record(state,history_decision=True)
            self.assertEqual(self.submit(history_mode='retry')['queued'],1)
            self.assertEqual(self.submit(history_mode='retry')['queued'],0)

    def test_retry_only_excludes_new_analyzed_tested_and_successful(self):
        self.assertEqual(self.submit(history_mode='retry')['queued'],0)
        for state in ('analyzed','tested','awaiting-playback','kept-original','running','pending'):
            self.controls.state['jobs']=[]
            self.record(state)
            self.assertEqual(self.submit(history_mode='retry')['queued'],0)

    def test_retry_only_protects_success_even_after_redundant_failure(self):
        self.record('awaiting-playback')
        self.source.write_bytes(b'previous manually published conversion')
        self.record('failed')
        self.assertEqual(self.submit(history_mode='retry')['queued'],0)

    def test_retry_only_protects_renamed_published_output(self):
        published=self.media/'movie.mkv';published.write_bytes(b'converted')
        self.record('replaced',published_path=str(published),published_signature=signature(published))
        self.source.unlink()
        self.assertEqual(self.submit(history_mode='retry')['queued'],0)

    def test_retry_only_does_not_treat_changed_version_as_failed(self):
        self.record('failed');self.source.write_bytes(b'new version')
        self.assertEqual(self.submit(history_mode='retry')['queued'],0)

    def test_retry_preview_explains_unselected_files_and_validates_mode(self):
        preview=self.controls.preview(dict(path='.',history_mode='retry'))
        self.assertIn('Retry only',preview['files'][0]['history_reason'])
        for settings in (dict(history_mode='invalid'),dict(history_mode='retry',recheck=True)):
            with self.assertRaises(ValueError):self.controls.settings(settings)


if __name__=='__main__':unittest.main()
