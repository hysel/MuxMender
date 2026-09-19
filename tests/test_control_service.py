import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import control_service as cs
from dashboard import Catalog, make_handler
from autonomous_queue import write


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.media=self.root/'media';self.output=self.root/'output'
        self.media.mkdir();self.output.mkdir()
        self.source=self.media/'test.mkv';self.source.write_bytes(b'original')
        self.controls=cs.Controls(self.media,self.output,lambda _:True,['hevc','av1'])
        self.controls.ready=True

    def draft(self,**settings):
        return self.controls.preview(dict(path='test.mkv',**settings))

    def test_preview_and_keep_never_encode_or_modify_media(self):
        draft=self.draft(mode='keep')
        self.assertEqual(len(draft['files']),1)
        with patch.object(cs.subprocess,'Popen') as process:
            self.controls.submit(draft['preview_id']);self.controls.step();process.assert_not_called()
        self.assertEqual(self.controls.state['jobs'][0]['state'],'kept-original')
        self.assertEqual(self.source.read_bytes(),b'original')

    def test_modes_and_manual_options_map_to_safe_commands(self):
        for mode in ('analyze','test','encode'):
            settings=self.controls.settings(dict(mode=mode,codec='hevc',hardware='nvidia',quality='transparent'))
            command=self.controls.build_command(dict(source=str(self.source),settings=settings),self.output)
            self.assertEqual('--execute' in command,mode!='analyze')
            self.assertEqual('--encode-best' in command,mode=='encode')
            self.assertEqual(command[command.index('--playback-verified-codecs')+1],'hevc')
            self.assertIn('transparent',command)
            self.assertNotIn('--vmaf-mean',command)
            self.assertNotIn('--vmaf-p5',command)

    def test_reject_unknown_unsafe_or_unverified_settings(self):
        for data in [dict(codec='h264'),dict(hardware='cpu'),dict(quality='bad'),dict(minimum_savings=0),
                     dict(minimum_savings=float('nan')),dict(delete_original=True),dict(recursive='yes')]:
            with self.assertRaises(ValueError):self.controls.settings(data)
        self.controls.codecs=['hevc']
        with self.assertRaises(ValueError):self.draft(mode='encode',codec='av1')

    def test_scope_traversal_and_changed_file_protection(self):
        for path in ('../other.mkv',str(self.root)):
            with self.assertRaises(ValueError):self.controls.resolve(path)
        draft=self.draft()
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.controls.submit(draft['preview_id'])
        self.assertFalse(self.controls.state['jobs'])

    def test_dedup_expiry_and_replay(self):
        draft=self.draft(mode='test')
        self.assertEqual(self.controls.submit(draft['preview_id'])['queued'],1)
        with self.assertRaises(ValueError):self.controls.submit(draft['preview_id'])
        duplicate=self.draft(mode='test')
        self.assertEqual(self.controls.submit(duplicate['preview_id'])['queued'],0)
        expired=self.draft();self.controls.drafts[expired['preview_id']]['expires']=0
        with self.assertRaises(ValueError):self.controls.submit(expired['preview_id'])

    def test_folder_recursion_and_limit(self):
        folder=self.media/'sub';folder.mkdir();(folder/'nested.mp4').write_bytes(b'video')
        self.assertEqual(len(self.controls.preview(dict(path='.'))['files']),2)
        self.assertEqual(len(self.controls.preview(dict(path='.',recursive=False))['files']),1)
        nested=self.controls.browse('.',videos=True)
        self.assertEqual(len(nested['entries']),2)
        self.assertTrue(any('nested.mp4' in row['name'] for row in nested['entries']))
        self.assertEqual(len(self.controls.browse('.',videos=True,recursive=False)['entries']),1)
        self.assertEqual(len(self.controls.preview(dict(path='.',recursive=True))['files']),2)
        for i in range(101):(folder/f'{i}.mkv').write_bytes(b'v')
        draft=self.controls.preview(dict(path='sub'))
        self.assertEqual(len(draft['files']),102)
        self.assertEqual(self.controls.submit(draft['preview_id'])['queued'],102)
        self.assertEqual(len(self.controls.browse('sub')['entries']),100)
        self.assertEqual(self.controls.browse('sub')['next_offset'],100)

    def test_lifetime_counts_only_confirmed_replacements(self):
        self.controls.state['jobs']=[dict(id='one',state='replaced',original_bytes=1000,output_bytes=600,saved_bytes=400),
                                     dict(id='copy',state='awaiting-playback',saved_bytes=900)]
        folder=self.controls.root/'request-manual'/'auto-test';folder.mkdir(parents=True)
        write(folder/'approved-replacement.json',dict(original_removed=True,old_bytes=2000,new_bytes=1000,output_sha256='a'*64))
        result=self.controls.lifetime_savings()
        self.assertEqual(result['saved_bytes'],1400)
        self.assertEqual(result['replaced_files'],2)
        self.assertAlmostEqual(result['percent'],100*1400/3000)
        self.controls.state['jobs'].append(dict(id='manual',state='replaced',original_bytes=2000,output_bytes=1000,saved_bytes=1000))
        self.assertEqual(self.controls.lifetime_savings()['saved_bytes'],1400)

    def test_readonly_pause_and_space_guards(self):
        self.controls.submit(self.draft(mode='encode')['preview_id'])
        with patch.object(cs.subprocess,'Popen') as process:
            self.controls.action(dict(action='pause'));self.controls.step()
            self.controls.action(dict(action='resume'))
            with patch.object(cs.shutil,'disk_usage',return_value=Mock(free=1)):self.controls.step()
            process.assert_not_called()
        self.controls.readonly=lambda _:False
        with self.assertRaises(ValueError):self.draft()

    def test_worker_result_and_durable_state(self):
        self.controls.submit(self.draft(mode='encode')['preview_id'])
        def worker(command,**kwargs):
            folder=Path(command[command.index('--output-dir')+1])/'auto-result';folder.mkdir()
            candidate=folder/'full-hevc.mkv';candidate.write_bytes(b'copy')
            write(folder/'status.json',dict(state='validated-copy-awaiting-playback',source=str(self.source),
                output=str(candidate),source_sha256='a'*64,output_sha256='b'*64))
            return Mock(wait=lambda:0)
        with patch.object(cs.subprocess,'Popen',side_effect=worker):self.controls.step()
        self.assertEqual(self.controls.state['jobs'][0]['state'],'awaiting-playback')
        resumed=cs.Controls(self.media,self.output,lambda _:True,['hevc'])
        self.assertEqual(resumed.state['jobs'][0]['state'],'awaiting-playback')
        self.assertEqual(self.source.read_bytes(),b'original')

    def test_twice_failed_pauses_queue(self):
        for name in ('test.mkv','second.mkv'):
            (self.media/name).write_bytes(b'video')
            draft=self.controls.preview(dict(path=name,mode='test'));self.controls.submit(draft['preview_id'])
        with patch.object(cs.subprocess,'Popen',return_value=Mock(wait=lambda:1)):
            self.controls.step();self.controls.step()
        self.assertTrue(self.controls.state['paused'])
        self.assertIn('repeated processing failures',self.controls.snapshot()['pause_reason'])

    def test_efficiency_decision_is_saved_but_inconclusive_is_failure(self):
        for code,expected in [('already_efficient_for_settings','skipped'),('evaluation_inconclusive','failed')]:
            self.controls.state['jobs']=[]
            self.controls.submit(self.draft(mode='test')['preview_id'])
            def worker(command,**kwargs):
                folder=Path(command[command.index('--output-dir')+1])/'auto-result';folder.mkdir()
                write(folder/'status.json',dict(state='trials-completed',decision=dict(
                    action='keep_original',reason_code=code,reason='Explanation',
                    cacheable=code=='already_efficient_for_settings')))
                return Mock(wait=lambda:0)
            with patch.object(cs.subprocess,'Popen',side_effect=worker):self.controls.step()
            job=self.controls.state['jobs'][0]
            self.assertEqual(job['state'],expected)
            self.assertEqual(job['decision_code'],code)
            self.assertEqual(bool(job.get('history_decision')),expected=='skipped')

    def test_unsupported_is_skipped_without_failure(self):
        self.controls.submit(self.draft(mode='analyze')['preview_id'])
        def worker(command,**kwargs):
            folder=Path(command[command.index('--output-dir')+1])
            write(folder/'eligibility.json',dict(state='unsupported',reason='Unknown color/HDR requires specialized review'))
            return Mock(wait=lambda:0)
        with patch.object(cs.subprocess,'Popen',side_effect=worker):self.controls.step()
        self.assertEqual(self.controls.state['jobs'][0]['state'],'skipped')
        self.assertEqual(self.controls.state['failures'],0)
        self.assertFalse(self.controls.state['paused'])

    def test_replacement_requires_enable_and_confirmation(self):
        with self.assertRaises(ValueError):self.draft(mode='replace')
        self.controls.replacement_root=self.media
        self.controls.readonly=lambda _:False
        draft=self.draft(mode='replace')
        with self.assertRaises(ValueError):self.controls.submit(draft['preview_id'])
        self.controls.submit(draft['preview_id'],True)
        command=self.controls.build_command(self.controls.state['jobs'][0],self.output/'new')
        self.assertIn('--encode-best',command)

    def test_single_writable_mount_preserves_copy_default(self):
        self.controls.replacement_root=self.media
        self.controls.readonly=lambda _:False
        draft=self.draft(mode='encode')
        self.controls.submit(draft['preview_id'])
        self.assertEqual(self.controls.state['jobs'][0]['settings']['mode'],'encode')
        self.assertEqual(self.source.read_bytes(),b'original')

    def test_replacement_rechecks_readonly_at_submit(self):
        self.controls.replacement_root=self.media
        with self.assertRaises(ValueError):self.draft(mode='replace')
        self.controls.readonly=lambda _:False
        draft=self.draft(mode='replace')
        self.controls.readonly=lambda _:True
        with self.assertRaises(ValueError):self.controls.submit(draft['preview_id'],True)

    def test_writable_mount_without_opt_in_rejected(self):
        self.controls.readonly=lambda _:False
        for mode in ('analyze','test','encode','keep'):
            with self.assertRaises(ValueError):self.draft(mode=mode)

    def test_mixed_replacement_folder_and_conflict_skip(self):
        self.controls.replacement_root=self.media;self.controls.readonly=lambda _:False
        (self.media/'test.avi').write_bytes(b'avi')
        (self.media/'another.mp4').write_bytes(b'mp4')
        draft=self.controls.preview(dict(path='.',mode='replace'))
        self.assertEqual(len(draft['files']),3)
        self.controls.submit(draft['preview_id'],True)
        self.controls.state['jobs'].sort(key=lambda j:not j['source'].endswith('.avi'))
        with patch.object(cs.subprocess,'Popen') as process:self.controls.step();process.assert_not_called()
        self.assertEqual(self.controls.state['jobs'][0]['state'],'skipped')
        self.assertFalse(self.controls.state['paused'])
        self.assertEqual((self.media/'test.avi').read_bytes(),b'avi')

    @unittest.skipUnless(os.name=='posix','Linux service locking and symlinks')
    def test_symlink_escape_and_restart(self):
        (self.media/'escape').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):self.controls.resolve('escape')
        self.controls.submit(self.draft()['preview_id'])
        self.controls.state['jobs'][0]['state']='running';self.controls.save()
        self.controls.stop_event.set();self.controls.loop()
        self.assertEqual(self.controls.state['jobs'][0]['state'],'interrupted')
        self.assertTrue(self.controls.state['paused'])

    def test_http_auth_origin_csrf_and_bounded_requests(self):
        base=make_handler(Catalog(self.output),allowed_hosts=('nas:8767',),authorize=lambda s:s=='test-auth')
        server=ThreadingHTTPServer(('127.0.0.1',0),cs.handler(base,self.controls))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(method,path,body=None,**headers):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            defaults={'Host':'nas:8767','Authorization':'test-auth','Origin':'http://nas:8767',
                      'Content-Type':'application/json','X-MuxMender-CSRF':self.controls.token}
            defaults.update(headers)
            connection.request(method,path,body=json.dumps(body) if body is not None else None,headers=defaults)
            response=connection.getresponse();code=response.status;response.read();connection.close();return code
        try:
            self.assertEqual(request('GET','/api/media'),200)
            self.assertEqual(request('GET','/api/controls',Authorization=''),401)
            self.assertEqual(request('GET','/api/media?path=..'),400)
            self.assertEqual(request('GET','/api/controls',Host='evil:8767'),403)
            self.assertEqual(request('POST','/api/control',dict(action='pause'),Origin='http://evil'),403)
            self.assertEqual(request('POST','/api/control',dict(action='pause'),**{'X-MuxMender-CSRF':'bad'}),403)
            self.assertEqual(request('POST','/api/control',dict(action='pause')),200)
            self.assertEqual(request('POST','/api/control',dict(action='delete')),400)
            self.assertEqual(request('POST','/api/control',dict(action='preview',settings=dict(path='test.mkv'))),200)
        finally:server.shutdown();thread.join();server.server_close()


if __name__=='__main__':unittest.main()
