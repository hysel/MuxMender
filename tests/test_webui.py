import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from webui import Manager,handler
from workflow_worker import Context


class WebUITests(unittest.TestCase):
    def test_filtered_pagination_preserves_original_line_identity(self):
        folder=self.root/'reports'/'filter-scan';folder.mkdir()
        records=[dict(path=f'/Shows/Episode-{i}.mkv',action='preview-candidate' if i%2 else 'needs-review') for i in range(8)]
        (folder/'files.jsonl').write_text('\n'.join([json.dumps(records[0]),'{broken',*[json.dumps(r) for r in records[1:]]]))
        scan=next(iter(self.manager.scans()))
        result=self.manager.rows(scan,1,2,'preview-candidate','SHOWS')
        self.assertEqual(result['total'],4)
        self.assertEqual(result['scanned'],8)
        self.assertEqual([r['id'] for r in result['rows']],[4,6])
        self.assertEqual(self.manager.row(scan,4)['path'],'/Shows/Episode-3.mkv')
        self.assertEqual(self.manager.rows(scan,0,100,'','absent')['total'],0)
        with self.assertRaises(ValueError):self.manager.rows(scan,action='unsafe')
        with self.assertRaises(ValueError):self.manager.rows(scan,query='x'*257)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.manager=Manager(self.root,start=False)
    def tearDown(self):
        self.manager.close();self.tmp.cleanup()

    def test_queue_scan_and_cancel_do_not_start_encoder(self):
        source=self.root/'media';source.mkdir()
        identifier=self.manager.enqueue({'kind':'scan','source':str(source)})
        self.assertEqual(self.manager.jobs()[0]['state'],'queued')
        self.manager.cancel(identifier)
        self.assertEqual(self.manager.jobs()[0]['state'],'cancelled')
        self.assertFalse((self.manager.folder(identifier)/'Optimized.mkv').exists())

    def test_approval_validation_and_no_command_injection(self):
        for payload in ({'kind':'convert'}, {'kind':'delete'}, {'kind':'scan','source':'relative'},
                        {'kind':'dependencies','hardware':'amd; delete'}, {'kind':'dependencies','codec':'evil'}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):self.manager.enqueue(payload)
        identifier=self.manager.enqueue({'kind':'dependencies','ffmpeg':'malicious'})
        request=json.loads((self.manager.folder(identifier)/'request.json').read_text())
        self.assertEqual(request['ffmpeg'],'ffmpeg')

    def test_invalid_ids_and_traversal(self):
        for identifier in ('../secret','a'*31,'X'*32,None):
            with self.assertRaises(ValueError):self.manager.folder(identifier)

    def test_local_token_and_origin_required(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.manager))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        port=server.server_port
        try:
            connection=http.client.HTTPConnection('127.0.0.1',port)
            for headers in ({},{'Origin':f'http://127.0.0.1:{port}'},
                            {'Origin':'http://evil.example','X-MuxMender-Token':self.manager.token}):
                connection.request('POST','/api/enqueue',json.dumps({'kind':'dependencies'}),headers={'Content-Type':'application/json',**headers})
                response=connection.getresponse();self.assertEqual(response.status,403);response.read()
            connection.request('GET','/api/session',headers={'Host':'evil.example'})
            response=connection.getresponse();self.assertEqual(response.status,403);response.read()
            connection.request('POST','/api/enqueue',json.dumps({'kind':'dependencies'}),headers={'Content-Type':'application/json',
                'Origin':f'http://127.0.0.1:{port}','X-MuxMender-Token':self.manager.token})
            response=connection.getresponse();self.assertEqual(response.status,201);response.read()
            connection.close()
        finally:server.shutdown();server.server_close();thread.join()

    def test_only_one_controller(self):
        with self.assertRaises(RuntimeError):Manager(self.root,start=False)

    def test_restart_requires_new_approval(self):
        identifier=self.manager.enqueue({'kind':'dependencies'})
        self.manager.close()
        self.manager=Manager(self.root,start=False)
        self.assertEqual(self.manager.jobs()[0]['state'],'interrupted')
        self.assertEqual(len(self.manager.pending),0)

    def test_guard_cancellation_and_disk_reserve(self):
        identifier=self.manager.enqueue({'kind':'dependencies'});folder=self.manager.folder(identifier)
        ctx=Context(folder)
        with patch('workflow_worker.shutil.disk_usage') as usage:
            usage.return_value.free=0
            with self.assertRaises(RuntimeError):ctx.guard()
        (folder/'STOP').touch()
        with self.assertRaises(InterruptedError):ctx.guard()

    def test_unapproved_scan_row_cannot_convert(self):
        scan=self.root/'reports'/'scan';scan.mkdir()
        (scan/'files.jsonl').write_text(json.dumps({'path':'source.mkv','action':'needs-review'})+'\n')
        identifier=next(iter(self.manager.scans()))
        with self.assertRaises(ValueError):self.manager.enqueue({'kind':'convert','approved':True,'scan':identifier,'row':0})

    def test_stop_signal_does_not_delete_files(self):
        identifier=self.manager.enqueue({'kind':'dependencies'});folder=self.manager.folder(identifier)
        data=json.loads((folder/'job.json').read_text());data['state']='running'
        (folder/'job.json').write_text(json.dumps(data))
        generated=folder/'retained-fixture.txt';generated.write_text('keep')
        self.manager.cancel(identifier)
        self.assertTrue((folder/'STOP').exists());self.assertEqual(generated.read_text(),'keep')
