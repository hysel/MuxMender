import io
import json
import unittest
from unittest.mock import patch
from tools.monitor_queue import snapshot


class MonitorTests(unittest.TestCase):
    def test_only_status_fields_are_retained(self):
        data={'csrf_token':'secret','password':'secret','app_version':'test','paused':False,
              'jobs':[{'id':'one','source':'/media/movie.mkv','state':'running',
                       'private_setting':'secret','settings':{'password':'secret'}}]}
        with patch('tools.monitor_queue.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(data).encode())) as call:
            result=snapshot('http://server:8767/')
        self.assertEqual(call.call_args.args[0],'http://server:8767/api/controls')
        self.assertEqual(call.call_args.kwargs['timeout'],20)
        self.assertNotIn('secret',json.dumps(result))
        self.assertEqual(result['jobs'],[{'id':'one','source':'/media/movie.mkv','state':'running'}])

    def test_missing_jobs_is_not_reported_as_finished_queue(self):
        with patch('tools.monitor_queue.urllib.request.urlopen',return_value=io.BytesIO(b'{}')):
            with self.assertRaises(ValueError):snapshot('http://server')
