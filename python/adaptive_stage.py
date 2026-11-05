"""Shared adaptive CPU/GPU stage admission; media commands and checks stay intact."""
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import time
import uuid


def _open(path):return os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)


def claim_cpu(root,budget,wanted,solo=False,*,data=None,memory_gib=0):
    """Atomic cross-engine budget; tokens are advisory demand, not OS CPU quotas."""
    import fcntl
    path=Path(root)/'cpu-budget';path.mkdir(exist_ok=True)
    if path.is_symlink():raise ValueError('Linked resource budget')
    coordinator=_open(path/'admission.lock');free=[];held=0;reserved_memory=0
    try:
        fcntl.flock(coordinator,fcntl.LOCK_EX)
        for n in range(64):
            fd=_open(path/('worker-'+str(n)+'.lock'))
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                held+=1
                try:
                    record=json.loads(os.pread(fd,256,0) or b'{}')
                    if not isinstance(record,dict):return None
                    memory=record.get('memory_gib',0)
                    if type(memory) not in (int,float) or not math.isfinite(memory) or memory<0:return None
                    debt=record.get('cpu_debt',0)
                    if type(debt) is not int or not 0<=debt<=32:return None
                    held+=debt;reserved_memory+=memory
                except (OSError,ValueError,TypeError):return None
                finally:os.close(fd)
            else:
                os.ftruncate(fd,0);free.append(fd)
        cost=min(wanted,budget) if solo and held==0 else wanted
        if budget-held<cost:return None
        if data is not None:
            from adaptive_resources import memory_room
            if not memory_room(data,memory_gib+reserved_memory):return None
        result=free[:cost]
        if result:os.write(result[0],json.dumps(dict(memory_gib=memory_gib)).encode())
        free=free[cost:];return result
    finally:
        for fd in free:os.close(fd)
        os.close(coordinator)


def _gpu_data(data,engine):
    # Do not serialize the dedicated encoder behind an otherwise idle compute
    # stage. Shared CUDA, CPU, VRAM, temperature and pressure remain relevant.
    result=dict(data)
    for key in ('gpu_encode_percent','gpu_decode_percent','gpu_compute_percent'):
        if key!='gpu_'+engine+'_percent':result[key]=0 if key in result else result.get(key)
    return result


