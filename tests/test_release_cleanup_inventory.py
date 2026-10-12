from pathlib import Path
import unittest


class ReleaseCleanupInventory(unittest.TestCase):
    def test_inventory_is_read_only_and_never_sweeps_production(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'deploy/truenas/inventory-release-storage.sh').read_text()
        for command in ('docker rm ','docker rmi ','docker image rm','docker system prune',
                        'docker volume prune','rm -rf','docker stop','docker start'):
            self.assertNotIn(command,text)
        self.assertIn('docker ps -a',text)
        self.assertIn('docker inspect --format',text)
        self.assertNotIn('"$base"/output',text)
        self.assertNotIn('/media',text)
        self.assertIn('No cleanup performed',text)
