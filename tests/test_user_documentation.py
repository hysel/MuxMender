"""Keep published docs limited to installation, configuration and UI help."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
USER_DOCS = {
    'README.md', 'GETTING-STARTED.md', 'output-presets.md',
    'processing-timeouts.md', 'post-task-cleanup.md', 'replacement-cleanup.md',
    'file-age-filter.md', 'size-aware-savings.md', 'stable-updates.md',
    'gpu-monitor-setup.md', 'processing-dashboard.md', 'TESTED-FORMATS.md',
    'SUPPORTED-USE-CASES.md',
}


class UserDocumentation(unittest.TestCase):
    def test_top_level_contains_only_user_guides(self):
        actual = {p.name for p in (ROOT / 'docs').iterdir() if p.is_file()}
        self.assertEqual(actual, USER_DOCS)

    def test_user_guide_local_links_exist(self):
        for path in [ROOT / 'README.md', *(ROOT / 'docs').rglob('*.md')]:
            for link in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
                if '://' in link or link.startswith('#'):
                    continue
                target = link.split('#', 1)[0]
                if target:
                    self.assertTrue((path.parent / target).exists(), f'{path.name}: {link}')
