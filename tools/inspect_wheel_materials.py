"""Inventory a pinned PyAV wheel and upstream source recipes without executing them."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
import tarfile
import urllib.parse
import zipfile


def package_pins(text):
    """Read only literal Package fields; never import or evaluate upstream code."""
    result = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'Package':
            continue
        fields = {k.arg: k.value.value for k in node.keywords
                  if isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)}
        if not {'name', 'source_url', 'sha256'}.issubset(fields):
            raise ValueError('Non-literal source recipe requires review')
        original = fields['source_url']
        url = 'https://' + original[7:] if original.startswith('http://deb.debian.org/') else original
        name = fields.get('source_filename') or Path(urllib.parse.urlsplit(url).path).name
        result.append(dict(package=fields['name'], url=url, original_url=original,
                           name=name, sha256=fields['sha256']))
    return result


def elf_text_hash(data):
    """Hash ELF64 machine code as data, without loading the library."""
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Expected little-endian ELF64')
    offset = struct.unpack_from('<Q', data, 40)[0]
    width, count, names = struct.unpack_from('<HHH', data, 58)
    if width != 64 or not 0 < count <= 20000 or names >= count or offset + width*count > len(data):
        raise ValueError('Invalid ELF section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset+i*width) for i in range(count)]
    name_offset, name_size = sections[names][4:6]
    if name_offset + name_size > len(data):
        raise ValueError('Invalid ELF section names')
    strings = data[name_offset:name_offset+name_size]
    for section in sections:
        start = section[0]
        if start >= len(strings):
            continue
        end = strings.find(b'\0', start)
        if end < 0:
            continue
        name = strings[start:end]
        if name == b'.text':
            begin, size = section[4:6]
            if not size or begin + size > len(data):
                raise ValueError('Invalid ELF text section')
            return hashlib.sha256(data[begin:begin+size]).hexdigest()
    raise ValueError('ELF text section missing')


def inspect(wheel, expected_hash, build_sources, destination, upstream_runtime=None):
    wheel = Path(wheel)
    with wheel.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != expected_hash:
        raise ValueError('Wheel checksum mismatch')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    libraries, configurations, sbom = [], [], None
    upstream = {}
    if upstream_runtime:
        with tarfile.open(upstream_runtime) as archive:
            for member in archive.getmembers():
                if member.isfile() and member.name.startswith('lib/') and '.so' in member.name:
                    if member.size > 128 * 1024**2:
                        raise ValueError('Oversized upstream library')
                    upstream[Path(member.name).name] = elf_text_hash(archive.extractfile(member).read())
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            if member.file_size > 128 * 1024**2:
                raise ValueError('Oversized wheel member')
            if member.filename.startswith('av.libs/') and not member.is_dir():
                data = archive.read(member)
                name = re.sub(r'-[0-9a-f]{8}(?=\.so)', '', Path(member.filename).name)
                text_hash = elf_text_hash(data)
                libraries.append(dict(name=member.filename, sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                                      text_sha256=text_hash, upstream_name=name,
                                      upstream_text_match=text_hash == upstream[name] if name in upstream else None))
                if '/libav' in member.filename:
                    configurations.extend(s.decode('ascii') for s in re.findall(rb'[ -~]{30,}', data)
                                          if b'--enable-' in s or b'--disable-' in s)
            if member.filename.endswith('/sboms/auditwheel.cdx.json'):
                sbom = json.loads(archive.read(member))
    if not libraries or not configurations:
        raise ValueError('Expected bundled library/configuration evidence is missing')
    with tarfile.open(build_sources) as archive:
        members = [m for m in archive.getmembers() if m.isfile() and m.name.endswith('/scripts/pkg.py')]
        if len(members) != 1 or members[0].size > 1024**2:
            raise ValueError('Missing or oversized package recipe')
        pins = package_pins(archive.extractfile(members[0]).read().decode())
    report = dict(wheel_sha256=digest, bundled_libraries=libraries,
                  embedded_configurations=sorted(set(configurations)), auditwheel_sbom=sbom,
                  source_recipe_sha256=hashlib.sha256(Path(build_sources).read_bytes()).hexdigest(),
                  source_pins=pins, redistribution_reviewed=False,
                  limits=['Upstream build tag association needs verification against wheel build records',
                          'Bundled system RPM libraries need matching source and notices',
                          'Encoder licenses must be reviewed independently of configure flags'])
    (destination / 'wheel-materials.json').write_text(json.dumps(report, indent=2))
    (destination / 'source-pins.json').write_text(json.dumps(pins, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--build-sources', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--upstream-runtime', type=Path, help='Compare code sections with the pinned upstream build')
    args = parser.parse_args()
    result = inspect(args.wheel, args.sha256, args.build_sources, args.destination, args.upstream_runtime)
    print(json.dumps(dict(libraries=len(result['bundled_libraries']), source_pins=len(result['source_pins']),
                          redistribution_reviewed=False)))
