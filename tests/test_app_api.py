import http.client
import ast
import json
from pathlib import Path
import tempfile
import threading
import re
import unittest
from http.server import ThreadingHTTPServer

from app_api import describe
from app_version import VERSION
from dashboard import Catalog,make_handler


class AppApiTests(unittest.TestCase):
    def test_api_and_shared_performance_modules_ship_in_python_package(self):
        config=(Path(__file__).resolve().parents[1]/'pyproject.toml').read_text()
        modules=set(ast.literal_eval(re.search(r'py-modules\s*=\s*(\[[^\]]+\])',config).group(1)))
        for name in ('app_api','gpu_admission','parallel_frame_audit','source_evidence_cache'):
            self.assertIn(name,modules)

    def test_discovery_does_not_claim_unavailable_controls(self):
        data=describe()
        self.assertEqual(data['api_version'],1)
        self.assertEqual(data['app_version'],VERSION)
        self.assertEqual(set(data['endpoints']),{'jobs'})
        self.assertFalse(data['controls_enabled'])
        self.assertIsNone(data['writes']['token_source'])
        enabled=describe(controls=True)
        self.assertEqual(enabled['endpoints']['actions']['path'],'/api/control')
        self.assertNotIn('csrf_token',enabled)
        self.assertIn('not authentication',enabled['writes']['note'])

    def test_bundled_endpoint_obeys_host_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Catalog(Path(folder)),allowed_hosts=('nas:8767',)))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                def request(host):
                    connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
                    connection.request('GET','/api',headers={'Host':host})
                    response=connection.getresponse();result=(response.status,response.read(),response.getheader('Cache-Control'))
                    connection.close();return result
                code,body,cache=request('nas:8767')
                self.assertEqual(code,200);self.assertEqual(json.loads(body)['app_version'],VERSION)
                self.assertEqual(cache,'no-store');self.assertEqual(request('untrusted:8767')[0],403)
            finally:server.shutdown();thread.join();server.server_close()
