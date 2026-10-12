"""Read-only Linux diagnostic for an installed qualification rejection."""
import json
import os
from pathlib import Path
import sys


def main():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Installed reader diagnostics run on Linux only')
    from gpu_frame_reader import trusted_file, load_qualification, HOST_QUALIFICATION_ROOT
    from encoder_capabilities import nvidia_adapters
    root = Path('/opt/muxmender-readers')
    report = dict(adapters=nvidia_adapters(), visibility={key: os.environ.get(key) for key in
        ('CUDA_VISIBLE_DEVICES', 'NVIDIA_VISIBLE_DEVICES', 'CUDA_DEVICE_ORDER')}, files={})
    for name, path, limit in [('qualification.json',root/'qualification.json',65536),
            ('host_qualification.json',HOST_QUALIFICATION_ROOT/'qualification.json',65536),
            ('ffprobe-cuda',root/'ffprobe-cuda',64*1024*1024)]:
        try:
            trusted_file(path, limit)
            report['files'][name] = dict(trusted=True, executable=os.access(path, os.X_OK))
        except (OSError, ValueError) as exc:
            report['files'][name] = dict(trusted=False, error=str(exc))
    report['directories'] = []
    for path in dict.fromkeys((root,HOST_QUALIFICATION_ROOT,*root.parents)):
        try:
            info = path.stat()
            report['directories'].append(dict(path=str(path), uid=info.st_uid, mode=oct(info.st_mode & 0o7777)))
        except OSError as exc:report['directories'].append(dict(path=str(path),error=str(exc)))
    report['loader_accepted'] = load_qualification() is not None
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
