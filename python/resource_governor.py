"""Read-only shared-host telemetry and conservative job admission.

Backoff drains active jobs; it does not suspend FFmpeg or weaken validation.
"""
import os
import math
from pathlib import Path
import subprocess
import time

PROFILES={
    'quiet':dict(max_jobs=1,cpu=55,memory_gib=8,gpu=60,io=5),
    'shared':dict(max_jobs=2,cpu=70,memory_gib=8,gpu=75,io=8),
    'faster':dict(max_jobs=4,cpu=80,memory_gib=6,gpu=85,io=12),
}


def arc_memory(text):
    """Account only resident evictable ARC, never ghost/L2 or pinned buffers."""
    rows={parts[0]:int(parts[2]) for line in text.splitlines()
          if len(parts:=line.split())==3 and parts[1] in ('3','4')}
    keys=('size','c_min','mru_evictable_data','mru_evictable_metadata',
          'mfu_evictable_data','mfu_evictable_metadata','arc_need_free')
    if any(k not in rows or rows[k]<0 for k in keys):raise ValueError('Incomplete ARC telemetry')
    reclaim=min(max(0,rows['size']-rows['c_min']),sum(rows[k] for k in keys[2:6]))
    return dict(zfs_arc_gib=rows['size']/1024**3,zfs_reclaimable_gib=reclaim/1024**3,
                zfs_need_free_gib=rows['arc_need_free']/1024**3)


def cache_assisted_start(data, required):
    """Bounded serial admission, not a promise that cache is immediately free."""
    keys=('host_available_gib','host_free_gib','zfs_reclaimable_gib',
          'zfs_need_free_gib','memory_pressure','io_pressure')
    if any(k not in data or not math.isfinite(data[k]) or data[k]<0 for k in keys):return False
    # Use max rather than adding to MemAvailable, which may include cache already.
    budget=max(data['host_available_gib'],data['host_free_gib']+min(8,data['zfs_reclaimable_gib']*.5))
    return (data['host_available_gib']>=6 and data['zfs_reclaimable_gib']>=8
            and data['zfs_need_free_gib']==0 and data['memory_pressure']<.1
            and data['io_pressure']<5 and budget>=required)


def allocated_cpu_usage(previous, current, cpus):
    """Percent of the CPU allocation, not percent of the entire host."""
    elapsed=current[0]-previous[0]
    used=current[1]-previous[1]
    if elapsed<=0 or used<0 or not math.isfinite(cpus) or cpus<=0:return None
    return min(100.0,100*used/(1e6*elapsed*cpus))


def validation_thread_budget(data):
    """Bound one long HDR reader; unknown/pressured hosts retain two threads."""
    required=('cpus','cpu_percent','available_gib','host_available_gib','io_pressure','memory_pressure')
    if any(k not in data or not math.isfinite(data[k]) or data[k]<0 for k in required):return 2
    usage=max(data['cpu_percent'],data.get('container_cpu_percent',0))
    if (data['cpus']>=8 and usage<=50 and data['cpus']*(1-usage/100)>=6
            and data['available_gib']>=8 and data['host_available_gib']>=12
            and data['io_pressure']<5 and data['memory_pressure']<.1):return 4
    return 2


def hdr_validation_threads():
    governor=Governor()
    governor.sample(include_gpu=False)
    time.sleep(.25)
    return validation_thread_budget(governor.sample(include_gpu=False))


