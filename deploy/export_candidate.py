"""Retain an exact Docker candidate for testing; never approve or publish it."""
import hashlib
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def export(image, destination, revision, version=None):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('An exact source revision is required')
    if version is not None and not re.fullmatch(r'\d{8}-v\d+',version):
        raise ValueError('Invalid application version')
    inspected = json.loads(subprocess.check_output(
        ['docker', 'image', 'inspect', image], text=True))[0]
    image_id = inspected['Id']
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('Invalid image identity')
    labels = inspected.get('Config', {}).get('Labels') or {}
    if labels.get('org.opencontainers.image.revision') != revision:
        raise ValueError('Image revision does not match the build')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    partial = destination / 'candidate-image.tar.partial'
    # Save by immutable ID, not a tag that could move between inspect and save.
    subprocess.run(['docker', 'image', 'save', '--output', str(partial), image_id], check=True)
    if not partial.is_file() or partial.stat().st_size == 0:
        raise ValueError('Docker produced no image archive')
    with partial.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive = destination / 'candidate-image.tar'
    partial.rename(archive)
    manifest = dict(schema=1, revision=revision, image_id=image_id,
                    archive=archive.name, sha256=digest, size_bytes=archive.stat().st_size,
                    qualification='pending', publication_approved=False)
    if version is not None:manifest['version']=version
    (destination / 'candidate.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (destination / 'SHA256SUMS').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    return manifest


if __name__ == '__main__':
    tree=ast.parse((Path(__file__).resolve().parents[1]/'python/app_version.py').read_text())
    versions=[ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets)]
    if len(versions)!=1:raise ValueError('Exactly one application version required')
    print(json.dumps(export(sys.argv[1], sys.argv[2], os.environ['GITHUB_SHA'],versions[0]), indent=2))
