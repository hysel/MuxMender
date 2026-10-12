import hashlib
import json
from pathlib import Path
import unittest
from tools.promote_stable_image import verify


class StablePromotionTests(unittest.TestCase):
    def test_only_exact_reviewed_image_is_accepted(self):
        data=json.dumps(dict(mediaType='application/vnd.oci.image.manifest.v1+json',config=dict(digest='sha256:'+'a'*64))).encode()
        digest='sha256:'+hashlib.sha256(data).hexdigest()
        review=dict(version='20261012-v61',repository='ghcr.io/example/app',privacy_reviewed=True,redistribution_reviewed=True,qualified_image_id='sha256:'+'a'*64)
        self.assertIn('manifest',verify(data,digest,review,'20261012-v61','example/app'))
        for key,value in (('version','20261010-v60'),('qualified_image_id','sha256:'+'b'*64),('privacy_reviewed',False),('redistribution_reviewed',False),('repository','ghcr.io/other/app')):
            with self.assertRaises(ValueError):verify(data,digest,{**review,key:value},'20261012-v61','example/app')
        with self.assertRaises(ValueError):verify(data+b' ',digest,review,'20261012-v61','example/app')

    def test_approval_and_alias_only_no_docker_access(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/'.github/workflows/promote-stable-image.yml').read_text()
        script=(root/'tools/promote_stable_image.py').read_text()
        for text in ('environment: container-release','group: container-release','persist-credentials: false'):
            self.assertIn(text,workflow)
        self.assertIn("endpoint+'stable',data=data",script)
        self.assertNotIn('docker ',workflow+script)
        self.assertNotIn('self-hosted',workflow)
