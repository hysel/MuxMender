from pathlib import Path
import unittest


class SecurityScan(unittest.TestCase):
    def test_scanner_has_no_host_socket_gpu_or_media_access(self):
        text=(Path(__file__).resolve().parents[1]/'deploy/truenas/scan-public-candidate.sh').read_text()
        for value in ('docker.sock','--gpus','dst=/media','dst=/output','--privileged','docker start','docker stop'):
            self.assertNotIn(value,text)
        self.assertIn('--read-only',text)
        self.assertIn('--memory 4g',text)
        self.assertIn('--input /scan-input/image.tar',text)
        self.assertIn('--scanners vuln --format cyclonedx',text)
        self.assertIn('sha256sum -c',text)
