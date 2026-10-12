"""Compare wheel ELF code with pinned distribution RPMs as data, never execution."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from inspect_wheel_materials import elf_text_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from job_tracking import Job

BASE = 'https://repo.almalinux.org/vault/8.9/AppStream/x86_64/os/'
NS = {'r':'http://linux.duke.edu/metadata/repo',
      'c':'http://linux.duke.edu/metadata/common', 'p':'http://linux.duke.edu/metadata/rpm'}
VERSIONS = {'libXau': ('1.0.9', '3.el8'), 'libdrm': ('2.4.115', '2.el8'),
            'libxcb': ('1.13.1', '1.el8')}


def download(relative, output, expected=None):
    url = urllib.parse.urljoin(BASE, relative)
    if not url.startswith(BASE):
        raise ValueError('Unexpected repository URL')
    with urllib.request.urlopen(url, timeout=45) as response:
        if urllib.parse.urlsplit(response.url).scheme != 'https':
            raise ValueError('Insecure repository redirect')
        data = response.read(64*1024**2+1)
    if len(data)>64*1024**2:
        raise ValueError('Oversized repository download')
    digest = hashlib.sha256(data).hexdigest()
    if expected and digest != expected:
        raise ValueError('Repository checksum mismatch')
    Path(output).write_bytes(data)
    return data, digest


def compare(report_path, destination, reports):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    job = Job(reports, 'Wheel system-library source verification')
    try:
        job.save(phase='Reading official package metadata')
        data, _ = download('repodata/repomd.xml', destination/'repomd.xml')
        primary = ET.fromstring(data).find("r:data[@type='primary']", NS)
        checksum = primary.find('r:checksum', NS)
        if checksum.attrib['type'] != 'sha256':
            raise ValueError('Expected SHA256 repository metadata')
        data, _ = download(primary.find('r:location', NS).attrib['href'],
                           destination/'primary.xml.gz', checksum.text)
        packages = {}
        for package in ET.fromstring(gzip.decompress(data)).findall('c:package', NS):
            name = package.findtext('c:name', namespaces=NS)
            if name not in VERSIONS or package.findtext('c:arch', namespaces=NS) != 'x86_64':
                continue
            version = package.find('c:version', NS).attrib
            if (version['ver'], version['rel']) != VERSIONS[name]:
                continue
            checksum = package.find('c:checksum', NS)
            if checksum.attrib['type'] != 'sha256': raise ValueError('Expected RPM SHA256')
            packages[name] = dict(location=package.find('c:location', NS).attrib['href'],
                                  sha256=checksum.text,
                                  source=package.findtext('c:format/p:sourcerpm', namespaces=NS))
        if set(packages) != set(VERSIONS): raise ValueError('Expected RPM versions missing')
        wheel = json.loads(Path(report_path).read_text())
        missing = {r['upstream_name']: r for r in wheel['bundled_libraries'] if r['upstream_text_match'] is None}
        matches = []
        for index, (name, package) in enumerate(sorted(packages.items())):
            job.save(phase='Comparing packaged library code', completed=index, total=3, unit='RPMs')
            expected_source = name+'-'+ '-'.join(VERSIONS[name])+'.src.rpm'
            if package['source'] != expected_source: raise ValueError('RPM source identity differs')
            path = destination/Path(package['location']).name
            download(package['location'], path, package['sha256'])
            # bsdtar reads the RPM/CPIO payload; no extracted code is loaded.
            members = subprocess.check_output(['tar','-tf',str(path)], text=True).splitlines()
            for member in members:
                leaf = Path(member).name
                if leaf not in missing: continue
                data = subprocess.check_output(['tar','-xOf',str(path),member])
                actual = elf_text_hash(data)
                matches.append(dict(library=leaf, package=name, source=package['source'],
                                    text_sha256=actual, matches=actual==missing[leaf]['text_sha256']))
        passed = (len(matches)==len(missing) and {r['library'] for r in matches}==set(missing)
                  and all(row['matches'] for row in matches))
        result = dict(schema=1, passed=passed, wheel_sha256=wheel['wheel_sha256'],
                      packages=packages, libraries=matches,
                      limits=['ELF text-section comparison, not whole-file reproducible-build proof',
                              'HTTPS repository metadata hashes verified; RPM signatures not independently verified'])
        (destination/'verification.json').write_text(json.dumps(result, indent=2))
        if not passed: raise ValueError('A wheel library did not match the expected distribution code')
        job.save(state='completed', phase='System-library code and source mapping verified',
                 finished=time.time(), detail=f'{len(matches)} library code sections matched; no native execution')
        return result
    except Exception as exc:
        job.save(state='failed', phase='System-library verification failed', finished=time.time(), detail=str(exc))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel-report', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.wheel_report, args.destination, args.reports)
    print(json.dumps(dict(passed=result['passed'], libraries=len(result['libraries']))))
