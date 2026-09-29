import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('fel_research_cli',Path(__file__).resolve().parents[1]/'tools/dv_fel_research.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)


class FelResearchCliTests(unittest.TestCase):
    def test_dry_run_writes_nothing_and_execution_needs_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'generated fixture')
            output=root/'research'
            with patch.object(cli,'encode_fel_research_candidate') as encode:
                self.assertEqual(cli.main([str(source),'--output-dir',str(output)]),0)
                self.assertFalse(output.exists())
                with self.assertRaisesRegex(ValueError,'acknowledge'):
                    cli.main([str(source),'--output-dir',str(output),'--execute'])
                self.assertFalse(output.exists())
                encode.assert_not_called()

    def test_existing_output_and_source_ancestor_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'generated fixture')
            output=root/'research';output.mkdir()
            with patch.object(cli,'encode_fel_research_candidate') as encode:
                for target,exception in ((output,FileExistsError),(root,ValueError),(source,ValueError)):
                    with self.assertRaises(exception):
                        cli.main([str(source),'--output-dir',str(target),'--execute','--acknowledge-unvalidated-fel'])
                encode.assert_not_called()
            self.assertEqual(source.read_bytes(),b'generated fixture')
