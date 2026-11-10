"""Bounded raw-frame pipes sharing one resource admission and watchdog.

Producers are direct, owned children. They start only after group admission,
pause with the consumer, and are always reaped on cancellation or failure.
No raw-frame video is written to disk.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from validation_resources import validation_limited


@validation_limited
def stage(command, seconds, *, producer_commands, producer_env, env, directory,
          expected_frames, guard, timeout=120, stall=30, observe=None, measurement=None):
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Raw-frame streaming is supported only on Linux')
    if len(producer_commands)!=2 or type(expected_frames) is not int or expected_frames<=0:
        raise ValueError('Streaming comparison requires two complete frame inputs')
    tokens=['pipe:input-0','pipe:input-1']
    if any(command.count(token)!=1 for token in tokens):
        raise ValueError('Invalid streaming input bindings')
    if any(not c or c[-1]!='pipe:1' for c in producer_commands):
        raise ValueError('Streaming producers must write only their output pipe')
    from cooperative_pause import configured_lease,launch_owned
    lease=configured_lease(command,env)
    if lease and any(configured_lease(c,producer_env)!=lease for c in producer_commands):
        raise ValueError('Streaming pipeline must share its pause lease')
    from native_pipeline import stage as native_stage
    from muxmender import stop_process_tree
    directory=Path(directory)
    children=[];handles=[]
    def check():
        guard()
        for child in children:
            code=child.poll()
            if code not in (None,0):raise RuntimeError('Native comparison renderer failed')
    try:
        check()
        started=time.monotonic()
        for index,producer in enumerate(producer_commands):
            check()
            progress=directory/f'render-{index}-progress.txt'
            error=directory/f'render-{index}.stderr'
            if producer.count(str(progress))!=1:
                raise ValueError('Renderer progress must use its owned stage path')
            if progress.exists() or progress.is_symlink():
                raise ValueError('Renderer progress path already exists')
            handle=error.open('x');handles.append(handle)
            launch=launch_owned if lease else subprocess.Popen
            children.append(launch(producer,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                                   stderr=handle,env=producer_env))
        bound=list(command)
        for token,child in zip(tokens,children):
            bound[bound.index(token)]='pipe:'+str(child.stdout.fileno())
        setup_seconds=time.monotonic()-started
        timing={}
        # This wrapper owns admission for the whole group. The inner stage
        # retains watchdog, cancellation, telemetry and cooperative suspension.
        result=native_stage.__wrapped__(bound,seconds,timeout=timeout,stall=stall,
            guard=check,observe=observe,expected_frames=expected_frames,cwd=directory,env=env,
            pass_fds=tuple(child.stdout.fileno() for child in children),
            measurement=timing,companions=tuple(children))
        draining=time.monotonic()
        for index,child in enumerate(children):
            check()
            if child.wait(timeout=10):raise RuntimeError('Native comparison renderer failed')
            handles[index].flush()
            if (directory/f'render-{index}.stderr').stat().st_size:
                raise RuntimeError('Native comparison renderer reported decoding errors')
            progress=(directory/f'render-{index}-progress.txt').read_text()
            frames=re.findall(r'^frame=\s*(\d+)\s*$',progress,re.M)
            if not frames or int(frames[-1])!=expected_frames or 'progress=end' not in progress:
                raise ValueError('Native comparison renderer did not cover every frame')
        if measurement is not None:
            measurement.update(timing)
            measurement['execution_seconds']+=setup_seconds+time.monotonic()-draining
        return result
    finally:
        for child in children:
            if child.stdout:child.stdout.close()
            if child.poll() is None:stop_process_tree(child)
        for child in children:
            if child.poll() is None:child.kill()
            child.wait(timeout=10)
        for handle in handles:handle.close()
