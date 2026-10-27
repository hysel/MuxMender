"""Point stable at a reviewed, already-published manifest without rebuilding."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
from release_notes import check as check_release_notes

ACCEPT='application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'


def verify(data, digest, review, version, repository):
    if not re.fullmatch(r'\d{8}-v\d+',version) or not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):
        raise ValueError('Exact version and digest required')
    if 'sha256:'+hashlib.sha256(data).hexdigest()!=digest:
        raise ValueError('Registry manifest digest differs')
    manifest=json.loads(data)
    if (review.get('version')!=version or review.get('repository')!='ghcr.io/'+repository or
        review.get('privacy_reviewed') is not True or review.get('redistribution_reviewed') is not True or
        manifest.get('config',{}).get('digest')!=review.get('qualified_image_id')):
        raise ValueError('Published image does not match reviewed qualification')
    if manifest.get('mediaType') not in ACCEPT.split(', '):
        raise ValueError('Expected a qualified single-platform image manifest')
    return manifest['mediaType']


def main():
    repository=os.environ['GITHUB_REPOSITORY'].lower()
    if os.environ['GITHUB_REF']!='refs/heads/main':raise ValueError('Promotion requires main')
    if not re.fullmatch(r'[a-z0-9_.-]+/[a-z0-9_.-]+',repository):raise ValueError('Invalid repository')
    version=os.environ['VERSION'];digest=os.environ.get('MANIFEST_DIGEST')
    if not digest and os.environ.get('RESOLVE_PUBLISHED_DIGEST')!='1':
        raise ValueError('Manifest digest required unless resolving the reviewed published image')
    raw=Path(os.environ['REVIEW_PATH']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=os.environ['REVIEW_SHA']:raise ValueError('Review checksum differs')
    review=json.loads(raw)
    check_release_notes()
    auth=base64.b64encode((os.environ['GITHUB_ACTOR']+':'+os.environ['GH_TOKEN']).encode()).decode()
    token_url='https://ghcr.io/token?'+urllib.parse.urlencode(dict(service='ghcr.io',scope='repository:'+repository+':pull,push'))
    with urllib.request.urlopen(urllib.request.Request(token_url,headers={'Authorization':'Basic '+auth}),timeout=30) as response:
        token=json.load(response)['token']
    headers={'Authorization':'Bearer '+token,'Accept':ACCEPT}
    endpoint='https://ghcr.io/v2/'+repository+'/manifests/'
    # Validate inputs before interpolating a release identifier into a URL.
    if not re.fullmatch(r'\d{8}-v\d+',version):raise ValueError('Invalid version')
    with urllib.request.urlopen(urllib.request.Request(endpoint+version,headers=headers),timeout=30) as response:
        data=response.read()
    if not digest:
        digest='sha256:'+hashlib.sha256(data).hexdigest()
    content_type=verify(data,digest,review,version,repository)
    if os.environ.get('REQUIRE_ANONYMOUS_PULL')=='1':
        anonymous_url='https://ghcr.io/token?'+urllib.parse.urlencode(dict(service='ghcr.io',scope='repository:'+repository+':pull'))
        with urllib.request.urlopen(anonymous_url,timeout=30) as response:
            anonymous_token=json.load(response)['token']
        anonymous_headers={'Authorization':'Bearer '+anonymous_token,'Accept':ACCEPT}
        with urllib.request.urlopen(urllib.request.Request(endpoint+version,headers=anonymous_headers),timeout=30) as response:
            verify(response.read(),digest,review,version,repository)
    # PUT only the stable alias, never the immutable version tag or image layers.
    with urllib.request.urlopen(urllib.request.Request(endpoint+'stable',data=data,
            headers={**headers,'Content-Type':content_type},method='PUT'),timeout=30) as response:
        if response.status!=201:raise ValueError('Registry did not confirm promotion')
    with urllib.request.urlopen(urllib.request.Request(endpoint+'stable',headers=headers),timeout=30) as response:
        published=response.read()
    verify(published,digest,review,version,repository)
    result=dict(version=version,stable_digest=digest,qualified_image_id=review['qualified_image_id'],deployed=False)
    Path('stable-promotion.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
