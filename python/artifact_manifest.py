"""Record newly generated command outputs, independently of file extension."""
from contextlib import contextmanager
import json
from pathlib import Path


def stamp(path):
    s=path.stat()
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]


@contextmanager
def command_outputs(root,command,*,mutated=()):
    from replacement_cleanup import safe_path
    root=Path(root).resolve(strict=True);safe_path(root)
    candidates=[]
    if mutated:
        owned=registered_outputs(root)
        for value in mutated:
            path=Path(value).resolve(strict=True)
            if path not in owned:raise ValueError('Mutation requires an unchanged registered generated output')
            candidates.append(path)
    for arg in command:
        try:
            path=Path(arg)
            if not path.is_absolute() or path.exists() or path.is_symlink():continue
            safe_path(path)
            if path.resolve().is_relative_to(root):candidates.append(path)
        except (TypeError,OSError,ValueError):continue
    try:yield
    finally:
        entries=[]
        for path in dict.fromkeys(candidates):
            if not path.is_file() or path.is_symlink():continue
            safe_path(path)
            entries.append(dict(path=str(path.relative_to(root)),identity=stamp(path),kind='generated-command-output'))
        if entries:
            manifest=root/'generated-artifacts.jsonl';safe_path(manifest)
            with manifest.open('a',encoding='utf-8') as out:
                for entry in entries:out.write(json.dumps(entry)+'\n')


def registered_outputs(root):
    from replacement_cleanup import safe_path
    root=Path(root).resolve(strict=True);manifest=root/'generated-artifacts.jsonl'
    safe_path(manifest)
    if not manifest.exists():return set()
    latest={}
    with manifest.open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():continue
            entry=json.loads(line);path=Path(entry['path'])
            if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe generated artifact manifest path')
            path=root/path;safe_path(path)
            if not path.resolve().is_relative_to(root):raise ValueError('Artifact escapes work directory')
            latest[path]=entry
    for path,entry in latest.items():
        if path.exists() and (not path.is_file() or stamp(path)!=entry['identity']):
            raise ValueError('Registered artifact changed; cleanup requires review')
    return {path for path in latest if path.exists()}
