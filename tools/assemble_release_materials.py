"""Assemble a review-only source bundle; no media processing, deployment or publication."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from job_tracking import Job

MEDIA_SUFFIXES={'.mkv','.mp4','.avi','.mov','.hevc','.h264','.h265','.obu','.m2ts','.mts',
                '.vob','.mpg','.mpeg','.mp3','.wav','.aac','.dts','.flac','.ac3','.ogg','.yuv','.y4m'}


def code_only_archive(path,destination):
    """Omit recognized upstream media fixtures; preserve all remaining archive data."""
    path=Path(path)
    if not (path.name.endswith(('.tar.gz','.tar.xz','.tar.bz2','.crate'))):return path,0
    with tarfile.open(path) as original:
        members=original.getmembers()
        excluded=[m for m in members if not m.isdir() and PurePosixPath(m.name).suffix.lower() in MEDIA_SUFFIXES]
        if not excluded:return path,0
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
        mode='x:xz' if path.name.endswith('.tar.xz') else 'x:bz2' if path.name.endswith('.tar.bz2') else 'x:gz'
        with tarfile.open(destination,mode) as target:
            for member in members:
                if member not in excluded:
                    target.addfile(member,original.extractfile(member) if member.isfile() else None)
    return destination,len(excluded)


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def checked_file(root,name,expected):
    relative=PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe material filename')
    path=Path(root)/name
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError('Missing or linked material: '+name)
    if digest(path)!=expected:raise ValueError('Material checksum mismatch: '+name)
    return path


def descriptor_sources(folder,source,version):
    path=Path(folder)/f'{source}_{version.split(":",1)[-1]}.dsc'
    text=path.read_text()
    if f'\nSource: {source}\n' not in '\n'+text or f'\nVersion: {version}\n' not in '\n'+text:
        raise ValueError('Supplement descriptor identity mismatch')
    rows=[];reading=False
    for line in text.splitlines():
        if line=='Checksums-Sha256:':reading=True;continue
        if reading and not line.startswith(' '):break
        if reading:
            sha,size,name=line.split()
            if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('Invalid descriptor checksum')
            blob=checked_file(folder,name,sha)
            if blob.stat().st_size!=int(size):raise ValueError('Descriptor size mismatch')
            rows.append(dict(name=name,sha256=sha))
    if not rows:raise ValueError('Supplement has no source checksums')
    return rows


def assemble(remote,key,supplement,output,reports,collected_root=None,omit_media_fixtures=False):
    if collected_root is None and (not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+:/mnt/[A-Za-z0-9_./-]+',remote or '') or '..' in remote):
        raise ValueError('Use an explicit read-only source directory on the intended server')
    output,supplement=Path(output),Path(supplement)
    output.mkdir(parents=True,exist_ok=False)
    job=Job(reports,'Public source and license bundle assembly')
    try:
        job.save(phase='Copying collected source materials',detail='Read-only server copy; no Docker or media access')
        collected=Path(collected_root) if collected_root else output/'collected'
        if collected_root:
            if collected.is_symlink() or not collected.is_dir():raise ValueError('Unsafe cached collection directory')
        else:
            subprocess.run(['scp','-r','-i',str(key),'-o','BatchMode=yes','-o','ConnectTimeout=5',
                            remote,str(collected)],check=True,timeout=1200)
        job.save(phase='Verifying source archives and notice coverage')
        inventory=json.loads((collected/'source-inventory.json').read_text())
        for row in inventory['files']:checked_file(collected/'ubuntu-sources',row['path'],row['sha256'])
        for row in inventory['custom_downloads']:
            if not row['downloaded']:raise ValueError('An upstream source archive is missing')
            checked_file(collected/'custom-sources',row['name'],row['sha256'])
        supplements=[]
        for row in inventory['downloads']:
            if not row['downloaded']:
                supplements.append(dict(source=row['source'],version=row['version'],
                    files=descriptor_sources(supplement/'audit-supplement',row['source'],row['version']),
                    descriptor_signature_verified=False))
        for folder in ('pinned-inputs','wheel-sources','rust-sources','rpm-sources'):
            receipts=json.loads((supplement/folder/'download-receipts.json').read_text())
            for row in receipts:checked_file(supplement/folder,row['name'],row['sha256'])
        wheel_notices=supplement/'wheel-notices'
        if wheel_notices.exists():
            for row in json.loads((wheel_notices/'notice-index.json').read_text()):
                checked_file(wheel_notices,row['path'],row['sha256'])
        notices=json.loads((supplement/'rust-notices-r2/crate-license-inventory.json').read_text())
        recovered=json.loads((supplement/'recovered-notices-r2/notice-recovery.json').read_text())
        covered={r['archive'] for r in recovered if r['recovered']}
        gaps=[r['archive'] for r in notices if r['needs_notice_review'] and r['archive'] not in covered]
        if gaps:raise ValueError('Unresolved crate notice discovery gaps')
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        app_source=output/'app-source.tar'
        subprocess.run(['git','archive','--format=tar','-o',str(app_source),revision],cwd=ROOT,check=True)
        record=dict(schema=1,revision=revision,ubuntu_source_packages=len(inventory['downloads']),
                    recovered_ubuntu_sources=supplements,rust_crates=len(notices),notice_discovery_gaps=0,
                    redistribution_reviewed=False,privacy_reviewed=False,code_only_review=omit_media_fixtures,
                    limits=['Review license compatibility and archive privacy before public upload',
                            'Source descriptor signature for recovered Ubuntu supplement not independently verified',
                            'Source and notice coverage does not replace SBOM, vulnerability or installation checks',
                            *(['Filtered archives are not drop-in replacements for original checksum-pinned downloads; review build completeness before publication'] if omit_media_fixtures else [])])
        (output/'review-status.json').write_text(json.dumps(record,indent=2))
        job.save(phase='Packing source bundle',detail='Source archives are separate from the runtime image')
        bundle=output/'corresponding-source-review.tar'
        groups={'ubuntu-sources':collected/'ubuntu-sources','custom-sources':collected/'custom-sources',
                'ubuntu-notices':collected/'notices','python-notices':collected/'python-notices'}
        for name in ('audit-supplement','conda-materials','wheel-sources','rust-sources','rust-notices-r2',
                     'recovered-notices-r2','rpm-sources','wheel-match','pinned-inputs'):
            groups[name]=supplement/name
        if wheel_notices.exists():groups['wheel-notices']=wheel_notices
        catalog=[]
        transformations=[]
        with tarfile.open(bundle,'x') as archive:
            for label,folder in groups.items():
                for path in sorted(folder.rglob('*')):
                    if path.is_symlink():raise ValueError('Linked source material')
                    if not path.is_file() or '__pycache__' in path.parts or path.suffix in ('.pyc','.whl','.partial'):
                        continue
                    relative=label+'/'+path.relative_to(folder).as_posix()
                    public,excluded=code_only_archive(path,output/'code-only'/relative) if omit_media_fixtures else (path,0)
                    archive.add(public,arcname=relative,recursive=False)
                    catalog.append(dict(path=relative,sha256=digest(public),size=public.stat().st_size))
                    if excluded:transformations.append(dict(path=relative,original_sha256=digest(path),
                        public_sha256=digest(public),excluded_media_count=excluded,source_code_changed=False))
            for name in ('fel-dovi-submodule.tar.gz','felbaker-1.0.0.tar.gz','dovi-tool-2.3.3.tar.gz',
                         'hdr10plus-tool-1.7.2.tar.gz','pyav-19.0.0.tar.gz','pyav-ffmpeg-9.0.2-1.tar.gz',
                         'almalinux-8.9-repomd.xml','almalinux-8.9-source-primary.xml.gz'):
                path=supplement/name;relative='upstream/'+name
                public,excluded=code_only_archive(path,output/'code-only'/relative) if omit_media_fixtures else (path,0)
                archive.add(public,arcname=relative,recursive=False)
                catalog.append(dict(path=relative,sha256=digest(public),size=public.stat().st_size))
                if excluded:transformations.append(dict(path=relative,original_sha256=digest(path),
                    public_sha256=digest(public),excluded_media_count=excluded,source_code_changed=False))
            (output/'source-transformations.json').write_text(json.dumps(transformations,indent=2))
            archive.add(output/'source-transformations.json',arcname='source-transformations.json',recursive=False)
            for path in (app_source,output/'review-status.json'):
                archive.add(path,arcname=path.name,recursive=False)
        (output/'source-file-catalog.json').write_text(json.dumps(catalog,indent=2))
        result=dict(bundle=bundle.name,sha256=digest(bundle),size=bundle.stat().st_size,revision=revision,
                    reviewed=False,files=len(catalog))
        (output/'bundle-receipt.json').write_text(json.dumps(result,indent=2))
        job.save(state='completed',phase='Source bundle assembled for review',finished=time.time(),
                 detail='Checksums verified; no upload, publication, deployment or legal clearance claimed')
        return result
    except Exception as exc:
        job.save(state='failed',phase='Source bundle assembly failed',detail=str(exc),finished=time.time())
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remote')
    parser.add_argument('--ssh-key',type=Path)
    parser.add_argument('--collected',type=Path,help='Reuse verified collected sources instead of copying them again')
    parser.add_argument('--omit-media-fixtures',action='store_true',help='Create a code-only review draft; changed archives cannot satisfy original download hashes')
    parser.add_argument('--supplement',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reports',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(assemble(args.remote,args.ssh_key,args.supplement,args.output,args.reports,args.collected,args.omit_media_fixtures)))
