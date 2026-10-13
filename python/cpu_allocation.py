"""Portable CPU allocation advice; never changes container or OS limits."""
import math
import os
from pathlib import Path
import time

_cached=None
_checked=0


def detect(root=Path('/sys/fs/cgroup')):
    logical=os.cpu_count()
    limits=[logical] if logical else []
    affinity=None;physical=None;quotas=[]
    try:affinity=len(os.sched_getaffinity(0))
    except (AttributeError,OSError):
        try:
            import psutil
            affinity=len(psutil.Process().cpu_affinity())
        except (ImportError,AttributeError,OSError):pass
        if affinity is None and hasattr(os,'process_cpu_count'):affinity=os.process_cpu_count()
    try:
        import psutil
        physical=psutil.cpu_count(logical=False)
    except ImportError:pass
    if physical is None:
        try:
            blocks=Path('/proc/cpuinfo').read_text().strip().split('\n\n')
            rows=[dict(line.split(':',1) for line in block.splitlines() if ':' in line) for block in blocks]
            rows=[{k.strip():v.strip() for k,v in row.items()} for row in rows]
            if rows and all('physical id' in r and 'core id' in r for r in rows):
                physical=len({(r['physical id'],r['core id']) for r in rows})
        except (OSError,ValueError):pass
    if affinity:limits.append(affinity)
    bases=[root]
    try:
        for line in Path('/proc/self/cgroup').read_text().splitlines():
            _,controllers,path=line.split(':',2)
            if not controllers or 'cpu' in controllers.split(','):
                candidate=root/path.lstrip('/')
                if candidate.is_relative_to(root) and '..' not in candidate.parts:
                    bases.extend([candidate,*[p for p in candidate.parents if p.is_relative_to(root)]])
    except (OSError,ValueError):pass
    for base in set(bases):
        try:
            amount,period=(base/'cpu.max').read_text().split()
            if amount!='max' and float(amount)>0 and float(period)>0:quotas.append(float(amount)/float(period))
        except (OSError,ValueError):pass
        for folder in (base,base/'cpu',base/'cpu,cpuacct'):
            try:
                quota=int((folder/'cpu.cfs_quota_us').read_text())
                period=int((folder/'cpu.cfs_period_us').read_text())
                if quota>0 and period>0:quotas.append(quota/period)
            except (OSError,ValueError):pass
    limits.extend(q for q in quotas if math.isfinite(q))
    return dict(logical_cpus=logical,physical_cores=physical,affinity_cpus=affinity,
                quota_cpus=min(quotas) if quotas else None,
                effective_cpus=min(limits) if limits else None)


def capacity():
    global _cached,_checked
    if _cached is None or time.monotonic()-_checked>30:
        _cached=detect();_checked=time.monotonic()
    return dict(_cached)


def preference(mode='automatic',ceiling=None):
    if mode not in ('automatic','shared','custom'):raise ValueError('Unknown CPU allocation mode')
    if mode=='custom' and (type(ceiling) is not int or not 1<=ceiling<=1024):
        raise ValueError('Choose a scoring thread ceiling from 1 to 1024')
    return dict(mode=mode,ceiling=ceiling if mode=='custom' else None)


def recommendation(info,telemetry=None,setting=None):
    setting=preference(**(setting or {}));data=telemetry or {}
    available=info.get('effective_cpus')
    if type(available) not in (int,float) or not math.isfinite(available) or available<=0:
        suggested=1;reason='CPU allocation could not be confirmed; start with one scoring thread.'
    else:
        # Advice stays within measured worker counts; not all logical CPUs should
        # become metric workers. Decoding and other applications need headroom.
        suggested=4 if available>=8 else 2 if available>=4 else 1
        reason='Leaves CPU capacity for decoding and other applications.'
    if setting['mode']=='shared':suggested=min(suggested,2)
    if setting['mode']=='custom':suggested=min(suggested,setting['ceiling'])
    if suggested==3:suggested=2
    if data.get('cpu_percent',0)>70 or data.get('container_cpu_percent',0)>70:
        suggested=1;reason='CPU is busy; reduce scoring work until activity falls.'
    if data.get('available_gib',8)<4:
        suggested=1;reason='Available memory is low; use one scoring thread.'
    logical=info.get('logical_cpus')
    allocation=min(8,logical) if type(logical) is int and logical>0 else None
    return dict(**info,setting=setting,recommended_scoring_threads=suggested,reason=reason,
        suggested_single_job_allocation_cpus=allocation,
        note='Per-stage ceiling, not reserved CPU cores. Existing resource checks may use fewer threads. Qualified AV1 scoring can use four threads with headroom; no quality thresholds change.')


def scoring_ceiling(selected):
    """Restrict an already-qualified choice, never enable a new fast path."""
    mode=os.environ.get('MUXMENDER_CPU_MODE','automatic')
    try:
        limit=int(os.environ.get('MUXMENDER_SCORING_CEILING','2')) if mode=='custom' else None
        setting=preference(mode,limit)
    except ValueError:setting=preference('shared')
    count=recommendation(capacity(),setting=setting)['recommended_scoring_threads']
    return min(selected,count)
