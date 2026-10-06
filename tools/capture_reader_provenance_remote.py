"""Capture immutable reader identity before the active real-file GPU pass."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from job_tracking import Job


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--monitor-config',type=Path,required=True)
    args=parser.parse_args()
    records=json.loads(args.monitor_config.read_text())
    if len(records)!=1:raise ValueError('Expected one live research observer')
    remote=records[0]['roots'][0]
    if not re.fullmatch('/work/hdr-gpu-reader-[0-9a-f]{32}',remote):raise ValueError('Unexpected research root')
    job=Job('E:/MuxMender-TestOutputs/performance-followup-20261001/reports','Reader build identity before GPU inspection')
    payload="""import hashlib,json,os,pathlib,sys,time
if not sys.platform.startswith('linux'):raise RuntimeError('Linux provenance only')
root=pathlib.Path(REMOTE)
jobs=list(root.glob('qualification/reports/*/job.json'))
if len(jobs)!=1:raise ValueError('Expected one real-file research job')
state=json.loads(jobs[0].read_text());pid=state['pid']
if state.get('state')!='running' or state.get('phase') not in ('Whole-file real AV1 inspection: cpu','Whole-file real HEVC inspection: cpu'):
 raise ValueError('GPU pass may have started; cannot assert before-pass provenance')
if not pathlib.Path('/proc/'+str(pid)).is_dir():raise ValueError('Research supervisor is no longer live')
binary=pathlib.Path('/output/hdr-gpu-reader-build-20261002-r3/binary-r3/bin/ffprobe-cuda')
info=binary.stat()
if info.st_uid!=0 or info.st_mode&0o022 or binary.is_symlink():raise ValueError('Reader is not immutable image-owned data')
if not os.statvfs(binary).f_flag&os.ST_RDONLY:raise ValueError('Reader is not on a read-only research mount')
sys.path.insert(0,str(root/'python'))
from encoder_capabilities import nvidia_adapters
adapters=nvidia_adapters()
if len(adapters)!=1:raise ValueError('Expected one visible GPU')
print(json.dumps(dict(captured=time.time(),before_gpu_pass=True,remote_job_pid=pid,
 binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),read_only_mount=True,
 adapter={k:adapters[0][k] for k in ('uuid','driver')},
 visibility={k:os.environ.get(k) for k in ('CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER')})))
""".replace('REMOTE',repr(remote))
    try:
        result=subprocess.run(['ssh','-i','C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519',
            '-o','BatchMode=yes','-o','ConnectTimeout=5','muxmender@192.168.1.232',
            'sudo -n /root/muxmender-research-access'],input=payload,text=True,capture_output=True,timeout=30)
        if result.returncode:raise RuntimeError(result.stderr[-2000:])
        witness=json.loads(result.stdout)
        with (args.monitor_config.parent/'reader-artifact-before-gpu.json').open('x') as stream:
            json.dump(witness,stream,indent=2)
        job.save(state='completed',phase='Immutable reader identity captured',
                 detail='Read-only artifact SHA256 and live GPU/driver visibility recorded before the GPU pass. This alone does not qualify the reader.',finished=time.time())
        print('Immutable reader provenance captured; production unchanged')
        return 0
    except BaseException as exc:
        job.save(state='failed',phase='Reader provenance not established',error=str(exc),finished=time.time())
        raise


if __name__=='__main__':raise SystemExit(main())
