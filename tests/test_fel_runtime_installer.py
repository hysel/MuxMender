import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('fel_installer',Path(__file__).resolve().parents[1]/'tools/install_fel_runtime.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class RuntimeInstallerTests(unittest.TestCase):
    def test_dry_run_verifies_archives_without_creating_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'fixture.zip').write_bytes(b'fixture archive')
            checks={'fixture.zip':hashlib.sha256(b'fixture archive').hexdigest()}
            target=root/'runtime'
            with patch.object(installer,'CHECKSUMS',checks),redirect_stdout(io.StringIO()):
                installer.main(['--archives',str(root),'--destination',str(target)])
            self.assertFalse(target.exists())

    def test_checksum_failure_precedes_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'fixture.zip').write_bytes(b'bad')
            with patch.object(installer,'CHECKSUMS',{'fixture.zip':'0'*64}):
                with self.assertRaisesRegex(ValueError,'checksum'):installer.inspect_archives(root)
