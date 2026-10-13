"""Linux process lifecycle test using a sleeping worker, never a media encoder."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from control_service import Controls,source_identity
from autonomous_queue import signature


@unittest.skipUnless(sys.platform.startswith('linux'),'Process-group interruption requires Linux')
class RestartServiceTests(unittest.TestCase):
    def wait_for(self,predicate):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.05)
        self.fail('Service state did not arrive within ten seconds')

    def test_shutdown_and_new_service_resume_without_manual_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);media=root/'media';output=root/'output'
            media.mkdir();output.mkdir();source=media/'generated.mkv';source.write_bytes(b'generated-fixture')
            def service():
                control=Controls(media,output,lambda _:False,['hevc','av1'],replacement_root=media)
                # No media process or GPU probe: only exercise queue/shutdown recovery.
                control.build_command=lambda *unused:[sys.executable,'-c','import time; time.sleep(60)']
                control.governor.admit=lambda *unused:True
                control.gpu_yield.tick=lambda *unused,**kwargs:dict(block_admission=False)
                return control
            first=service()
            first.state['jobs']=[dict(id='a'*32,source=str(source),signature=signature(source),
                source_identity=source_identity(source),settings=first.settings(dict(mode='encode')),
                state='pending',created=time.time())]
            first.save()
            try:
                first.start()
                self.wait_for(lambda:bool(first.children))
                first.stop()
                self.assertFalse(first.thread.is_alive())
                persisted=json.loads(first.file.read_text())
                self.assertEqual(persisted['jobs'][0]['service_restart']['state'],'requested')
                self.assertEqual(persisted['jobs'][0]['state'],'interrupted')
                second=service()
                try:
                    second.start()
                    self.wait_for(lambda:bool(second.children))
                    active=[j for j in second.state['jobs'] if j['state']=='running']
                    self.assertEqual(len(active),1)
                    self.assertEqual(active[0]['restart_of'],'a'*32)
                    self.assertFalse(second.state['paused'])
                    self.assertEqual(source.read_bytes(),b'generated-fixture')
                finally:second.stop()
            finally:
                if first.thread and first.thread.is_alive():first.stop()
