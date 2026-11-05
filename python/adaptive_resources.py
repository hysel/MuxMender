"""Workload-aware resource plans; never change media acceptance policy."""
import math


def finite(n):return type(n) in (int,float) and math.isfinite(n) and n>=0


def cpu_room(data):
    """Leave host headroom after subtracting measured external CPU demand."""
    keys=('cpus','cpu_percent','container_cpu_percent')
    if any(not finite(data.get(k)) for k in keys) or not data['cpus']:return None
    if max(data['cpu_percent'],data['container_cpu_percent'])>100:return None
    host=data.get('host_cpus',data['cpus'] if not data.get('app_cpu_scope') else None)
    if not finite(host) or not host:return None
    host_used=host*data['cpu_percent']/100
    own_used=data['cpus']*data['container_cpu_percent']/100 if data.get('app_cpu_scope') is not False else 0
    external=max(0,host_used-own_used)
    reserve=min(max(1,host*.15),host*.25)
    return max(0,min(data['cpus'],host-external-reserve))


def memory_room(data,extra_gib=2):
    """Only currently available RAM funds parallel work, never total ARC size."""
    if not finite(extra_gib) or not finite(data.get('available_gib')) or not finite(data.get('host_available_gib')):return False
    # The reported availability already excludes resident workers. Reserve room
    # for the host and compare the additional stage's measured/estimated peak.
    return data['available_gib']>=extra_gib+3 and data['host_available_gib']>=extra_gib+4


def pressure_ok(data):
    return (all(finite(data.get(k)) for k in ('memory_pressure','io_pressure'))
            and data['memory_pressure']<.1 and data['io_pressure']<5
            and (not finite(data.get('zfs_need_free_gib')) or data['zfs_need_free_gib']==0))


def validation_plan(data,stage_cost=2,cpu_cost=2):
    """Budget qualified primary workers plus decoder capacity, not a CPU % gate.

    Count the current workload through actual available memory. Eight is the
    existing qualified aggregate worker budget, not an instruction to run eight
    jobs. Higher per-stage worker counts still require their own qualification.
    """
    room=cpu_room(data)
    if room is None or not pressure_ok(data):return dict(capacity=1,workers=2,reason='Waiting for complete, stable resource measurements')
    workers=min(8,max(2,int(room)-2))
    own=data['cpus']*data['container_cpu_percent']/100
    capacity=2 if workers>=6 and room-own>=cpu_cost and memory_room(data,stage_cost) else 1
    return dict(capacity=capacity,workers=workers,
        reason='Measured CPU and memory room for overlapping checks' if capacity==2 else 'Concentrating available resources on one check')


class WorkloadPlan:
    """Focus first; overlap only when another stage can use a different resource.

    Profiles remain upper bounds. Pressure and an existing same-resource queue
    prevent more starts. This is resource admission, not proof of a speed gain.
    """
    def __init__(self):self.healthy_since=None;self.last_launch=0;self.status={}

    def decide(self,data,workload,active,ceiling,now):
        room=cpu_room(data);target=1;reason='Focusing resources on one video'
        known=isinstance(workload,dict) and workload.get('valid') is True
        stages=workload.get('active',[]) if known else []
        waiting=workload.get('waiting',[]) if known else []
        blocked=(room is None or room<.25 or not pressure_ok(data) or not memory_room(data))
        if blocked:self.healthy_since=None;reason='Waiting for shared-host resource headroom'
        elif not known:self.healthy_since=None;reason='Confirming active stage demands before adding work'
        elif waiting:
            self.healthy_since=None;reason='Finishing current videos before adding work behind the same resource queue'
        else:
            if self.healthy_since is None:self.healthy_since=now
            cost=sum(s.get('cpu_cost',2) for s in stages if finite(s.get('cpu_cost',2)))
            needed=2  # One bounded new start; stage admission checks its real demand.
            if stages and room-cost<needed:self.healthy_since=None
            if stages and room-cost>=needed and self.healthy_since is not None and now-self.healthy_since>=30:
                target=min(ceiling,active+1);reason='Measured headroom for a bounded overlap trial'
            elif active and not stages and self.healthy_since is not None and now-self.healthy_since>=30:
                target=min(ceiling,active+1);reason='Current work leaves processing capacity available'
        allowed=not blocked and (active==0 or known and active<target and now-self.last_launch>=30)
        if not blocked and known and 0<active<target and now-self.last_launch<30:
            reason='Observing the new video before starting another'
        self.status=dict(target=target,maximum=ceiling,active=active,reason=reason,
            cpu_budget=room,mode='focus' if target==1 else 'overlap-trial',throughput_gain_verified=False)
        return allowed
