"""Bounded, measured telemetry for non-encoding work."""
import hashlib
import math
import re
import subprocess
import time
from job_tracking import progress


class ProcessingTimeout(subprocess.TimeoutExpired):
    """Preserve the subprocess timeout contract while providing a useful reason."""
    def __init__(self, command, timeout, label, detail):
        super().__init__(command, timeout)
        self.label=label
        self.detail=detail

    def __str__(self):
        return (f'{self.label}: reached the configured {self.timeout/60:g}-minute processing limit. '
                f'{self.detail}. Increase Processing time limit per stage when submitting a retry; '
                'the original was not approved for replacement.')


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


from validation_resources import validation_limited


@validation_limited
def run_probe(command,path,label,timeout,guard,duration=None,start=0,env=None):
    from cooperative_pause import configured_lease, OwnedStagePause, launch_owned
    from job_tracking import measured_operation
    lease=configured_lease(command,env)
    progress(label,detail='Starting validation reader')
    started=time.monotonic()
    with path.open('x',encoding='utf-8') as output, path.with_suffix(path.suffix+'.stderr').open('x') as errors:
        launch=launch_owned if lease else subprocess.Popen
        options={} if env is None else dict(env=env)
        child=launch(command,stdout=output,stderr=errors,text=True,**options)
        pause=OwnedStagePause(child,lease) if lease else None
        paused_seconds=0
        pause_measurement=None
        try:
            while True:
                guard()
                if pause:
                    paused=pause.update()
                    spent=pause.elapsed()
                    started+=spent-paused_seconds
                    paused_seconds=spent
                    if paused:
                        if pause_measurement is None:
                            pause_measurement=measured_operation('gpu_pause')
                            pause_measurement.__enter__()
                        progress(label,stage_percent=None,stage_eta=None,
                                 detail=f'Paused: {pause.reason}. GPU memory remains allocated.')
                        time.sleep(.2)
                        continue
                    if pause_measurement is not None:
                        pause_measurement.__exit__(None,None,None)
                        pause_measurement=None
                percent,detail=probe_status(path,duration,start)
                elapsed=time.monotonic()-started
                eta=elapsed*(100-percent)/percent if percent is not None and 0<percent<100 and elapsed>=5 else None
                progress(label,stage_percent=percent,stage_eta=eta,detail=detail)
                remaining=timeout-(time.monotonic()-started)
                if remaining<=0:
                    raise ProcessingTimeout(command,timeout,label,detail)
                try:
                    code=child.wait(timeout=min(2,remaining));break
                except subprocess.TimeoutExpired:pass
            if code:raise subprocess.CalledProcessError(code,command)
        except BaseException:
            child.kill();child.wait();raise
        finally:
            if pause_measurement is not None:pause_measurement.__exit__(None,None,None)
    progress(label,stage_percent=100,stage_eta=0,detail='Evidence collection complete; validation continues')
