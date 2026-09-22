"""Resident read-only app dashboard with an optional one-shot safe-copy worker."""
import base64
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer

from dashboard import Catalog, make_handler
from ui.app import HTML
from autonomous_queue import Queue
from control_service import Controls, handler as control_handler


def visible_gpus():
    names=[]
    if shutil.which('nvidia-smi'):
        try:
            result=subprocess.run(['nvidia-smi','--query-gpu=name,uuid','--format=csv,noheader'],
                                  capture_output=True,text=True,timeout=5,check=True)
            names.extend(result.stdout.strip().splitlines())
        except (OSError,subprocess.SubprocessError):pass
    for node in sorted(Path('/dev/dri').glob('renderD*')):
        vendor=Path('/sys/class/drm')/node.name/'device/vendor'
        try:
            label={'0x1002':'AMD','0x8086':'Intel'}.get(vendor.read_text().strip(),'DRM')
        except OSError:label='DRM'
        names.append(label+' '+str(node))
    return names


def config(env):
    media=Path(env.get('MUXMENDER_MEDIA_ROOT','/media')).resolve(strict=True)
    output=Path(env.get('MUXMENDER_OUTPUT_ROOT','/output')).resolve(strict=True)
    if not media.is_dir() or not output.is_dir() or media==output or media in output.parents or output in media.parents:
        raise ValueError('Mount separate existing media and output directories')
    bind=env.get('MUXMENDER_BIND','0.0.0.0')
    port=int(env.get('MUXMENDER_PORT','8765'))
    if not 1<=port<=65535:raise ValueError('Invalid dashboard port')
    hosts=tuple(s.strip() for s in env.get('MUXMENDER_ALLOWED_HOSTS','').split(',') if s.strip())
    if any(not re.fullmatch(r'[A-Za-z0-9.-]+:\d{1,5}',s) for s in hosts):
        raise ValueError('Allowed hosts must be explicit hostname:port entries; no wildcards')
    password=''
    if bind not in ('127.0.0.1','localhost') and not hosts:
        raise ValueError('LAN dashboard requires explicit allowed hosts')
    return media,output,bind,port,hosts,password


def is_read_only(path):
    return hasattr(os,'statvfs') and bool(os.statvfs(path).f_flag & os.ST_RDONLY)


def trial_summary(root,catalog):
    result=[]
    for path in sorted(root.glob('auto-*'),reverse=True)[:20]:
        status=catalog.read(path/'status.json')
        decision=catalog.read(path/'selection.json')
        trials=catalog.read(path/'trials.json')
        if not status:continue
        rows=[]
        for t in trials.get('trials',[]):
            samples=t.get('samples',[])
            passed=sum(s.get('quality_pass') is True and s.get('preservation_pass') is True and s.get('decode_pass') is True for s in samples)
            scores=[s['quality']['mean'] for s in samples if 'quality' in s]
            summary=f'{passed}/{len(samples)} samples passed'
            if scores:summary+='; mean VMAF '+', '.join(f'{x:.1f}' for x in scores)
            rows.append(dict(id=t.get('id','unknown'),summary=summary))
        result.append(dict(name=path.name,reason=decision.get('reason',status.get('state','Pending')),candidates=rows))
    return result


def worker_command(env,media,output):
    source_text=env.get('MUXMENDER_SOURCE','').strip()
    if not source_text:return None
    source=(media/source_text).resolve(strict=True)
    if not source.is_file() or not source.is_relative_to(media):
        raise ValueError('Source must be a file inside the mounted media directory')
    if not is_read_only(media):raise ValueError('Conversion requires a read-only media mount')
    codecs=env.get('MUXMENDER_PLAYBACK_CODECS','').split(',')
    codecs=[c.strip() for c in codecs if c.strip()]
    if not codecs or any(c not in ('hevc','av1') for c in codecs):
        raise ValueError('Declare tested playback codecs: hevc,av1')
    command=[sys.executable,'-B','-m','auto_optimize',str(source),'--output-dir',str(output),
             '--hardware','auto','--playback-verified-codecs',*codecs,'--execute']
    if env.get('MUXMENDER_FULL_COPY','false').lower()=='true':command.append('--encode-best')
    if env.get('MUXMENDER_ADAPTIVE','false').lower()=='true':command.append('--adaptive')
    return command


