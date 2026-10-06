"""Bounded, measured GPU-stage admission. Never changes media or encoder settings."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import os
import threading
from contextlib import contextmanager

_stage=threading.local()


@contextmanager
def stage_context(video):
    previous=getattr(_stage,'video',None)
    _stage.video=video
    try:yield
    finally:_stage.video=previous


def finite(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0


def family(command,seconds,video=None):
    if not finite(seconds) or seconds<=0:return None
    video=video if video is not None else getattr(_stage,'video',None)
    if not isinstance(video,dict) or any(not finite(video.get(k)) or video[k]<=0 for k in ('width','height')):return None
    options=[]
    for i,arg in enumerate(command[:-1]):
        if str(arg) in ('-preset','-cq','-pix_fmt','-vf','-filter:v','-filter_complex','-lavfi') or str(arg).startswith(('-c:v','-codec:v')):
            options.extend((str(arg),str(command[i+1])))
    # Compare similar-length stages with the same codec/filter settings, not
    # different whole files against small trials. Never persist input paths.
    options.append(str(int(math.log2(max(1,seconds)))))
    options.append('frame_reader' if '-show_frames' in command else 'media_stage')
    options.append({key:video.get(key) for key in ('codec_name','width','height','pix_fmt','avg_frame_rate','field_order','color_transfer')})
    options.append(os.environ.get('NVIDIA_VISIBLE_DEVICES','unspecified'))
    return hashlib.sha256(json.dumps(options).encode()).hexdigest()


def headroom(data):
    keys=('gpu_encode_percent','gpu_decode_percent','gpu_compute_percent',
          'vram_free_gib','gpu_temperature','available_gib','host_available_gib',
          'cpu_percent','container_cpu_percent','memory_pressure','io_pressure')
    if any(not finite(data.get(key)) for key in keys):return False,'GPU/resource telemetry unavailable'
    if max(data[k] for k in keys[:3])>=75:return False,'GPU engines busy'
    if data['vram_free_gib']<4:return False,'Insufficient VRAM headroom'
    if data['gpu_temperature']>=75:return False,'GPU cooling headroom needed'
    from resource_governor import cache_assisted_start
    memory=data['host_available_gib']>=12 or cache_assisted_start(data,8)
    if data['available_gib']<6 or not memory:return False,'Insufficient measured RAM headroom'
    if max(data['cpu_percent'],data['container_cpu_percent'])>70:return False,'CPU allocation busy'
    if data['memory_pressure']>=.1 or data['io_pressure']>=5:return False,'Memory/storage pressure'
    return True,'Measured headroom available'


def load(path):
    try:
        if path.is_symlink() or path.stat().st_size>128*1024:return {}
        value=json.loads(path.read_text())
        if not isinstance(value,dict) or value.get('schema')!=1:return {}
        groups=value.get('groups',{});active=value.get('active',{})
        if not isinstance(groups,dict) or len(groups)>16 or not isinstance(active,dict) or len(active)>2:return {}
        if not isinstance(value.get('status',{}),dict):return {}
        for group in groups.values():
            if not isinstance(group,dict) or group.get('mode') not in ('serial','trial','parallel'):return {}
            for field in ('single','paired'):
                rates=group.get(field,[])
                if not isinstance(rates,list) or len(rates)>8 or any(not finite(r) or r<=0 for r in rates):return {}
            for field in ('updated','healthy_since','cooldown','trial_started','gain'):
                if group.get(field) is not None and not finite(group[field]):return {}
        if any(not isinstance(r,dict) or type(r.get('overlap')) is not bool for r in active.values()):return {}
        return value
    except (OSError,ValueError):return {}


def save(path,state):
    # Caller holds the existing cross-process admission coordinator.
    if path.is_symlink():raise ValueError('Linked GPU admission state')
    temporary=path.with_suffix('.tmp')
    if temporary.is_symlink():raise ValueError('Linked GPU admission temporary')
    temporary.write_text(json.dumps(state))
    temporary.replace(path)


def decide(state,data,key,now,waiting,maximum=2,paused=False):
    state.setdefault('schema',1);groups=state.setdefault('groups',{})
    good,reason=headroom(data)
    group=groups.setdefault(key or 'unknown',dict(single=[],paired=[],mode='serial',updated=now))
    group['updated']=now
    for old in sorted(groups,key=lambda k:groups[k].get('updated',0))[:-16]:groups.pop(old,None)
    if not good or paused or maximum<2 or not key:
        group.update(healthy_since=None,mode='serial',paired=[],cooldown=now+60)
        limit=1
        if paused:reason='Yielding GPU to other apps'
        elif maximum<2:reason='User resource profile limits GPU stages to one'
        elif not key:reason='Unknown stage work; serial admission'
    else:
        if group.get('healthy_since') is None:group['healthy_since']=now
        baseline=group.get('single',[])
        mode=group.get('mode','serial')
        if mode in ('trial','parallel'):
            limit=2;reason='Measuring two-stage throughput' if mode=='trial' else 'Two-stage throughput gain verified for this stage family'
        elif len(baseline)>=3 and waiting>=5 and now-group['healthy_since']>=30 and now>=group.get('cooldown',0):
            group.update(mode='trial',paired=[],trial_started=now)
            limit=2;reason='Testing a second GPU stage against measured serial rate'
        else:limit=1;reason='Learning serial rate and sustained headroom before trying two GPU stages'
        if group.get('mode')=='trial' and now-group.get('trial_started',now)>300:
            group.update(mode='serial',paired=[],cooldown=now+600)
            limit=1;reason='Two-stage experiment timed out; serial admission restored'
    state['status']=dict(limit=limit,reason=reason,updated=now,baseline_samples=len(group.get('single',[])),
                         trial_samples=len(group.get('paired',[])),throughput_gain=group.get('gain'),
                         policy='Bounded GPU-stage learning; pressure drains workers, never interrupts publication')
    return limit


def observe(state,key,work,elapsed,overlap,success,now):
    if not key:return
    group=state.get('groups',{}).get(key)
    if not group:return
    if not success:
        group.update(mode='serial',paired=[],cooldown=now+600);return
    if not finite(work) or not finite(elapsed) or work<=0 or elapsed<2:return
    rate=work/elapsed
    fraction=float(overlap) if type(overlap) is bool else overlap
    if not finite(fraction) or fraction>1:return
    # A brief overlap does not represent two-stage throughput. Counting it as
    # fully parallel would falsely double a mostly serial stage's rate.
    if 0<fraction<.8:return
    overlap=fraction>=.8
    if overlap and group.get('mode') not in ('trial','parallel'):return
    field='paired' if overlap else 'single'
    group[field]=(group.get(field,[])+[rate])[-8:]
    if overlap and len(group['paired'])>=3 and len(group.get('single',[]))>=3:
        gain=2*statistics.median(group['paired'])/statistics.median(group['single'])
        group['gain']=gain
        group['mode']='parallel' if gain>=1.10 else 'serial'
        if gain<1.10:group.update(paired=[],cooldown=now+600)


def snapshot(root):
    import time
    state=load(Path(root)/'gpu'/'adaptive.json')
    status=state.get('status',{})
    if status and (not finite(status.get('updated')) or not 0<=time.time()-status['updated']<90):
        return dict(status,reason='Last GPU admission measurement is stale; current limit unconfirmed',stale=True)
    return status
