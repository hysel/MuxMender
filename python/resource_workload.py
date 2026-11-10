"""OS-leased stage demand records for adaptive admission; no media paths."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time
import uuid
import threading

_current=threading.local()


class CommandGroup(list):
    """Actual commands flattened for classification, never for execution."""
    def __init__(self, commands):
        self.components = tuple(tuple(c) for c in commands)
        super().__init__(arg for command in self.components for arg in command)


def group_command(command, producers):
    return CommandGroup((command, *producers)) if producers else command


def observed(cpu_cost,resident_gib,peak_cores):
    lease=getattr(_current,'lease',None)
    if lease is not None:
        lease.data.setdefault('estimated_cpu_cost',lease.data['cpu_cost'])
        lease.data.update(cpu_cost=cpu_cost,resident_gib=resident_gib,observed_peak_cores=peak_cores)
        lease.write()


def demand(command,env=None):
    if isinstance(command, CommandGroup):
        parts=[demand(c,env) for c in command.components]
        return dict(kind='mixed-quality',cpu_cost=min(16,sum(p['cpu_cost'] for p in parts)),
            memory_gib=sum(p['memory_gib'] for p in parts),cpu_inputs=sum(p['cpu_inputs'] for p in parts),
            gpu_encode=any(p['gpu_encode'] for p in parts),gpu_decode=any(p['gpu_decode'] for p in parts),
            gpu_compute=any(p['gpu_compute'] for p in parts),scoring_threads=max(p['scoring_threads'] for p in parts))
    graphs=[str(command[i+1]) for i,k in enumerate(command[:-1]) if k in ('-vf','-filter:v','-filter:v:0','-filter_complex','-lavfi')]
    quality=any('libvmaf' in g for g in graphs)
    gpu_render=any(any(v in g for v in ('libplacebo','scale_cuda','scale_npp','libvmaf_cuda')) for g in graphs)
    encode=any((str(k) in ('-c:v','-codec:v','-vcodec') or str(k).startswith(('-c:v:','-codec:v:'))) and str(command[i+1]).endswith('_nvenc') for i,k in enumerate(command[:-1]))
    gpu_decode=(any(k=='-hwaccel' and str(command[i+1]).lower() not in ('none','0') for i,k in enumerate(command[:-1])) or (env or {}).get('MUXMENDER_RESEARCH_CUDA_READER')=='1')
    threads=[int(command[i+1]) for i,k in enumerate(command[:-1]) if k in ('-threads','-threads:v') and str(command[i+1]).isdigit()]
    scoring=[int(n) for g in graphs for n in re.findall(r'n_threads=(\d+)',g)]
    decode_cost=0 if gpu_decode else min(8,command.count('-i')*max(threads,default=2))
    cost=decode_cost+max(scoring,default=2) if quality else max(2,decode_cost) if encode else max(threads,default=2)
    kind='mixed-quality' if quality and gpu_render else 'cpu-quality' if quality else 'encode' if encode else 'gpu-decode' if gpu_decode else 'cpu-check'
    return dict(kind=kind,cpu_cost=min(16,max(1,cost)),memory_gib=2,cpu_inputs=0 if gpu_decode else command.count('-i'),
        gpu_encode=encode,gpu_decode=gpu_decode,gpu_compute=gpu_render,scoring_threads=max(scoring,default=0))


def single_cpu_encode(request):
    """One software-decoded input feeding the dedicated NVIDIA encoder."""
    return (request.get('kind')=='encode' and request.get('gpu_encode') is True
            and not request.get('gpu_decode') and not request.get('gpu_compute')
            and request.get('cpu_inputs')==1)


def safe_root(root):
    path=Path(root)/'workloads'
    if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Unsafe workload state root')
    return path


class StageLease:
    def __init__(self,path,command,env):
        import fcntl
        self.path=path;self.file=path/('stage-'+uuid.uuid4().hex+'.lock')
        self.fd=os.open(self.file,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.data=dict(demand(command,env),state='waiting',started=time.monotonic())
        self.write()

    def write(self):
        raw=json.dumps(self.data).encode();os.lseek(self.fd,0,os.SEEK_SET);os.write(self.fd,raw);os.ftruncate(self.fd,len(raw))

    def active(self,workers=None):
        self.data.update(state='active',admitted=time.monotonic())
        if type(workers) is int:
            self.data['allocated_workers']=workers
            if self.data.get('scoring_threads'):self.data['cpu_cost']=max(1,self.data['cpu_cost']-max(0,self.data['scoring_threads']-workers))
            elif self.data['kind']=='cpu-check':self.data['cpu_cost']=min(self.data['cpu_cost'],workers)
            elif single_cpu_encode(self.data):self.data['cpu_cost']=min(self.data['cpu_cost'],workers)
        self.write()

    def close(self):
        try:self.file.unlink(missing_ok=True)
        finally:os.close(self.fd)


@contextmanager
def request(command,env=None):
    root=(os.environ if env is None else env).get('MUXMENDER_VALIDATION_LOCK_ROOT')
    if os.name!='posix' or not root:yield None;return
    path=safe_root(root);path.mkdir(parents=True,exist_ok=True);lease=StageLease(path,command,env)
    previous=getattr(_current,'lease',None);_current.lease=lease
    try:yield lease
    finally:
        _current.lease=previous;lease.close()


def snapshot(root):
    if os.name!='posix':return dict(valid=False,active=[],waiting=[])
    import fcntl
    path=safe_root(root)
    if not path.exists():return dict(valid=True,active=[],waiting=[])
    rows=[];valid=True
    from itertools import islice
    files=list(islice(path.glob('stage-*.lock'),65))
    if len(files)>64:return dict(valid=False,active=[],waiting=[])
    for file in files:
        fd=None
        try:
            fd=os.open(file,os.O_RDWR|os.O_NOFOLLOW)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                raw=os.pread(fd,4097,0)
                if len(raw)>4096:raise ValueError('Oversized stage record')
                row=json.loads(raw)
                if not isinstance(row,dict) or row.get('state') not in ('active','waiting'):raise ValueError('Incomplete stage demand')
                from adaptive_resources import finite
                if not finite(row.get('cpu_cost')) or not 0<row['cpu_cost']<=16:raise ValueError('Invalid stage demand')
                rows.append(row)
            else:file.unlink(missing_ok=True)  # Dead leases only, never media.
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError):valid=False
        finally:
            if fd is not None:os.close(fd)
    return dict(valid=valid,active=[r for r in rows if r['state']=='active'],waiting=[r for r in rows if r['state']=='waiting'])


def legacy_busy(root):
    if os.name!='posix':return False
    import fcntl
    for folder in (Path(root),Path(root)/'gpu'):
        if folder.is_symlink():raise ValueError('Linked legacy resource pool')
        for name in ('heavy-reader.lock','heavy-reader-2.lock'):
            try:fd=os.open(folder/name,os.O_RDWR|os.O_NOFOLLOW)
            except FileNotFoundError:continue
            try:
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:return True
            finally:os.close(fd)
    return False