@contextmanager
def slot(command,guard,*,pool,env,estimated_duration=None,timeout=None):
    import fcntl
    from adaptive_resources import cpu_room,pressure_ok,memory_room,finite
    from resource_workload import demand,safe_root
    from validation_resources import AdmissionBudget,reader_threads,ticket_rank,validation_rank
    from job_tracking import progress,current_workflow_stage
    from gpu_admission import family,load,save,decide,observe
    from cooperative_pause import configured_lease,lease_reason
    root=Path(env['MUXMENDER_VALIDATION_LOCK_ROOT']);safe_root(root)
    request=demand(command,env);quality=request['kind'] in ('cpu-quality','mixed-quality')
    engine='encode' if request['gpu_encode'] else 'compute' if request['gpu_compute'] else 'decode' if request['gpu_decode'] else None
    path=root/('gpu-'+engine if engine else 'cpu-adaptive');path.mkdir(exist_ok=True)
    if path.is_symlink():raise ValueError('Linked resource pool')
    coordinator=_open(path/'admission.lock');ticket=path/('wait-'+str(time.monotonic_ns()).zfill(20)+'-'+uuid.uuid4().hex+'.lock')
    lease=_open(ticket);fcntl.flock(lease,fcntl.LOCK_EX)
    os.write(lease,json.dumps(dict(started=time.monotonic(),seconds=estimated_duration,final=current_workflow_stage()=='validate')).encode())
    budget=AdmissionBudget();started=time.monotonic();stage_started=None;slot_fd=None;cpu=[];limit=reader_threads(command);success=False;state=None;key=family(command,estimated_duration)
    pause=configured_lease(command,env)
    from resource_workload import legacy_busy
    try:
        while slot_fd is None:
            guard();data=budget.gpu_sample(include_gpu=bool(engine));room=cpu_room(data)
            # Threads are indivisible; a tiny telemetry fluctuation must not
            # halve an otherwise fitting qualified pool. OS quotas still apply.
            cpu_budget=min(32,max(1,math.ceil(room))) if room is not None else 1
            reason='Waiting for measured CPU and memory headroom'
            ready=room is not None and room>=.25 and pressure_ok(data) and memory_room(data,request['memory_gib'])
            if legacy_busy(root):ready=False;reason='Waiting for existing legacy allocations to finish'
            if pause and lease_reason(pause):ready=False;reason='Yielding resources to other applications'
            if engine:
                needed=('vram_free_gib','gpu_temperature','gpu_encode_percent','gpu_decode_percent','gpu_compute_percent')
                ready=ready and all(finite(data.get(k)) for k in needed)
                if ready and (data['vram_free_gib']<1 or data['gpu_temperature']>=80):ready=False;reason='Waiting for GPU memory or cooling headroom'
                if ready and engine!='compute' and data['gpu_compute_percent']>=95:ready=False;reason='Waiting for shared GPU compute capacity'
            if ready:
                try:fcntl.flock(coordinator,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:pass
                else:
                    try:
                        ranking=ticket_rank if engine else validation_rank
                        own=ranking(ticket,time.monotonic());ahead=False
                        for other in path.glob('wait-*.lock'):
                            if other==ticket:continue
                            fd=_open(other)
                            try:
                                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                                except BlockingIOError:
                                    if ranking(other,time.monotonic())<own:ahead=True
                                else:other.unlink(missing_ok=True)
                            finally:os.close(fd)
                        capacity=1
                        state=load(path/'adaptive.json') if engine else None
                        if engine:
                            active=state.setdefault('active',{})
                            for name in list(active):
                                if name not in ('heavy-reader.lock','heavy-reader-2.lock'):active.pop(name,None);continue
                                fd=_open(path/name)
                                try:
                                    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                                    except BlockingIOError:pass
                                    else:active.pop(name,None)
                                finally:os.close(fd)
                            maximum=1 if env.get('MUXMENDER_GPU_STAGE_MAX')=='1' else 2
                            capacity=decide(state,_gpu_data(data,engine),key,time.time(),time.monotonic()-started,maximum)
                            save(path/'adaptive.json',state)
                        else:capacity=2 if room>=6 else 1
                        if not ahead:
                            for name in ('heavy-reader.lock','heavy-reader-2.lock')[:capacity]:
                                fd=_open(path/name)
                                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                                except BlockingIOError:os.close(fd);continue
                                wanted=request['cpu_cost']
                                selected=limit
                                if quality and wanted>cpu_budget:
                                    selected=2 if limit>=2 else 1;wanted=max(1,wanted-max(0,limit-selected))
                                tokens=claim_cpu(root,cpu_budget,wanted,solo=True,data=data,memory_gib=request['memory_gib'])
                                if tokens is None:os.close(fd);continue
                                cpu=tokens;slot_fd=fd;limit=selected
                                if len(tokens)<wanted:limit=1
                                ticket.unlink(missing_ok=True);stage_started=time.monotonic()
                                if state is not None:
                                    mixed=any(v.get('family')!=key for v in state['active'].values())
                                    for record in state['active'].values():
                                        record.update(overlap=True,overlap_started=stage_started)
                                        if mixed:record['mixed']=True
                                    state['active'][name]=dict(family=key,overlap=bool(state['active']),mixed=mixed,overlap_seconds=0,overlap_started=stage_started if state['active'] else None)
                                    save(path/'adaptive.json',state)
                                break
                    finally:fcntl.flock(coordinator,fcntl.LOCK_UN)
            if slot_fd is None:
                if timeout is not None and time.monotonic()-started>=timeout:raise TimeoutError('Timed out waiting for adaptive resource allocation')
                progress('Waiting for adaptive '+(engine or 'CPU')+' resources',stage_percent=None,stage_eta=None,
                    detail=reason+'; existing work keeps its allocation. Waiting '+str(int(time.monotonic()-started))+'s.')
                time.sleep(1)
        from live_allocation import scope
        with scope(root,cpu,request):yield limit
        success=True
    finally:
        if state is not None and slot_fd is not None:
            try:
                fcntl.flock(coordinator,fcntl.LOCK_EX)
                current=load(path/'adaptive.json');active=current.get('active',{});now=time.monotonic()
                own=active.pop(name,{});elapsed=now-stage_started
                overlap=own.get('overlap_seconds',0)
                if own.get('overlap_started') is not None:overlap+=max(0,now-own['overlap_started'])
                for other in active.values():
                    if other.get('overlap_started') is not None:
                        other['overlap_seconds']=other.get('overlap_seconds',0)+max(0,now-other['overlap_started'])
                        other['overlap_started']=None
                observe(current,own.get('family'),estimated_duration,elapsed,min(1,overlap/elapsed) if elapsed>0 else 0,success,time.time(),mixed=own.get('mixed',False))
                save(path/'adaptive.json',current)
            except (OSError,ValueError,TypeError):pass
            finally:fcntl.flock(coordinator,fcntl.LOCK_UN)
        for fd in cpu:os.close(fd)
        if slot_fd is not None:os.close(slot_fd)
        ticket.unlink(missing_ok=True);os.close(lease);os.close(coordinator)
