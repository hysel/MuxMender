from pathlib import Path
import unittest


class SecurityScan(unittest.TestCase):
    def test_build_installers_are_not_copied_into_runtime_layers(self):
        text=(Path(__file__).resolve().parents[1]/'deploy/truenas/Dockerfile.public').read_text()
        runtime=text.rsplit('\nFROM ',1)[1]
        self.assertNotIn('python3-pip',runtime)
        self.assertNotIn('python3 -m pip',runtime)
        self.assertIn('COPY --from=python-runtime-build /opt/muxmender-runtime/',runtime)
        self.assertIn('--require-hashes',text)
    def test_scanner_has_no_host_socket_gpu_or_media_access(self):
        text=(Path(__file__).resolve().parents[1]/'deploy/truenas/scan-public-candidate.sh').read_text()
        for value in ('docker.sock','--gpus','dst=/media','dst=/output','--privileged','docker start','docker stop'):
            self.assertNotIn(value,text)
        self.assertIn('--read-only',text)
        self.assertIn('--memory 4g',text)
        self.assertIn('--input /scan-input/image.tar',text)
        self.assertIn('--scanners vuln --format cyclonedx',text)
        self.assertIn('sha256sum -c',text)
