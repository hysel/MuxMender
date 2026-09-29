import json
from pathlib import Path
import tempfile
import unittest
from artifact_manifest import command_outputs,registered_outputs
from replacement_cleanup import prune_generated


class ManifestTests(unittest.TestCase):
    def test_explicit_owned_mutation_refreshes_cleanup_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'output.custom';source=root/'input.custom';source.write_bytes(b'original')
            with command_outputs(root,[str(out)]):out.write_bytes(b'temp')
            with command_outputs(root,[],mutated=[out]):out.write_bytes(b'metadata-restored')
            self.assertIn(out,registered_outputs(root))
            with self.assertRaises(ValueError),command_outputs(root,[],mutated=[source]):pass
            prune_generated(root,execute=True)
            self.assertFalse(out.exists());self.assertEqual(source.read_bytes(),b'original')

    def test_failed_owned_mutation_is_still_disposable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'output.custom'
            with command_outputs(root,[str(out)]):out.write_bytes(b'temp')
            with self.assertRaises(RuntimeError),command_outputs(root,[],mutated=[out]):
                out.write_bytes(b'partial');raise RuntimeError('editor failed')
            self.assertIn(out,registered_outputs(root))

    def test_unknown_suffix_registered_but_existing_inputs_and_logs_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.custom';source.write_bytes(b'original')
            out=root/'output.custom'
            with command_outputs(root,['tool',str(source),str(out)]):out.write_bytes(b'temporary')
            (root/'status.json').write_text('{}')
            prune_generated(root,execute=True)
            self.assertFalse(out.exists());self.assertEqual(source.read_bytes(),b'original')
            self.assertTrue((root/'status.json').exists())

    def test_changed_registered_file_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'output.custom'
            with command_outputs(root,[str(out)]):out.write_bytes(b'temp')
            out.write_bytes(b'changed externally')
            with self.assertRaises(ValueError):prune_generated(root,execute=True)
            self.assertTrue(out.exists())

    def test_manifest_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'generated-artifacts.jsonl').write_text(json.dumps(dict(path='../original.mkv',identity=[])))
            with self.assertRaises(ValueError):registered_outputs(root)