def standalone_wait_reason(catalog):
    active=[j for j in catalog.snapshot() if j.get('state')=='running'
            and not str(j.get('directory','')).startswith('ui-requests/')]
    if not active:return False
    names=list(dict.fromkeys(str(j.get('title') or 'standalone test') for j in active))
    return 'Waiting for standalone work reported active: '+', '.join(names[:3])+'. If it was stopped, its saved status may need recovery.'


def main():
    env=os.environ
    media,output,bind,port,hosts,password=config(env)
    catalog=Catalog(output,[output])
    expected='Basic '+base64.b64encode(('muxmender:'+password).encode()).decode()
    authorize=(lambda value:hmac.compare_digest(value,expected)) if password else None
    worker=None
    queue=None
    controls=None
    queue_enabled=env.get('MUXMENDER_QUEUE_ENABLED','false').lower()=='true'
    controls_enabled=env.get('MUXMENDER_CONTROLS_ENABLED','false').lower()=='true'
    if controls_enabled and (queue_enabled or env.get('MUXMENDER_SOURCE','').strip()):
        raise ValueError('UI controls require legacy queue disabled and MUXMENDER_SOURCE cleared')
    if queue_enabled and env.get('MUXMENDER_SOURCE','').strip():
        raise ValueError('Clear MUXMENDER_SOURCE before enabling the autonomous queue')
    worker_state='Idle; configure a source and a new job ID to run a trial'
    def snapshot():
        state=worker_state if worker is None else 'Running' if worker.poll() is None else f'Finished (exit {worker.returncode}); originals retained'
        active=[j for j in catalog.snapshot() if j.get('state')=='running']
        if active:
            state='Running: '+'; '.join(j['title'] for j in active)
        return dict(media_root=str(media),output_root=str(output),media_read_only=is_read_only(media),
                    free_bytes=shutil.disk_usage(output).free,gpus=visible_gpus(),worker=state,
                    queue=queue.snapshot() if queue is not None else None,
                    trials=trial_summary(output,catalog))
    server=ThreadingHTTPServer((bind,port),make_handler(catalog,page=HTML,allowed_hosts=hosts,
                                                     authorize=authorize,app_provider=snapshot))
    try:
        if controls_enabled:
            codecs=[c.strip() for c in env.get('MUXMENDER_PLAYBACK_CODECS','').split(',') if c.strip()]
            controls=Controls(media,output,is_read_only,codecs,
                              busy=lambda:standalone_wait_reason(catalog),
                              replacement_root=media)
            server.RequestHandlerClass=control_handler(server.RequestHandlerClass,controls)
            controls.start()
        if queue_enabled:
            codecs=[c.strip() for c in env.get('MUXMENDER_PLAYBACK_CODECS','').split(',') if c.strip()]
            queue=Queue(media,output,codecs,is_read_only,
                        busy=lambda:any(j.get('state')=='running' for j in catalog.snapshot()))
            queue.start()
        command=worker_command(env,media,output)
        if command:
            job_id=env.get('MUXMENDER_JOB_ID','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',job_id):raise ValueError('Set a unique MUXMENDER_JOB_ID')
            marker=output/('app-request-'+job_id+'.json')
            try:
                with marker.open('x',encoding='utf-8') as f:json.dump(dict(source=str(command[4]),started=True),f)
            except FileExistsError:
                worker_state='Job ID already submitted; not automatically rerunning it'
            else:
                worker=subprocess.Popen(command)
        def stop(*unused):
            if controls is not None:controls.stop_event.set()
            if queue is not None:queue.stop_event.set()
            if worker is not None and worker.poll() is None:
                worker.send_signal(signal.SIGINT)
            threading.Thread(target=server.shutdown,daemon=True).start()
        signal.signal(signal.SIGTERM,stop)
        signal.signal(signal.SIGINT,stop)
        print(f'MuxMender dashboard listening on port {port}; trusted-network access without login',flush=True)
        server.serve_forever()
    finally:
        if controls is not None:controls.stop()
        if queue is not None:queue.stop()
        server.server_close()
        if worker is not None and worker.poll() is None:
            worker.send_signal(signal.SIGINT)
            try:worker.wait(timeout=15)
            except subprocess.TimeoutExpired:
                from muxmender import stop_process_tree
                stop_process_tree(worker)


if __name__=='__main__':main()
