"""Static packaging checks; live orphan/signal behavior requires Linux Docker."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ContainerReaperContractTests(unittest.TestCase):
    def test_entrypoints_include_installed_reaper(self):
        for name, module in [('Dockerfile', 'auto_optimize'),
                             ('Dockerfile.app', 'app_service'),
                             ('Dockerfile.full-research', 'full_research_app')]:
            with self.subTest(name=name):
                text = (ROOT / 'deploy/truenas' / name).read_text()
                self.assertIn('install -y --no-install-recommends', text)
                self.assertIn('tini && apt-get clean', text)
                self.assertIn(f'ENTRYPOINT ["/usr/bin/tini", "--", "python3", "-B", "-m", "{module}"]', text)

    def test_legacy_detached_research_uses_runtime_init(self):
        for folder in ('hdr10', 'hdr10plus'):
            with self.subTest(folder=folder):
                text = (ROOT / 'deploy' / folder / 'run.sh').read_text()
                self.assertIn('docker run -d --init ', text)


if __name__ == '__main__':
    unittest.main()
