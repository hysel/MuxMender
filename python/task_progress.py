"""Bounded, measured telemetry for non-encoding work."""
import hashlib
import math
import re
import subprocess
import time
from job_tracking import progress


def digest(path, guard=lambda:None):
    total=path.stat().st_size;done=0;last=0;started=time.monotonic()
    label='Verifying file checksum: '+path.name
    progress(label,detail='Reading file bytes',unit='bytes')
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):
            guard();value.update(block);done+=len(block)
            now=time.monotonic()
            if now-last>=2:
                progress(label,stage_percent=100*done/total if total else None,
                         detail=f'{done/1e9:.2f} of {total/1e9:.2f} GB checked',
                         stage_eta=(total-done)*(now-started)/done if done else None)
                last=now
    progress(label,stage_percent=100,stage_eta=0,detail='Checksum read complete')
    return value.hexdigest()


def probe_status(path, duration, start=0):
    """Read a bounded tail; never load full-episode evidence into memory."""
    size=path.stat().st_size
    with path.open('rb') as stream:
        stream.seek(max(0,size-16384));lines=stream.read().decode('utf-8',errors='replace').splitlines()
    times=[]
    for line in lines[:-1]:  # Last line may still be in flight.
        # ffprobe JSON frame evidence (HDR) uses quoted key/value pairs.
        match=re.search(r'"(?:best_effort_timestamp_time|pts_time)"\s*:\s*"([^"\r\n]+)"',line)
        if match:
            try:
                number=float(match[1])-start
                if math.isfinite(number):times.append(number)
            except ValueError:pass
        for item in line.split('|'):
            key,_,value=item.partition('=')
            if key in ('best_effort_timestamp_time','pts_time'):
                try:
                    number=float(value)-start
                    if math.isfinite(number):times.append(number)
                except ValueError:pass
    position=max(times,default=0)
    percent=min(99.9,max(0,100*position/duration)) if times and duration and math.isfinite(duration) and duration>0 else None
    return percent,f'{position:.1f} seconds inspected · {size/1e6:.1f} MB of validation evidence'


def run_probe(command,path,label,timeout,guard,duration=None,start=0):
    progress(label,detail='Starting validation reader')
    started=time.monotonic()
    with path.open('x',encoding='utf-8') as output, path.with_suffix(path.suffix+'.stderr').open('x') as errors:
        child=subprocess.Popen(command,stdout=output,stderr=errors,text=True)
        try:
            while True:
                guard()
                percent,detail=probe_status(path,duration,start)
                elapsed=time.monotonic()-started
                eta=elapsed*(100-percent)/percent if percent is not None and 0<percent<100 and elapsed>=5 else None
                progress(label,stage_percent=percent,stage_eta=eta,detail=detail)
                remaining=timeout-(time.monotonic()-started)
                if remaining<=0:raise subprocess.TimeoutExpired(command,timeout)
                try:
                    code=child.wait(timeout=min(2,remaining));break
                except subprocess.TimeoutExpired:pass
            if code:raise subprocess.CalledProcessError(code,command)
        except BaseException:
            child.kill();child.wait();raise
    progress(label,stage_percent=100,stage_eta=0,detail='Evidence collection complete; validation continues')
