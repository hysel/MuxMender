import ast
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.build_app_release import prepared_gpu_monitor

ROOT=Path(__file__).resolve().parents[1]


class MonitorPackageTests(unittest.TestCase):
    def test_package_contains_matching_collector(self):
        tree=ast.parse(prepared_gpu_monitor(ROOT))
        embedded=next(ast.literal_eval(n.value) for n in tree.body
                      if isinstance(n,ast.Assign) and any(
                          isinstance(t,ast.Name) and t.id=='COLLECTOR_B64' for t in n.targets))
        self.assertEqual(base64.b64decode(embedded),
                         (ROOT/'python/gpu_activity.py').read_bytes())


@unittest.skipUnless(sys.platform.startswith('linux'),'Host installer uses Linux ownership and services')
class MonitorStartupTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('monitor_installer',
            ROOT/'deploy/truenas/install_gpu_monitor.py')
        self.module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_creates_one_startup_task_when_missing(self):
        with patch.object(self.module.shutil,'which',return_value='/usr/bin/midclt'), \
             patch.object(self.module.subprocess,'run',return_value=
                          subprocess.CompletedProcess([],0,stdout='[]')) as run:
            self.module.configure_startup()
        self.assertEqual(run.call_count,2)
        command=run.call_args_list[1].args[0]
        self.assertEqual(command[:3],['midclt','call','initshutdownscript.create'])
        settings=json.loads(command[3])
        self.assertEqual(settings['when'],'POSTINIT')
        self.assertTrue(settings['enabled'])

    def test_reuses_enabled_startup_task(self):
        command='/usr/bin/python3 -I -B /root/muxmender-gpu-monitor/bootstrap.py --start'
        tasks=[dict(id=12,type='COMMAND',command=command,when='POSTINIT',enabled=True,timeout=60)]
        with patch.object(self.module.shutil,'which',return_value='/usr/bin/midclt'), \
             patch.object(self.module.subprocess,'run',return_value=
                          subprocess.CompletedProcess([],0,stdout=json.dumps(tasks))) as run:
            self.module.configure_startup()
        self.assertEqual(run.call_count,1)

    def test_restores_disabled_startup_task(self):
        command='/usr/bin/python3 -I -B /root/muxmender-gpu-monitor/bootstrap.py --start'
        tasks=[dict(id=12,type='COMMAND',command=command,when='POSTINIT',enabled=False,timeout=10)]
        with patch.object(self.module.shutil,'which',return_value='/usr/bin/midclt'), \
             patch.object(self.module.subprocess,'run',return_value=
                          subprocess.CompletedProcess([],0,stdout=json.dumps(tasks))) as run:
            self.module.configure_startup()
        self.assertEqual(run.call_args.args[0][:4],
                         ['midclt','call','initshutdownscript.update','12'])

    def test_telemetry_mount_survives_runtime_cleanup(self):
        self.assertEqual(self.module.DATA,Path('/var/lib/muxmender-gpu-monitor'))
        text=self.module.service_text(3005)
        self.assertIn('ReadWritePaths=/var/lib/muxmender-gpu-monitor',text)
        self.assertIn('InaccessiblePaths=-/mnt -/media',text)

    def test_upgrade_replaces_only_validated_root_owned_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bootstrap.py'
            path.write_bytes(b'old')
            path.chmod(0o600)
            info=SimpleNamespace(st_uid=0,st_mode=path.lstat().st_mode)
            with patch.object(Path,'lstat',return_value=info):
                self.module.protected_file(path,b'new',replace=True)
            self.assertEqual(path.read_bytes(),b'new')
            self.assertFalse(path.with_name('bootstrap.py.new').exists())

    def test_upgrade_refuses_writable_monitor_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bootstrap.py'
            path.write_bytes(b'old')
            path.chmod(0o666)
            with self.assertRaisesRegex(ValueError,'Unsafe existing file'):
                self.module.protected_file(path,b'new',replace=True)
            self.assertEqual(path.read_bytes(),b'old')


if __name__=='__main__':
    unittest.main()
