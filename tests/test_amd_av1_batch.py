import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import amd_av1_batch as batch


class BatchSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root/'media'; self.media.mkdir()
        self.output = self.root/'outputs'
        self.sources = [self.media/'a.mkv', self.media/'b.mkv']
        for source in self.sources: source.write_bytes(b'original video fixture')
        self.plan = dict(schema='muxmender-amd-batch-v1', source=str(self.media), output_root=str(self.output),
                         entries=[dict(source=str(p),fingerprint=batch.fingerprint(p),action='preview-candidate') for p in self.sources])
        self.args = SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',max_files=2)
        self.patches = [patch.object(batch.av.mm,'gpu_vendors',return_value={'amd'}),
                        patch.object(batch.av.mm,'ffmpeg_encoder_names',return_value={'av1_amf'}),
                        patch.object(batch.shutil,'disk_usage',return_value=SimpleNamespace(free=100*1024**3)),
                        patch.object(batch.av.np,'stage')]
        self.mocks = [self.enterContext(p) for p in self.patches]
        # Filesystem timestamp resolution is not an ordering guarantee (e.g.
        # two synthetic batches can finish within one Linux filesystem tick).
        real_save=batch.worker.save
        self.latest_report=None
        def observe_save(path,data):
            result=real_save(path,data)
            if path.name=='batch.json':self.latest_report=path
            return result
        self.enterContext(patch.object(batch.worker,'save',side_effect=observe_save))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def runner(self, args, on_result, guard):
        self.assertTrue(args.full)
        guard()
        output=args.output_dir/(args.source.stem+'.mkv')
        with output.open('xb') as stream: stream.write(b'encoded fixture')
        value=batch.digest(args.source)
        on_result(dict(status=batch.SUCCESS,output=str(output),original_size_mtime_unchanged=True,
                       source_sha256_before=value,source_sha256_after=value,total_savings_percent=40))
        return 0

    def report(self):
        path=self.latest_report
        self.assertIsNotNone(path)
        return json.loads(path.read_text())

    def test_sequential_success_originals_retained_and_repeat_skipped(self):
        with patch.object(batch,'digest',wraps=batch.digest):
            self.assertEqual(batch.execute(self.plan,self.args,self.runner),0)
            with patch.object(batch.av,'run') as runner:
                self.assertEqual(batch.execute(self.plan,self.args,runner),0)
                runner.assert_not_called()
        self.assertEqual([r['status'] for r in self.report()['entries']],['already-validated']*2)
        self.assertFalse((self.output/'.amd-batch.lock').exists())
        for source in self.sources: self.assertEqual(source.read_bytes(),b'original video fixture')

    def test_file_limit_and_unsupported_skip(self):
        self.args.max_files=1
        self.plan['entries'].append(dict(source='unsupported',action='keep-as-is'))
        self.assertEqual(batch.execute(self.plan,self.args,self.runner),0)
        self.assertEqual([r['status'] for r in self.report()['entries']],['validated-copy','deferred-file-limit','skipped'])

    def test_probe_errors_are_not_reported_as_success(self):
        self.plan['entries']=[dict(source=str(self.sources[0]),action='probe-error',reason='Unreadable')]
        with patch.object(batch.av,'run') as runner:
            self.assertEqual(batch.execute(self.plan,self.args,runner),1)
            runner.assert_not_called()
        self.assertEqual(self.report()['status'],'completed-with-errors')

    def test_changed_source_rejected_before_encode(self):
        self.sources[0].write_bytes(b'changed externally')
        self.plan['entries']=self.plan['entries'][:1]
        with patch.object(batch.av,'run') as runner:
            self.assertEqual(batch.execute(self.plan,self.args,runner),1)
            runner.assert_not_called()
        self.assertEqual(self.report()['entries'][0]['status'],'failed-retained')

    def test_corrupt_scan_skips_encode_and_continues(self):
        self.mocks[3].side_effect=[ValueError('Container integrity warning'),None]
        self.assertEqual(batch.execute(self.plan,self.args,self.runner),1)
        self.assertEqual([r['status'] for r in self.report()['entries']],['failed-retained','validated-copy'])

    def test_low_space_stops_and_releases_lock(self):
        self.mocks[2].return_value=SimpleNamespace(free=1024)
        with self.assertRaises(InterruptedError): batch.execute(self.plan,self.args,self.runner)
        self.assertEqual(self.report()['status'],'stopped')
        self.assertFalse((self.output/'.amd-batch.lock').exists())

    def test_existing_lock_not_removed(self):
        self.output.mkdir()
        lock=self.output/'.amd-batch.lock';lock.write_text('other owner')
        with self.assertRaises(FileExistsError): batch.execute(self.plan,self.args,self.runner)
        self.assertEqual(lock.read_text(),'other owner')

    def test_failed_partial_retained_and_not_cached(self):
        self.plan['entries']=self.plan['entries'][:1]
        def fail(args,**kwargs):
            (args.output_dir/'partial.mkv').write_bytes(b'partial')
            raise ValueError('Failed validation')
        self.assertEqual(batch.execute(self.plan,self.args,fail),1)
        self.assertTrue(list(self.output.glob('AMD-BATCH-*/partial.mkv')))
        self.assertFalse((self.output/'amd-batch-completed.json').exists())

    def test_missing_or_tampered_completed_output_reencoded(self):
        batch.execute(self.plan,self.args,self.runner)
        record=self.report()['entries'][0]
        Path(record['output']).write_bytes(b'changed')
        self.assertEqual(batch.execute(self.plan,self.args,self.runner),0)
        self.assertEqual([r['status'] for r in self.report()['entries']],['validated-copy','already-validated'])

    def test_stop_request_prevents_next_file(self):
        def stop_after_first(args,**kwargs):
            result=self.runner(args,**kwargs)
            (args.output_dir/'STOP').write_text('stop')
            return result
        with self.assertRaises(InterruptedError): batch.execute(self.plan,self.args,stop_after_first)
        self.assertEqual(self.report()['status'],'stopped')
        self.assertTrue(all(p.exists() for p in self.sources))

    def test_overlapping_output_rejected(self):
        for output in (self.media,self.media/'outputs',self.root):
            with self.assertRaises(ValueError): batch.disjoint(self.media,output)

    def test_dry_run_never_starts_encoder_or_creates_output(self):
        with patch.object(batch.planner,'probe_with_frame_color'),patch.object(batch.worker,'shape'),patch.object(batch.planner,'amd_av1_eligibility',return_value=('preview-candidate','eligible')),patch.object(batch,'execute') as execute:
            self.assertEqual(batch.main([str(self.media),'--output-dir',str(self.output)]),0)
            execute.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_outside_completed_output_not_accepted(self):
        row=self.plan['entries'][0]
        old=dict(fingerprint=row['fingerprint'],output=str(self.sources[1]))
        self.assertFalse(batch.completed_matches(row,old,self.output,lambda:None))


if __name__=='__main__': unittest.main()
