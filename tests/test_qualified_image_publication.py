from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QualifiedPublication(unittest.TestCase):
    def test_draft_access_is_scoped_to_approved_job(self):
        text=(ROOT/'.github/workflows/publish-qualified-image.yml').read_text()
        defaults, job=text.split('jobs:',1)
        self.assertIn('contents: read',defaults)
        self.assertNotIn('contents: write',defaults)
        self.assertIn('contents: write',job)
        self.assertIn('environment: container-release',job)
        self.assertIn('persist-credentials: false',job)
        self.assertNotIn('gh release edit',job)

    def test_hosted_workflow_does_not_build_or_run_media(self):
        text=(ROOT/'.github/workflows/publish-qualified-image.yml').read_text()
        self.assertIn('runs-on: ubuntu-24.04',text)
        self.assertIn('environment: container-release',text)
        self.assertIn('packages: write',text)
        self.assertIn('GH_TOKEN: ${{ github.token }}',text)
        self.assertIn('docker load --input',text)
        self.assertIn("from audit_public_release import audit,extract_context",text)
        for value in ('docker build', 'docker run', '--gpus', 'self-hosted', 'secrets.GH_PAT'):
            self.assertNotIn(value,text)
        self.assertIn("==os.environ[key]",text)
        self.assertIn('Tag exists; refusing overwrite.',text)

    def test_export_fixed_image_no_registry_or_production(self):
        text=(ROOT/'deploy/truenas/export-qualified-public-image.sh').read_text()
        self.assertIn('image=sha256:20bceb9acd80f3bcf9e6a81312f4eede6d576b06fab978ab48e5da48f10c8c04',text)
        self.assertIn('docker image save',text)
        self.assertIn('sha256sum',text)
        self.assertIn('systemd-run',text)
        for value in ('docker login','docker push','docker build','docker stop','docker start','docker rm','prune'):
            self.assertNotIn(value,text)

    def test_export_observer_is_read_only(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools'))
        from monitor_release_stage import read_command
        command=read_command('20261010-v60',public_export=True)
        self.assertIn('public-image-export-20261012-r1',command)
        self.assertNotIn('docker ',command)
        with self.assertRaises(ValueError):read_command('20261010-v60',public_export=True,public_scan=True)
