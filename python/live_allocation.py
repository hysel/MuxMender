"""Read-only Linux child telemetry for advisory stage allocations, not CPU caps."""
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import sys
import threading
import time

_active=threading.local()


def target(original,rates):
    """Release at most two advisory cores, only after a sustained measurement."""
    if len(rates)<3 or any(type(r) not in (int,float) or not math.isfinite(r) or r<0 for r in rates):return original
    return min(16,max(1,original-2,math.ceil(max(rates)*1.2+.5)))


@contextmanager
def scope(root,tokens,request):
    previous=getattr(_active,'value',None)
    allocation=dict(root=Path(root),tokens=tokens,request=request)
    _active.value=allocation
    try:yield
    finally:_active.value=previous


def attach(pid):
    value=getattr(_active,'value',None)
    if os.name!='posix' or sys.platform!='linux' or value is None or type(pid) is not int or pid<=0:return None
    try:return Child(pid,value)
    except (OSError,ValueError,TypeError,KeyError):return None


class Child:
    def __init__(self,pid,allocation):
        self.pid=pid;self.allocation=allocation;self.start=time.monotonic();self.previous=None;self.identity=None;self.rates=[]
        self.original=len(allocation['tokens']);self.tick=os.sysconf('SC_CLK_TCK')
        if self.tick<=0 or not self.original:raise ValueError('Child resource clock unavailable')
        self.sample()

    def reset(self):
        self.start=time.monotonic();self.previous=None;self.rates=[]

    def sample(self):
        now=time.monotonic()
        if self.previous is not None and now-self.previous[0]<1:return
        try:
            path=Path('/proc')/str(self.pid);fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[1])!=os.getpid():return  # This exact direct child only.
            identity=int(fields[19])
            if self.identity is not None and identity!=self.identity:return
            self.identity=identity
            used=(int(fields[11])+int(fields[12]))/self.tick
            status=dict(line.split(':',1) for line in (path/'status').read_text().splitlines())
            resident=int(status['VmRSS'].split()[0])/1024**2
            confirmation=(path/'stat').read_text().rsplit(')',1)[1].split()
            if int(confirmation[19])!=identity or int(confirmation[1])!=os.getpid():return
            if self.previous is not None:
                rate=(used-self.previous[1])/(now-self.previous[0])
                if rate<0:return
                self.rates=(self.rates+[rate])[-20:]
            self.previous=(now,used)
            tokens=self.allocation['tokens']
            wanted=target(self.original,self.rates) if now-self.start>=10 else self.original
            import fcntl
            coordinator=os.open(self.allocation['root']/'cpu-budget/admission.lock',os.O_RDWR|os.O_NOFOLLOW)
            try:
                try:fcntl.flock(coordinator,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:return
                # Available-memory readings already include resident pages.
                # Keep only the unfulfilled allowance, not the same RAM twice.
                memory=max(0,self.allocation['request']['memory_gib']-resident)
                while len(tokens)>wanted:os.close(tokens.pop())
                raw=json.dumps(dict(memory_gib=memory,resident_gib=resident,cpu_debt=max(0,wanted-len(tokens)))).encode()
                os.pwrite(tokens[0],raw,0);os.ftruncate(tokens[0],len(raw))
                from resource_workload import observed
                observed(max(len(tokens),wanted),resident,max(self.rates,default=0))
            finally:os.close(coordinator)
        except (OSError,ValueError,KeyError,IndexError):
            return  # Missing telemetry never releases more capacity.
