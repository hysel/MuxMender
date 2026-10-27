"""Check the user-facing GitHub changelog before publishing or promoting an image."""
import json
import os
import re
import urllib.request


def validate(release, version, *, published):
    if release.get('tag_name') != version:
        raise ValueError('Release notes must match the image version')
    if not isinstance(release.get('body'), str) or not release['body'].strip():
        raise ValueError('Write release notes describing changes and required user actions before publication')
    if published and (release.get('draft') is not False or release.get('prerelease') is not False):
        raise ValueError('Publish the final release notes before promoting stable')
    return release


def check(*, published=True):
    repository = os.environ['GITHUB_REPOSITORY']
    version = os.environ['VERSION']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid repository')
    if not re.fullmatch(r'\d{8}-v\d+', version):
        raise ValueError('Invalid release version')
    request = urllib.request.Request(
        f'https://api.github.com/repos/{repository}/releases/tags/{version}',
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return validate(json.load(response), version, published=published)


if __name__ == '__main__':
    import sys
    check(published='--allow-draft' not in sys.argv)
    print('Release notes match the image version')
