"""Build a version-independent compatibility package; never builds app images."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]


def regression_index(root,ledger):
    mapping={}
    for fix in ledger['fixes']:
        for pattern in fix['tests']:mapping.setdefault(pattern,[]).append(fix['id'])
    entries=[]
    for path in sorted((root/'tests').glob('test_*.py')):
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        methods=[]
        for node in tree.body:
            if isinstance(node,ast.ClassDef):
                methods.extend(node.name+'.'+m.name for m in node.body
                               if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and m.name.startswith('test'))
            elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test'):
                methods.append(node.name)
        entries.append({'module':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'tests':methods,'fix_ids':mapping.get(path.name,[]),
                        'coverage':'ledger-linked' if path.name in mapping else 'additional regression; not an upstream retirement test'})
    return entries


def build(destination,root=ROOT):
    from ffmpeg_compatibility_suite import load_ledger
    ledger=load_ledger(root/'docs/fix-ledger.json')
    destination.mkdir(parents=True,exist_ok=False)
    files={}
    for folder in ('python','tests','tools','deploy','docs'):
        for path in (root/folder).rglob('*'):
            if path.is_symlink():raise ValueError('Linked package source')
            if path.is_file() and (path.suffix in ('.py','.js','.json','.sh','.yaml','.yml','.md') or path.name.startswith('Dockerfile')) and '__pycache__' not in path.parts:
                files[path.relative_to(root).as_posix()]=path.read_bytes()
    for name in ('README.md','pyproject.toml','AGENTS.md'):
        files[name]=(root/name).read_bytes()
    for name in ('docs/fix-ledger.json','docs/ffmpeg-compatibility.md'):
        files[name]=(root/name).read_bytes()
    index=regression_index(root,ledger)
    files['regression-index.json']=json.dumps(index,indent=2).encode()
    inventory={'schema':1,'fix_families':len(ledger['fixes']),'regression_modules':len(index),
               'test_methods':sum(len(e['tests']) for e in index),
               'ledger_linked_modules':sum(bool(e['fix_ids']) for e in index),
               'runtime_bundled':False,'production_modified':False,
               'files':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}}
    files['package-manifest.json']=json.dumps(inventory,indent=2).encode()
    archive=destination/'ffmpeg-compatibility-tests.tar'
    with tarfile.open(archive,'x') as target:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.uid=info.gid=0
            target.addfile(info,io.BytesIO(data))
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    (destination/'ffmpeg-compatibility-tests.tar.sha256').write_text(checksum+'  '+archive.name+'\n')
    (destination/'summary.json').write_text(json.dumps(inventory,indent=2))
    return {'archive':str(archive),'sha256':checksum,**{k:v for k,v in inventory.items() if k!='files'}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(build(args.destination),indent=2))


if __name__=='__main__':main()
