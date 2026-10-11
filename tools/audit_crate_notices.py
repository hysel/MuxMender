"""Retain Cargo license metadata and notices from checksum-verified source archives."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tomllib


def licensing_header(data):
    """Retain existing introductory source notices, never synthesize a license."""
    lines=[];block=False
    for line in data.decode('utf-8',errors='replace').splitlines():
        stripped=line.strip()
        if stripped.startswith('/*'):block=True
        if block or stripped.startswith('//') or not stripped:
            lines.append(line)
            if '*/' in stripped:block=False
        else:break
    header='\n'.join(lines).strip()
    if any(token in header.lower() for token in ('licensed under','license, v.','spdx-license-identifier')):
        return (header+'\n').encode()
    return None


def inspect(archives, destination):
    archives, destination=Path(archives),Path(destination)
    receipts=json.loads((archives/'download-receipts.json').read_text())
    destination.mkdir(parents=True,exist_ok=False)
    rows=[]
    for receipt in receipts:
        source=archives/receipt['name']
        if source.is_symlink() or source.name!=receipt['name'] or not source.is_file():
            raise ValueError('Unsafe crate path')
        with source.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=receipt['sha256']:
                raise ValueError('Crate checksum mismatch')
        with tarfile.open(source) as archive:
            members=archive.getmembers()
            manifests=[m for m in members if m.isfile() and len(PurePosixPath(m.name).parts)==2
                       and m.name.endswith('/Cargo.toml')]
            if len(manifests)!=1 or manifests[0].size>1024**2:
                raise ValueError('Expected one bounded crate manifest')
            package=tomllib.loads(archive.extractfile(manifests[0]).read().decode())['package']
            prefix=PurePosixPath(manifests[0].name).parts[0]
            license_file=package.get('license-file')
            notices=[]
            for member in members:
                name=PurePosixPath(member.name)
                if (name.is_absolute() or '..' in name.parts or '\\' in member.name or ':' in member.name):
                    raise ValueError('Unsafe crate notice path')
                selected=(any(token in name.name.upper() for token in ('LICENSE','COPYING','NOTICE','AUTHORS'))
                          or any(part.upper()=='LICENSES' for part in name.parts)
                          or license_file and member.name==prefix+'/'+license_file)
                if member.isfile() and selected:
                    if member.size>4*1024**2:raise ValueError('Oversized crate notice')
                    target=destination/source.stem/name
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
                    notices.append(member.name)
                elif member.isfile() and member.name.endswith('.rs') and member.size<=4*1024**2:
                    header=licensing_header(archive.extractfile(member).read())
                    if header:
                        target=destination/source.stem/(member.name+'.notice.txt')
                        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(header)
                        notices.append(member.name+' (existing source header)')
            rows.append(dict(archive=source.name,package=package['name'],version=package['version'],
                             declared_license=package.get('license'),license_file=license_file,
                             notices=notices,needs_notice_review=not bool(notices),
                             redistribution_reviewed=False))
    (destination/'crate-license-inventory.json').write_text(json.dumps(rows,indent=2))
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    rows=inspect(args.archives,args.destination)
    print(json.dumps(dict(crates=len(rows),missing_notice_files=sum(r['needs_notice_review'] for r in rows),
                          redistribution_reviewed=False)))
