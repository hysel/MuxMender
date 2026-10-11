import io
import tarfile
import unittest
from tools.stage_conda_materials import retained_members, source_rows


class CondaMaterials(unittest.TestCase):
    def test_source_pins_required(self):
        with self.assertRaises(ValueError):
            source_rows({'source': {'url': 'https://example.invalid/source'}})
        rows = source_rows({'source': {'url': 'https://example.invalid/source', 'sha256': 'a'*64}})
        self.assertEqual(rows[0]['urls'], ['https://example.invalid/source'])

    def test_traversal_and_links_rejected_before_extraction(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('info/link', tarfile.SYMTYPE)]:
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode='w') as archive:
                member = tarfile.TarInfo(name); member.type = kind
                archive.addfile(member)
            data.seek(0)
            with tarfile.open(fileobj=data) as archive, self.assertRaises(ValueError):
                retained_members(archive)

    def test_only_notices_and_recipes_retained(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w') as archive:
            for name in ('info/recipe/meta.yaml', 'info/licenses/COPYING', 'info/test/run.py'):
                archive.addfile(tarfile.TarInfo(name))
        data.seek(0)
        with tarfile.open(fileobj=data) as archive:
            self.assertEqual([m.name for m in retained_members(archive)],
                             ['info/recipe/meta.yaml', 'info/licenses/COPYING'])
