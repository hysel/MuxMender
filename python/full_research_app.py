"""Isolated serial research frontend. No queue controls or replacement service."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer

from app_service import config, is_read_only
from dashboard import Catalog, make_handler
from ui.app import HTML
from dvd_av1_batch import save


def cases(manifest, media):
    rows=json.loads(Path(manifest).read_text())
    if not isinstance(rows,list) or not rows:raise ValueError('Expected nonempty case list')
    seen=set()
    for row in rows:
        name=row['id']
        if not re.fullmatch(r'[a-z0-9-]{1,48}',name) or name in seen:
            raise ValueError('Case IDs must be unique neutral identifiers')
        seen.add(name)
        source=Path(row['source']).resolve(strict=True)
        if not source.is_file() or not source.is_relative_to(media):
            raise ValueError('Source must be inside read-only media mount')
        if type(row['cq']) is not int or row['cq'] not in range(18,33):
            raise ValueError('Invalid AV1 CQ')
        row['source']=str(source)
    return rows


def command(row, output):
    return [sys.executable,'-B','-m','auto_optimize',row['source'],
        '--output-dir',str(output),'--execute','--encode-best','--hardware','nvidia',
        '--playback-verified-codecs','av1','--research-full-av1-cq',str(row['cq']),
        '--qualities','balanced','--nvenc-tune','hq','--nvenc-analysis','lookahead32-fullres',
        '--nvenc-maxrate-mbps','200','--seconds','10','--vmaf-mean','90','--vmaf-p5','90',
        '--savings-mode','size-aware','--minimum-savings-percent','25',
        '--min-free-gib','50','--timeout','86400']


def main():
    if sys.platform!='linux':raise RuntimeError('Run only in the isolated Linux Docker app')
    media,output,bind,port,hosts,_=config(os.environ)
    if not is_read_only(media):raise ValueError('Media mount must be read-only')
    rows=cases(os.environ.get('MUXMENDER_RESEARCH_MANIFEST','/config/cases.json'),media)
    stop=threading.Event()
    catalog=Catalog(output,[output])
    summary=dict(research_only=True,publication_authorized=False,state='starting')
    server=ThreadingHTTPServer((bind,port),make_handler(catalog,page=HTML,
        allowed_hosts=hosts,app_provider=lambda:dict(media_root=str(media),output_root=str(output),
            media_read_only=True,worker=summary['state'],research=dict(summary))))
    def batch():
        for row in rows:
            if stop.is_set():break
            folder=output/row['id']
            folder.mkdir(exist_ok=True)
            marker=folder/'submitted.json'
            try:
                with marker.open('x') as f:json.dump(row,f)
            except FileExistsError:
                # Includes interrupted work: never silently restart or overwrite.
                continue
            summary.update(state='Running '+row['id'])
            save(output/'research-batch.json',summary)
            try:
                with (folder/'launcher.log').open('x') as log:
                    worker=subprocess.Popen(command(row,folder),stdout=log,stderr=subprocess.STDOUT,
                                            start_new_session=True)
                    while worker.poll() is None:
                        if stop.wait(1):
                            os.killpg(worker.pid,signal.SIGINT)
                            try:worker.wait(timeout=20)
                            except subprocess.TimeoutExpired:
                                os.killpg(worker.pid,signal.SIGKILL)
                                worker.wait()
                            break
                    save(folder/'exit.json',dict(exit_code=worker.returncode,
                         research_only=True,publication_authorized=False))
            except Exception as exc:
                save(folder/'exit.json',dict(error=str(exc),research_only=True,publication_authorized=False))
        summary.update(state='Stopped' if stop.is_set() else 'Research batch finished; inspect each result')
        save(output/'research-batch.json',summary)
    thread=threading.Thread(target=batch)
    def shutdown(*unused):
        stop.set()
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    thread.start()
    try:server.serve_forever()
    finally:
        stop.set()
        thread.join()
        server.server_close()


if __name__=='__main__':main()
