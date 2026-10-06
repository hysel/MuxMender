"""Cross-process admission for memory-heavy readers, not weaker validation.

The OS releases the lock on process death. Only an explicitly configured shared
work root is used; source folders are never used for lock files.
"""
from contextlib import contextmanager
from functools import wraps
import inspect
import json
import math
import os
import re
from pathlib import Path
import time
import uuid


class AdmissionBudget:
    """Observe sustained headroom before admitting a second reader."""
    def __init__(self):
        from resource_governor import Governor
        self.governor=Governor();self.healthy_since=None;self.checked=-float('inf');self.capacity=1

    def sample(self):
        from resource_governor import validation_capacity
        now=time.monotonic()
        if now-self.checked<5:return self.capacity
        self.checked=now
        try:healthy=validation_capacity(self.governor.sample())==2
        except (OSError,ValueError,TypeError):healthy=False
        if not healthy:self.healthy_since=None
        elif self.healthy_since is None:self.healthy_since=now
        self.capacity=2 if self.healthy_since is not None and now-self.healthy_since>=30 else 1
        return self.capacity

    def gpu_sample(self):
        now=time.monotonic()
        if not hasattr(self,'gpu_checked') or now-self.gpu_checked>=5:
            try:
                # CPU percentages require two counters separated by an interval.
                # A fresh GPU stage otherwise always publishes incomplete data.
                if not hasattr(self,'gpu_checked'):
                    self.governor.sample(include_gpu=False)
                    time.sleep(.25)
                self.gpu_data=self.governor.sample()
            except (OSError,ValueError,TypeError):self.gpu_data={}
            self.gpu_checked=now
        return self.gpu_data


def _open_lock(path):
    return os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)


def heavy_reader(command):
    return '-show_frames' in command or any(
        word in str(arg) for arg in command for word in ('libvmaf','libplacebo','tonemap'))


def resource_pool(command,env=None):
    """Classify explicit command options, not filenames or GPU model names."""
    filters=[str(command[i+1]) for i,arg in enumerate(command[:-1])
             if str(arg) in ('-lavfi','-filter_complex','-vf','-filter:v')]
    gpu_filter=any(word in graph for graph in filters for word in ('libplacebo','libvmaf_cuda','scale_cuda','scale_npp'))
    gpu_codec=any((str(arg) in ('-c:v','-codec:v','-vcodec') or
                   str(arg).startswith(('-c:v:','-codec:v:'))) and
                  str(command[i+1]).endswith('_nvenc') for i,arg in enumerate(command[:-1]))
    native_gpu_reader=(env or {}).get('MUXMENDER_RESEARCH_CUDA_READER')=='1' and '-show_frames' in command
    if gpu_filter or gpu_codec or native_gpu_reader:return 'gpu'
    return 'validation' if heavy_reader(command) else None


def ticket_rank(path,now):
    """Short GPU trials may pass new long work, never a 30-second waiter."""
    sequence=int(path.name.split('-')[1])
    try:
        with path.open('rb') as stream:
            record=json.loads(stream.read(4096))
        age=now-record['started']
        seconds=record.get('seconds')
        if not math.isfinite(age) or age<0:raise ValueError('Invalid ticket age')
        short=type(seconds) in (int,float) and math.isfinite(seconds) and 0<seconds<=60
        return (-1 if age>=30 else (0 if short else 1),sequence)
    except (OSError,ValueError,TypeError,KeyError):
        return (-1,sequence)  # Preserve FIFO for legacy/unknown evidence.


def validation_rank(path,now):
    """Final checks may pass fresh trials; aged or unknown work stays FIFO."""
    sequence=int(path.name.split('-')[1])
    try:
        with path.open('rb') as stream:record=json.loads(stream.read(4096))
        age=now-record['started']
        if not math.isfinite(age) or age<0:raise ValueError('Invalid age')
        return (-1 if age>=30 else 0 if record.get('final') else 1,sequence)
    except (OSError,ValueError,TypeError,KeyError):return (-1,sequence)


def reader_threads(command):
    values=[]
    for i,arg in enumerate(command[:-1]):
        if arg in ('-threads','-threads:v') and str(command[i+1]).isdigit():values.append(int(command[i+1]))
    for i,arg in enumerate(command[:-1]):
        if arg in ('-filter_complex','-lavfi','-vf','-filter:v'):
            values.extend(int(x) for x in re.findall(r'(?<![\w])n_threads=(\d+)',str(command[i+1])))
    return max(2,min(4,max(values,default=2)))