class Governor:
    def __init__(self):
        self.previous=None;self.healthy_since=None;self.last_launch=0
        self.previous_container_cpu=None
        self.status=dict(reason='Collecting resource measurements',telemetry={})

    def sample(self, *, include_gpu=True):
        values={}
        try:
            counters=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
            total=sum(counters);idle=counters[3]+counters[4]
            if self.previous and total>self.previous[0]:
                values['cpu_percent']=100*(1-(idle-self.previous[1])/(total-self.previous[0]))
            self.previous=(total,idle)
            info=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
            values['available_gib']=int(info['MemAvailable'].split()[0])/1024**2
            values['host_available_gib']=values['available_gib']
            values['host_free_gib']=int(info['MemFree'].split()[0])/1024**2
            values['host_total_gib']=int(info['MemTotal'].split()[0])/1024**2
            values['cpus']=len(os.sched_getaffinity(0))
            # Respect a container memory limit; host cache is not free container RAM.
            limit=Path('/sys/fs/cgroup/memory.max')
            if limit.exists() and limit.read_text().strip()!='max':
                values['container_limit_gib']=int(limit.read_text())/1024**3
                remaining=values['container_limit_gib']-int(Path('/sys/fs/cgroup/memory.current').read_text())/1024**3
                values['container_available_gib']=max(0,remaining)
                values['available_gib']=min(values['available_gib'],remaining)
            quota=Path('/sys/fs/cgroup/cpu.max')
            if quota.exists():
                amount,period=quota.read_text().split()
                if amount!='max':values['cpus']=min(values['cpus'],float(amount)/float(period))
            for kind in ('io','memory'):
                line=Path('/proc/pressure/'+kind).read_text().splitlines()[0]
                values[kind+'_pressure']=float(dict(x.split('=') for x in line.split()[1:])['avg10'])
        except (OSError,ValueError,KeyError,AttributeError):pass
        try:values.update(arc_memory(Path('/proc/spl/kstat/zfs/arcstats').read_text()))
        except (OSError,ValueError):pass
        try:
            counters=dict(line.split() for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())
            current=(time.monotonic(),int(counters['usage_usec']))
            if self.previous_container_cpu is not None:
                percent=allocated_cpu_usage(self.previous_container_cpu,current,values.get('cpus',0))
                if percent is not None:values['container_cpu_percent']=percent
            self.previous_container_cpu=current
        except (OSError,ValueError,KeyError):pass
        if not include_gpu:return values
        try:
            result=subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu,utilization.encoder,utilization.decoder,memory.free,temperature.gpu',
                                            '--format=csv,noheader,nounits'],text=True,timeout=3)
            gpus=[list(map(float,line.split(','))) for line in result.strip().splitlines()]
            if any(len(g)!=5 or any(not math.isfinite(x) or x<0 for x in g) for g in gpus):
                raise ValueError('Incomplete GPU telemetry')
            if gpus:
                values.update(gpu_percent=max(max(g[:3]) for g in gpus),vram_free_gib=min(g[3] for g in gpus)/1024,
                              gpu_temperature=max(g[4] for g in gpus),
                              gpu_compute_percent=max(g[0] for g in gpus),
                              gpu_encode_percent=max(g[1] for g in gpus),gpu_decode_percent=max(g[2] for g in gpus))
        except (OSError,ValueError,subprocess.SubprocessError):pass
        return values

    def admit(self, profile, active, now=None):
        now=time.monotonic() if now is None else now
        limits=PROFILES[profile];data=self.sample();reason=None
        maximum=min(limits['max_jobs'],max(1,int(data.get('cpus',2)//2)))
        host_available=data.get('host_available_gib',data.get('available_gib',0))
        # Keep the host's profile reserve, but do not demand ten free GiB inside
        # an eight-GiB app. Retain a container reserve plus two GiB per new job.
        container_required=2+min(2,max(1,data.get('container_limit_gib',0)*.2))
        cache_assisted=host_available<limits['memory_gib']+2 and cache_assisted_start(data,limits['memory_gib']+2)
        if cache_assisted:maximum=1
        if not math.isfinite(host_available) or (host_available<limits['memory_gib']+2 and not cache_assisted):reason='Waiting for memory headroom'
        elif ('container_available_gib' in data and
              data['container_available_gib']<container_required):reason='Waiting for container memory headroom'
        elif data.get('cpu_percent',100)>limits['cpu']:reason='Waiting for CPU headroom'
        elif data.get('container_cpu_percent',0)>limits['cpu']:reason='Waiting for container CPU allocation headroom'
        elif data.get('io_pressure',100)>limits['io']:reason='Waiting for storage pressure to fall'
        elif data.get('memory_pressure',100)>1:reason='Waiting for memory pressure to fall'
        elif data.get('gpu_percent',0)>limits['gpu']:reason='Waiting for GPU headroom'
        elif data.get('vram_free_gib',8)<2:reason='Waiting for free GPU memory'
        elif data.get('gpu_temperature',0)>=80:reason='Waiting for GPU temperature to fall'
        # Unknown GPU telemetry: still support other vendors, but only serially.
        if 'gpu_percent' not in data:maximum=1
        if reason:self.healthy_since=None
        elif self.healthy_since is None:self.healthy_since=now
        if not reason and active>=maximum:reason='Concurrency ceiling reached'
        if not reason and active and (now-self.healthy_since<30 or now-self.last_launch<60):
            reason='Observing sustained headroom before adding a worker'
        if not reason and cache_assisted and now-self.healthy_since<30:
            reason='Observing memory headroom before one cache-assisted job'
        self.status=dict(profile=profile,ceiling=maximum,active=active,reason=reason or 'Resources available',
                         telemetry=data,cache_assisted=cache_assisted,updated=time.time(),policy='Backoff drains running jobs; does not suspend them')
        return reason is None
