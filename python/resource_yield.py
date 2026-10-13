"""Hysteretic CPU contention policy, without signaling or changing quality."""
import math
import time


class CPUYieldPolicy:
    def __init__(self):
        self.busy_since=None;self.quiet_since=None;self.last=None;self.paused=False

    def decide(self,data,now=None):
        now=time.monotonic() if now is None else now
        valid=(data.get('app_cpu_scope') is True and all(
            type(data.get(k)) in (int,float) and math.isfinite(data[k]) and data[k]>=0
            for k in ('host_cpus','cpus','cpu_percent','container_cpu_percent'))
            and data.get('host_cpus',0)>0 and 0<data.get('cpus',0)<=data.get('host_cpus',0)
            and data.get('cpu_percent',101)<=100 and data.get('container_cpu_percent',101)<=100)
        if not valid:
            self.__init__()
            return dict(pause=False,block_admission=False,state='unavailable',
                reason='CPU ownership unavailable; stage budgets and ordinary admission checks remain active')
        if self.last is not None and not 0<=now-self.last<=15:self.__init__()
        self.last=now
        host=data['host_cpus'];host_busy=host*data['cpu_percent']/100
        owned=data['cpus']*data['container_cpu_percent']/100
        external=max(0,host_busy-owned)
        # High usage from MuxMender alone is useful work, not a reason to pause.
        busy=data['cpu_percent']>=85 and external>=max(1,host*.25)
        if busy:
            if self.busy_since is None:self.busy_since=now
            self.quiet_since=None
            if now-self.busy_since>=10:self.paused=True
        else:
            self.busy_since=None
            # Hysteresis avoids rapid stop/start when a large stage resumes.
            if data['cpu_percent']<=65:
                if self.quiet_since is None:self.quiet_since=now
                if now-self.quiet_since>=60:self.paused=False
            else:self.quiet_since=None
        return dict(pause=self.paused,block_admission=busy or self.paused,
            state='yielding' if self.paused else 'busy' if busy else 'available',
            external_cpu_equivalents=external,
            reason=('Yielding CPU to other applications; waiting for 60 seconds of headroom' if self.paused
                    else 'Competing CPU load; holding new starts' if busy else 'CPU headroom available'))
