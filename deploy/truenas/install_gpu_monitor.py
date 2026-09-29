"""Administrator-run, self-contained installation of the read-only GPU monitor.

No packages, Docker access, media access, or persistent /etc modifications.
Use --start from a TrueNAS Post Init task after installing once.
"""
import argparse
import base64
import grp
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

# Populated when preparing the deployment bundle from python/gpu_activity.py.
COLLECTOR_B64 = ''
INSTALL_ROOT = Path('/root/muxmender-gpu-monitor')
CODE = Path('/run/muxmender-gpu-monitor-code')
DATA = Path('/run/muxmender-gpu-monitor')
UNIT = Path('/run/systemd/system/muxmender-gpu-monitor.service')


def protected_directory(path, mode=0o700, gid=0):
    if path.is_symlink():
        raise ValueError('Refusing symlink: '+str(path))
    path.mkdir(mode=mode, exist_ok=True)
    info=path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('Directory must be root-owned and not group/world writable: '+str(path))
    os.chown(path, 0, gid)
    path.chmod(mode)


def protected_file(path, content, mode=0o600):
    if path.exists() or path.is_symlink():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Unsafe existing file: '+str(path))
        if path.read_bytes()!=content:
            raise ValueError('Existing file differs; refusing to overwrite: '+str(path))
        return
    fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as target:
        target.write(content)


def service_text(group):
    return f'''[Unit]
Description=MuxMender read-only NVIDIA process telemetry
After=multi-user.target

[Service]
Type=simple
User=root
Group={group}
UMask=0027
ExecStart=/usr/bin/python3 -I -B {CODE}/gpu_activity.py --output {DATA}/activity.json
Restart=on-failure
RestartSec=5
TimeoutStopSec=10
NoNewPrivileges=yes
CapabilityBoundingSet=CAP_SYS_PTRACE CAP_DAC_READ_SEARCH
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths={DATA}
InaccessiblePaths=-/mnt -/media -/run/docker.sock -/var/run/docker.sock
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictAddressFamilies=AF_UNIX
LockPersonality=yes
MemoryMax=256M
TasksMax=32
CPUQuota=10%
StandardOutput=journal
StandardError=journal
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--install', action='store_true')
    mode.add_argument('--start', action='store_true')
    parser.add_argument('--group', type=int, default=3005, help='Numeric app group allowed to read telemetry')
    args=parser.parse_args()
    if not sys.platform.startswith('linux') or os.geteuid()!=0:
        parser.error('Run as administrator on the TrueNAS Linux host')
    if args.group<1:
        parser.error('Use the non-root app group')
    grp.getgrgid(args.group)
    os.umask(0o027)
    if args.install:
        if not COLLECTOR_B64:
            parser.error('Use the prepared bundle, not this unpopulated source template')
        collector=base64.b64decode(COLLECTOR_B64, validate=True)
        protected_directory(INSTALL_ROOT)
        protected_file(INSTALL_ROOT/'gpu_activity.py', collector)
        protected_file(INSTALL_ROOT/'bootstrap.py', Path(__file__).read_bytes())
        config=dict(group=args.group, sha256=hashlib.sha256(collector).hexdigest())
        protected_file(INSTALL_ROOT/'config.json', json.dumps(config,sort_keys=True).encode())
    else:
        if Path(__file__).resolve()!=INSTALL_ROOT/'bootstrap.py':
            parser.error('Start only the installed root-owned bootstrap')
    protected_directory(INSTALL_ROOT)
    config=json.loads((INSTALL_ROOT/'config.json').read_text())
    collector=(INSTALL_ROOT/'gpu_activity.py').read_bytes()
    if hashlib.sha256(collector).hexdigest()!=config['sha256']:
        raise ValueError('Installed monitor hash mismatch')
    protected_directory(CODE)
    protected_file(CODE/'gpu_activity.py',collector)
    protected_directory(DATA,0o750,int(config['group']))
    protected_file(UNIT,service_text(int(config['group'])).encode(),0o644)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','start',UNIT.name],check=True)
    subprocess.run(['systemctl','is-active',UNIT.name],check=True)
    for _ in range(15):
        try:
            snapshot=json.loads((DATA/'activity.json').read_text())
            if time.time()-snapshot['updated']<10:
                print('Fresh GPU telemetry. Complete:',snapshot.get('complete'))
                break
        except (OSError,ValueError,KeyError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Monitor started but no fresh telemetry; inspect its journal')
    print('Read-only app mount:',str(DATA),'-> /gpu-telemetry')
    print('App variable: MUXMENDER_GPU_TELEMETRY=/gpu-telemetry/activity.json')
    print('TrueNAS Post Init command: /usr/bin/python3 -I -B '+str(INSTALL_ROOT/'bootstrap.py')+' --start')
    print('No production app, queue or media files were changed.')


if __name__=='__main__':
    main()
