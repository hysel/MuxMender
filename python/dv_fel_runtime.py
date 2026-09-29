"""Process-local configuration for an optional, manifest-bound FEL runtime."""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys


def manifest(plugin):
    plugin=Path(plugin).resolve(strict=True)
    path=plugin.parent/'runtime.json'
    if not path.exists():return None
    if path.stat().st_size>65536:raise ValueError('FEL runtime manifest is oversized')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema')!='muxmender-fel-runtime-v1':raise ValueError('Unsupported FEL runtime manifest')
    if data.get('plugin_sha256')!=hashlib.sha256(plugin.read_bytes()).hexdigest():
        raise ValueError('FEL renderer library differs from its runtime manifest')
    return data


def child_environment(plugin,base=None):
    """Never alter the app/encoder environment to load renderer dependencies."""
    environment=dict(os.environ if base is None else base)
    data=manifest(plugin)
    if data is None:return environment
    root=Path(plugin).resolve(strict=True).parent
    for key,variable in [('library_dir','LD_LIBRARY_PATH'),('python_dir','PYTHONPATH')]:
        value=data.get(key)
        if not isinstance(value,str) or not value:raise ValueError('Missing FEL runtime '+key)
        directory=(root/value).resolve(strict=True)
        if not directory.is_relative_to(root) or not directory.is_dir():
            raise ValueError('FEL runtime dependency path escapes its directory')
        environment[variable]=str(directory)+(os.pathsep+environment[variable] if environment.get(variable) else '')
    environment['PYTHONNOUSERSITE']='1'
    return environment


def cpu_features():
    text=Path('/proc/cpuinfo').read_text(encoding='ascii',errors='replace')
    rows=[set(line.split(':',1)[1].split()) for line in text.splitlines() if line.startswith('flags') and ':' in line]
    return set.intersection(*rows) if rows else set()


def validate_worker(plugin):
    data=manifest(plugin)
    if data is None:return  # Explicit manually configured dependency; loader validates its ABI.
    if sys.platform!='linux' or platform.machine().lower() not in ('x86_64','amd64'):
        raise RuntimeError('This pinned FEL runtime requires Linux x86-64')
    if data.get('python_version')!=list(sys.version_info[:2]):
        raise RuntimeError('FEL runtime Python ABI does not match the renderer executable')
    required=data.get('required_cpu_features')
    if not isinstance(required,list) or any(not isinstance(x,str) or not x for x in required):
        raise ValueError('Invalid renderer CPU requirements')
    if not set(required)<=cpu_features():raise RuntimeError('CPU lacks instructions required by this FEL renderer build')
