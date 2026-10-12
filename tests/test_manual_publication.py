from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile
import unittest


class ManualPublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (Path(__file__).resolve().parents[1] / 'deploy/truenas/publish-reviewed-image.sh').read_text()

    def test_uses_shared_audit_and_exact_image(self):
        self.assertIn('from audit_public_release import audit', self.script)
        self.assertIn("manifest.get('qualified_image_id') != sys.argv[3]", self.script)
        self.assertIn('files(expected) != files(actual)', self.script)

    def test_dry_run_precedes_credentials_and_upload(self):
        self.assertLess(self.script.index('if [[ "$publish" != true ]]'), self.script.index('read -r -s'))
        self.assertIn('--password-stdin', self.script)
        self.assertIn('export DOCKER_CONFIG="$temporary/auth"', self.script)
        self.assertIn('unset registry_token', self.script)

    def test_no_build_deploy_or_prune(self):
        for forbidden in ('docker build ', 'docker restart ', 'docker stop ', 'docker system prune', 'docker volume ', '--privileged', '/var/run/docker.sock'):
            self.assertNotIn(forbidden, self.script)
        self.assertIn('That release tag exists. It will not be overwritten.', self.script)
        self.assertIn('manifest unknown|manifest_unknown', self.script)
        self.assertIn('Research-only image cannot be published', self.script)


@unittest.skipUnless(os.name == 'posix', 'Shell integration runs on Linux only')
class ManualPublicationShell(unittest.TestCase):
    def test_local_preflight_and_rejections_without_registry_access(self):
        root = Path(__file__).resolve().parents[1]
        # TrueNAS mounts /tmp noexec; keep only the fake executable in this
        # explicitly staged test workspace, never fall through to real Docker.
        with tempfile.TemporaryDirectory(prefix='publication-test-', dir=root) as directory:
            work = Path(directory)
            context = work/'context'
            materials = context/'public-materials'
            materials.mkdir(parents=True)
            (materials/'notice').write_text('fixture notice')
            sha = hashlib.sha256(b'fixture notice').hexdigest()
            image = 'sha256:' + 'a'*64
            manifest = dict(schema=1, version='20261010-v60', revision='b'*40,
                            redistribution_reviewed=True, privacy_reviewed=True,
                            qualified_image_id=image, repository='ghcr.io/hysel/muxmender',
                            materials=[dict(role=role, path='public-materials/notice', sha256=sha)
                                for role in ('app-license','third-party-notices','corresponding-source','build-instructions')])
            manifest_path = context/'public-release.json'
            manifest_path.write_text(json.dumps(manifest))
            binaries = work/'bin'
            binaries.mkdir()
            docker = binaries/'docker'
            docker.write_text('''#!/usr/bin/env python3
import os, pathlib, shutil, sys
args=sys.argv[1:]
with open(os.environ['CALL_LOG'],'a') as log: log.write(' '.join(args)+'\\n')
if args[:2]==['image','inspect']: print('sha256:'+'a'*64)
elif args[0]=='create': print('fixture-container')
elif args[0]=='cp':
    target=pathlib.Path(args[2])
    if args[1].endswith('/public-materials'): shutil.copytree(os.environ['MATERIALS'],target)
    else: target.write_text("VERSION = '20261010-v60'\\n")
elif args[0]=='rm': pass
else: raise SystemExit('Unexpected Docker call: '+str(args))
''')
            docker.chmod(0o755)
            if subprocess.run([str(docker)], env=dict(os.environ, CALL_LOG=str(work/'probe')), capture_output=True).returncode == 0:
                self.fail('Mock unexpectedly accepted an empty invocation')
            log = work/'calls'
            env = dict(os.environ, PATH=str(binaries)+os.pathsep+os.environ['PATH'],
                       CALL_LOG=str(log), MATERIALS=str(materials))
            command = ['bash',str(root/'deploy/truenas/publish-reviewed-image.sh'),
                       '--context',str(context),'--image',image]
            result = subprocess.run(command, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Nothing uploaded', result.stdout)
            self.assertNotIn('login', log.read_text())
            self.assertNotIn('push', log.read_text())
            manifest['qualified_image_id'] = 'sha256:'+'c'*64
            manifest_path.write_text(json.dumps(manifest))
            result = subprocess.run(command, env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('exact qualified image', result.stderr)
            manifest['qualified_image_id'] = image
            manifest_path.write_text(json.dumps(manifest))
            (materials/'REVIEW-PENDING.md').write_text('not approved')
            result = subprocess.run(command, env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Research-only image', result.stderr)
