"""Recover upstream notices at crate-recorded revisions using read-only GitHub calls."""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.parse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from job_tracking import Job


def github_repository(url):
    parsed=urllib.parse.urlsplit(url or '')
    parts=parsed.path.strip('/').split('/')
    if parsed.scheme!='https' or parsed.hostname!='github.com' or len(parts)<2:
        raise ValueError('Notice recovery needs a GitHub repository')
    owner,repo=parts[:2];repo=repo.removesuffix('.git')
    if any(not re.fullmatch('[A-Za-z0-9_.-]+',p) or p in ('.','..') for p in (owner,repo)):
        raise ValueError('Unsafe repository name')
    return owner+'/'+repo


def selected_notice(path, crate_path=''):
    path=PurePosixPath(path)
    crate=PurePosixPath(crate_path)
    if path.is_absolute() or '..' in path.parts or '..' in crate.parts or '\\' in str(path):
        raise ValueError('Unsafe notice path')
    parents={PurePosixPath('.'),crate,*crate.parents}
    return (path.parent in parents and any(t in path.name.upper() for t in ('LICENSE','COPYING','NOTICE','COPYRIGHT','AUTHORS'))
            or path.parent.name.upper()=='LICENSES' and path.parent.parent in parents)


def api(endpoint):
    return json.loads(subprocess.check_output(['gh','api',endpoint],text=True,timeout=60))


def recover(sources,inventory,manual_revisions,destination,reports):
    sources,destination=Path(sources),Path(destination)
    rows=json.loads(Path(inventory).read_text())
    receipts={r['name']:r for r in json.loads((sources/'download-receipts.json').read_text())}
    manual=json.loads(Path(manual_revisions).read_text()) if manual_revisions else {}
    missing=[r for r in rows if r['needs_notice_review']]
    destination.mkdir(parents=True,exist_ok=False)
    job=Job(reports,'Pinned dependency notice recovery')
    result=[];trees={}
    try:
        for index,row in enumerate(missing):
            name=row['archive']
            job.save(phase='Recovering dependency license notices',progress_kind='structured',
                     completed=index,total=len(missing),unit='packages',detail=name)
            try:
                path=sources/name
                if path.name!=name or path.is_symlink():raise ValueError('Unsafe archive path')
                with path.open('rb') as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=receipts[name]['sha256']:
                        raise ValueError('Crate checksum mismatch')
                with tarfile.open(path) as archive:
                    members=archive.getmembers()
                    cargo=next(m for m in members if m.isfile() and len(PurePosixPath(m.name).parts)==2 and m.name.endswith('/Cargo.toml'))
                    package=tomllib.loads(archive.extractfile(cargo).read().decode())['package']
                    vcs=next((m for m in members if m.isfile() and m.name.endswith('/.cargo_vcs_info.json')),None)
                    vcs=json.loads(archive.extractfile(vcs).read()) if vcs else {}
                repository=github_repository(package.get('repository'))
                revision=vcs.get('git',{}).get('sha1') or manual.get(name)
                if not isinstance(revision,str) or not re.fullmatch('[0-9a-f]{40}',revision):
                    raise ValueError('A matching source revision is required')
                key=(repository,revision)
                if key not in trees:trees[key]=api(f'repos/{repository}/git/trees/{revision}?recursive=1')
                tree=trees[key]
                if tree.get('truncated'):raise ValueError('Upstream tree is truncated')
                notices=[]
                for item in tree['tree']:
                    if item.get('type')!='blob' or item.get('mode')=='120000' or not selected_notice(item['path'],vcs.get('path_in_vcs','')):
                        continue
                    content=api(f'repos/{repository}/git/blobs/{item["sha"]}')
                    if content.get('encoding')!='base64' or content.get('size',0)>4*1024**2:
                        raise ValueError('Unexpected notice content')
                    data=base64.b64decode(content['content'])
                    target=destination/Path(name).stem/item['path']
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                    notices.append(dict(path=item['path'],sha256=hashlib.sha256(data).hexdigest(),
                                        source=f'https://github.com/{repository}/blob/{revision}/{item["path"]}'))
                if not notices:raise ValueError('No matching upstream notice files found')
                result.append(dict(archive=name,repository=repository,revision=revision,notices=notices,
                                   recovered=True,manual_revision=name in manual,redistribution_reviewed=False))
            except (OSError,ValueError,KeyError,StopIteration,subprocess.SubprocessError) as exc:
                result.append(dict(archive=name,recovered=False,error=str(exc)))
            (destination/'notice-recovery.json').write_text(json.dumps(result,indent=2))
        failures=sum(not r['recovered'] for r in result)
        job.save(state='failed' if failures else 'completed',phase='Dependency notice recovery finished',
                 completed=len(result),total=len(missing),unit='packages',finished=time.time(),
                 detail=f'{len(result)-failures} recovered; {failures} unresolved. Redistribution review is separate.')
        return result
    except Exception as exc:
        job.save(state='failed',phase='Notice recovery failed',detail=str(exc),finished=time.time())
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--manual-revisions',type=Path)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--reports',type=Path,required=True)
    args=parser.parse_args()
    rows=recover(args.sources,args.inventory,args.manual_revisions,args.destination,args.reports)
    print(json.dumps(dict(recovered=sum(r['recovered'] for r in rows),total=len(rows))))