def bounded_reader(command,limit):
    """Reduce explicit concurrency only; preserve fields, filters and thresholds."""
    if type(limit) is not int or limit not in (2,4):return command
    result=list(command)
    for i,arg in enumerate(result[:-1]):
        if arg in ('-threads','-threads:v') and str(result[i+1]).isdigit():
            result[i+1]=str(min(int(result[i+1]),limit))
    for i,arg in enumerate(result[:-1]):
        if arg in ('-filter_complex','-lavfi','-vf','-filter:v'):
            result[i+1]=re.sub(r'(?<![\w])n_threads=(\d+)',lambda m:'n_threads='+str(min(int(m.group(1)),limit)),str(result[i+1]))
    return result


def live_waiters(path):
    """Read OS leases, not stale filenames. Never signal or change a worker."""
    import fcntl
    count=0
    for ticket in path.glob('wait-*.lock'):
        try:fd=_open_lock(ticket)
        except OSError:continue
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:count+=1
        finally:os.close(fd)
    return count


@contextmanager
def validation_slot(command,guard=lambda:None,timeout=None,*,pool='validation',env=None,estimated_duration=None):
    if pool not in ('validation','gpu','publication'):raise ValueError('Unknown resource pool')
    root=(os.environ if env is None else env).get('MUXMENDER_VALIDATION_LOCK_ROOT')
    if not root or os.name!='posix' or (pool=='validation' and not heavy_reader(command)):
        yield
        return
    import fcntl
    from job_tracking import progress
    path=Path(root)
    if pool!='validation':path=path/pool
    if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('Unsafe validation lock root')
    path.mkdir(parents=True,exist_ok=True)
    # The coordinator serializes ticket creation and admission, not validation.
    # Ticket leases use OS locks: dead processes cannot strand the queue.
    pause_lease=None
    # Do not start GPU work during an external sharing request. Existing
    # in-flight suspension in native_pipeline remains unchanged.
    if pool=='gpu':
        from cooperative_pause import configured_lease
        pause_lease=configured_lease(command,env)
    coordinator=_open_lock(path/'admission.lock')
    ticket=None;lease=None;fd=None;slot_name=None;gpu_started=None;succeeded=False;cpu_tokens=[];thread_limit=None
    started=time.monotonic();waiting=False
    budget=AdmissionBudget()
    try:
        while True:
            guard()
            capacity=1 if pool in ('publication','gpu') else budget.sample()
            paused=False
            if pause_lease:
                from cooperative_pause import lease_reason
                paused=bool(lease_reason(pause_lease))
            from job_tracking import current_workflow_stage
            backlogged=(pool=='gpu' and current_workflow_stage()!='validate' and type(estimated_duration) in (int,float) and
                        0<estimated_duration<=60 and time.monotonic()-started<30 and
                        live_waiters(Path(root))>=2)
            paused=paused or backlogged
            gpu_state=None
            gpu_telemetry=budget.gpu_sample() if pool=='gpu' else None
            try:
                fcntl.flock(coordinator,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                try:
                    gpu_state=None
                    if pool=='gpu':
                        from gpu_admission import load,save,decide,family
                        gpu_state=load(path/'adaptive.json')
                        active=gpu_state.setdefault('active',{})
                        for name in list(active):
                            if name not in ('heavy-reader.lock','heavy-reader-2.lock'):
                                active.pop(name,None);continue
                            probe=_open_lock(path/name)
                            try:
                                try:fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
                                except BlockingIOError:pass
                                else:active.pop(name,None)
                            finally:os.close(probe)
                        key=family(command,estimated_duration)
                        maximum=1 if (os.environ if env is None else env).get('MUXMENDER_GPU_STAGE_MAX')=='1' else 2
                        capacity=decide(gpu_state,gpu_telemetry,key,time.time(),time.monotonic()-started,maximum,paused)
                        if any(a.get('family')!=key for a in active.values()):
                            capacity=1
                            gpu_state['status'].update(limit=1,reason='Waiting for a comparable GPU-stage family')
                        save(path/'adaptive.json',gpu_state)
                    if ticket is None:
                        # Monotonically increasing order even if wall time changes.
                        existing=list(path.glob('wait-*.lock'))
                        sequence=max((int(p.name.split('-')[1]) for p in existing),default=0)+1
                        ticket=path/f'wait-{sequence:020d}-{uuid.uuid4().hex}.lock'
                        lease=_open_lock(ticket)
                        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        if pool=='gpu':
                            os.write(lease,json.dumps(dict(started=time.monotonic(),seconds=estimated_duration)).encode())
                        elif pool=='validation':
                            from job_tracking import current_workflow_stage
                            os.write(lease,json.dumps(dict(started=time.monotonic(),final=current_workflow_stage()=='validate')).encode())
                    ahead=False
                    rank=(ticket_rank(ticket,time.monotonic()) if pool=='gpu' else
                          validation_rank(ticket,time.monotonic()) if pool=='validation' else None)
                    for other in sorted(path.glob('wait-*.lock')):
                        if other==ticket:continue
                        probe=_open_lock(other)
                        try:
                            try:fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
                            except BlockingIOError:
                                if ((pool=='gpu' and ticket_rank(other,time.monotonic())<rank) or
                                    (pool=='validation' and validation_rank(other,time.monotonic())<rank) or
                                    (pool=='publication' and other.name<ticket.name)):
                                    ahead=True
                            else:other.unlink()  # Abandoned lease only; never a media file.
                        finally:os.close(probe)
                    if not ahead and not paused:
                        # Keep the legacy first lock for compatibility with older workers.
                        reserve=None
                        try:
                            if capacity==1:
                                # A reader in slot two still counts after pressure
                                # rises; do not refill slot one until it drains.
                                reserve=_open_lock(path/'heavy-reader-2.lock')
                                fcntl.flock(reserve,fcntl.LOCK_EX|fcntl.LOCK_NB)
                            for name in ('heavy-reader.lock','heavy-reader-2.lock')[:capacity]:
                                candidate=_open_lock(path/name)
                                try:fcntl.flock(candidate,fcntl.LOCK_EX|fcntl.LOCK_NB)
                                except BlockingIOError:os.close(candidate)
                                else:
                                    if pool=='validation':
                                        # Primary reader/scorer workers: four with one stage,
                                        # eight only after sustained two-stage headroom.
                                        token_budget=4 if capacity==1 else 8
                                        tokens=[]
                                        try:
                                            for number in range(token_budget):
                                                token_fd=_open_lock(path/f'cpu-token-{number}.lock')
                                                try:fcntl.flock(token_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                                                except BlockingIOError:os.close(token_fd)
                                                else:tokens.append(token_fd)
                                        except BaseException:
                                            for token_fd in tokens:os.close(token_fd)
                                            os.close(candidate)
                                            raise
                                        wanted=reader_threads(command)
                                        allocation=4 if wanted==4 and len(tokens)>=4 else 2
                                        # Older workers hold a reader slot but no CPU tokens.
                                        # Treat their unknown allocation as the entire budget.
                                        legacy_busy=False
                                        if len(tokens)==token_budget and reserve is None:
                                            other_name='heavy-reader-2.lock' if name=='heavy-reader.lock' else 'heavy-reader.lock'
                                            probe=_open_lock(path/other_name)
                                            try:
                                                try:fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
                                                except BlockingIOError:legacy_busy=True
                                            finally:os.close(probe)
                                        if len(tokens)<allocation or legacy_busy:
                                            for token_fd in tokens:os.close(token_fd)
                                            os.close(candidate);continue
                                        cpu_tokens=tokens[:allocation]
                                        for token_fd in tokens[allocation:]:os.close(token_fd)
                                        thread_limit=allocation
                                    fd=candidate;slot_name=name;ticket.unlink()
                                    if gpu_state is not None:
                                        gpu_started=time.monotonic()
                                        for record in gpu_state['active'].values():
                                            record.update(overlap=True,overlap_started=gpu_started)
                                        gpu_state['active'][name]=dict(family=key,overlap=bool(gpu_state['active']),
                                            overlap_seconds=0,overlap_started=gpu_started if gpu_state['active'] else None)
                                        save(path/'adaptive.json',gpu_state)
                                    break
                        except BlockingIOError:pass
                        finally:
                            if reserve is not None:os.close(reserve)
                finally:fcntl.flock(coordinator,fcntl.LOCK_UN)
            if fd is not None:break
            waiting=True
            elapsed=time.monotonic()-started
            progress('Waiting for '+pool+' resources',stage_percent=None,stage_eta=None,
                     detail=f'Waiting {int(elapsed)} seconds in fair {pool} order; up to {capacity} stages allowed; execution has not started'+
                            ('; allowing validation backlog to drain' if backlogged else '; yielding GPU to other applications' if paused else '')+
                            ('; '+gpu_state.get('status',{}).get('reason','') if pool=='gpu' and gpu_state else ''))
            if timeout is not None and elapsed>=timeout:
                raise TimeoutError('Timed out waiting for '+pool+' resources; retry when the server is less busy')
            time.sleep(1)
        if waiting:progress(pool.capitalize()+' resources acquired',detail='Continuing the same checks')
        yield thread_limit
        succeeded=True
    finally:
        if pool=='gpu' and gpu_started is not None:
            # Completion records are serialized with admission; worker death
            # leaves no held OS slot and its stale record is reclaimed next time.
            fcntl.flock(coordinator,fcntl.LOCK_EX)
            try:
                from gpu_admission import load,save,observe
                state=load(path/'adaptive.json')
                record=state.setdefault('active',{}).pop(slot_name,{})
                ended=time.monotonic();elapsed=ended-gpu_started
                overlap=record.get('overlap_seconds',0)
                if record.get('overlap_started') is not None:overlap+=max(0,ended-record['overlap_started'])
                for other in state['active'].values():
                    if other.get('overlap_started') is not None:
                        other['overlap_seconds']=other.get('overlap_seconds',0)+max(0,ended-other['overlap_started'])
                        other['overlap_started']=None
                observe(state,record.get('family'),estimated_duration,elapsed,
                        min(1,overlap/elapsed) if elapsed>0 else 0,succeeded,time.time())
                save(path/'adaptive.json',state)
            except (OSError,ValueError,TypeError):
                # Learning is optional evidence. Never strand an OS slot or
                # replace the original processing/cancellation exception.
                pass
            finally:fcntl.flock(coordinator,fcntl.LOCK_UN)
        if fd is not None:os.close(fd)
        for token_fd in cpu_tokens:os.close(token_fd)
        if lease is not None:
            try:fcntl.flock(coordinator,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:pass  # Next admission reclaims the closed lease.
            else:
                try:ticket.unlink(missing_ok=True)
                finally:fcntl.flock(coordinator,fcntl.LOCK_UN)
            os.close(lease)
        os.close(coordinator)


def validation_limited(function):
    signature=inspect.signature(function)
    @wraps(function)
    def wrapped(*args,**kwargs):
        values=signature.bind(*args,**kwargs).arguments
        pool=resource_pool(values['command'],values.get('env'))
        if pool is None:return function(*args,**kwargs)
        from job_tracking import measured_operation,current_phase,progress
        original_phase=current_phase()
        # The wrapped timeout limits actual processing, not time queued behind
        # another reader. The guard still permits cancellation while waiting.
        options={} if pool=='validation' else dict(pool=pool,env=values.get('env'),
            estimated_duration=values.get('seconds',values.get('duration')))
        with measured_operation('validation_wait' if pool=='validation' else 'gpu_wait'):
            with validation_slot(values['command'],values.get('guard') or (lambda:None),**options) as limit:
                if original_phase:progress(original_phase,detail='Resources acquired; processing'+
                    (f'; shared validation allocation: {limit} threads' if type(limit) is int else ''))
                kind=('frame_validation' if '-show_frames' in values['command'] else
                      'quality_measurement' if heavy_reader(values['command']) else 'encoding')
                with measured_operation(kind):
                    if pool=='validation' and type(limit) is int:
                        bound=signature.bind(*args,**kwargs)
                        bound.arguments['command']=bounded_reader(values['command'],limit)
                        return function(*bound.args,**bound.kwargs)
                    return function(*args,**kwargs)
    return wrapped


def publication_limited(function):
    """Bound final copy/hash I/O without moving publication checks outside the lock."""
    signature=inspect.signature(function)
    @wraps(function)
    def wrapped(*args,**kwargs):
        values=signature.bind(*args,**kwargs).arguments
        stopped=values.get('stopped',lambda:False)
        def guard():
            if stopped():raise InterruptedError('Publication cancelled before replacement')
        from job_tracking import measured_operation
        with measured_operation('publication_wait'):
            with validation_slot([],guard,pool='publication'):
                guard()
                with measured_operation('publication'):return function(*args,**kwargs)
    return wrapped
