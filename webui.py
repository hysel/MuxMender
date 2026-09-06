"""Local MuxMender workflow UI. No remote access, arbitrary commands or media deletion."""
import argparse
from collections import deque
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse,parse_qs
import uuid
from dashboard import Catalog,HTML as HISTORY_HTML,alive,contained,read_json,tail,progress,apply_outcome
from workflow_worker import save
from webui_page import PAGE


class ControllerLock:
    def __init__(self,path):
        self.file=path.open('a+b')
        self.file.seek(0,2)
        if self.file.tell()==0: self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close();raise RuntimeError('Another Web UI controller owns this queue')
    def close(self): self.file.close()


class Manager:
    def __init__(self,root,ffmpeg='ffmpeg',ffprobe='ffprobe',start=True):
        self.root=Path(root).resolve();self.directory=self.root/'reports'/'webui-jobs'
        self.directory.mkdir(parents=True,exist_ok=True)
        if not contained(self.directory,self.root): raise ValueError('Queue directory outside project')
        self.owner=ControllerLock(self.directory/'controller.lock')
        self.ffmpeg,self.ffprobe=ffmpeg,ffprobe
        self.token=secrets.token_urlsafe(32)
        self.cv=threading.Condition();self.pending=deque();self.stopping=False;self.active=None
        try:
            for folder in self.directory.iterdir():
                if not folder.is_dir() or not contained(folder,self.directory): continue
                data=read_json(folder/'job.json')
                if data.get('state') in ('running','queued','cancelling'):
                    if data.get('pid') and alive(data['pid']) is not False:
                        raise RuntimeError('An earlier worker may still be running. Wait for it to stop before restarting this controller.')
                    data.update(state='interrupted',phase='Interrupted — reselect and approve to retry',updated=time.time())
                    save(folder/'job.json',data)
        except BaseException:
            self.owner.close();raise
        self.thread=threading.Thread(target=self.loop,daemon=True)
        if start:self.thread.start()

    def folder(self,identifier):
        if not isinstance(identifier,str) or len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('Invalid job ID')
        folder=self.directory/identifier
        if not contained(folder,self.directory) or not folder.is_dir():raise ValueError('Unknown job')
        return folder

    def enqueue(self,payload):
        kind=payload.get('kind')
        if kind not in ('scan','dependencies','preview','convert'):raise ValueError('Unknown action')
        hardware=payload.get('hardware','auto');codec=payload.get('codec','hevc')
        if hardware not in ('auto','amd','nvidia','intel','cpu') or codec not in ('hevc','av1'):raise ValueError('Invalid encoder choice')
        request=dict(kind=kind,hardware=hardware,codec=codec,ffmpeg=self.ffmpeg,ffprobe=self.ffprobe,
                     excluded=[str(self.root/'reports'),str(self.root/'test-output')])
        if kind in ('preview','convert'):
            if payload.get('approved') is not True:raise ValueError('Explicit conversion approval is required')
            row=self.row(payload.get('scan'),payload.get('row'))
            if row.get('action')!='preview-candidate':raise ValueError('This row is not eligible for the ordinary SDR encoder')
            request.update(source=row['path'],fingerprint=row.get('fingerprint'))
            if not request['fingerprint']:
                selected_stat=Path(request['source']).stat()
                request['fingerprint']={'size':selected_stat.st_size,'mtime_ns':selected_stat.st_mtime_ns}
            for key,default in (('start',300),('seconds',30),('min_savings',5)):
                value=float(payload.get(key,default))
                if not math.isfinite(value):raise ValueError('Nonfinite option')
                request[key]=value
            if request['start']<0 or not 1<=request['seconds']<=30 or not 0<=request['min_savings']<100:
                raise ValueError('Invalid preview range/savings threshold')
        elif kind=='scan':
            value=payload.get('source')
            if not isinstance(value,str) or not value.strip() or '\x00' in value:raise ValueError('Enter a media path')
            path=Path(value).expanduser()
            if not path.is_absolute():raise ValueError('Use an absolute media path')
            path=path.resolve(strict=True)
            if contained(path,self.directory):raise ValueError('Cannot scan the queue output directory')
            request['source']=str(path)
        identifier=uuid.uuid4().hex
        with self.cv:
            if self.stopping:raise ValueError('Controller is stopping')
            folder=self.directory/identifier;folder.mkdir(exist_ok=False)
            with (folder/'request.json').open('x',encoding='utf-8') as out:json.dump(request,out,indent=2)
            save(folder/'job.json',dict(id=identifier,title=kind+': '+Path(request.get('source','Dependencies')).name,
                state='queued',kind=kind,phase='Queued',source=request.get('source'),started=None,updated=time.time()))
            self.pending.append(identifier);self.cv.notify()
        return identifier

    def cancel(self,identifier):
        with self.cv:
            folder=self.folder(identifier);data=read_json(folder/'job.json')
            if data.get('state')=='queued':
                try:self.pending.remove(identifier)
                except ValueError:pass
                data.update(state='cancelled',phase='Cancelled before start',finished=time.time(),updated=time.time())
                save(folder/'job.json',data)
            elif data.get('state') in ('running','cancelling'):
                (folder/'STOP').touch(exist_ok=True)
            else:raise ValueError('Job is not queued or running')

    def jobs(self):
        rows=[]
        for folder in self.directory.iterdir():
            if not folder.is_dir() or not contained(folder,self.directory):continue
            data=read_json(folder/'job.json')
            if not data:continue
            parsed=progress(tail(folder/'terminal.log'))
            if data.get('state')=='running':
                data.update(parsed)
                data['elapsed']=time.time()-(data.get('started') or time.time())
                if (folder/'STOP').exists():data['phase']='Cancellation requested; waiting for owned worker'
            rows.append(apply_outcome(data,folder,self.root))
        return sorted(rows,key=lambda x:x.get('updated',0),reverse=True)

    def scans(self):
        scans={}
        # Include this controller's scans and previous scan reports. Never follow directory links.
        for parent,children,files in os.walk(self.root/'reports',followlinks=False):
            children[:]=[n for n in children if not (Path(parent)/n).is_symlink()
                         and not getattr(Path(parent)/n,'is_junction',lambda:False)()
                         and contained(Path(parent)/n,self.root/'reports')]
            if 'files.jsonl' in files:
                path=Path(parent)/'files.jsonl'
                if not contained(path,self.root/'reports'):continue
                identifier=hashlib.sha256(str(path).encode()).hexdigest()[:24]
                scans[identifier]=path
        return scans

    def rows(self,identifier,offset=0,limit=100,action='',query=''):
        if action not in ('','preview-candidate','needs-review','keep-as-is','specialized-dv','probe-error'):
            raise ValueError('Invalid recommendation filter')
        if not isinstance(query,str) or len(query)>256:raise ValueError('Search is limited to 256 characters')
        path=self.scans().get(identifier)
        if path is None:raise ValueError('Unknown scan')
        results=[];total=0;scanned=0
        with path.open(encoding='utf-8') as stream:
            for index,line in enumerate(stream):
                try:row=json.loads(line)
                except ValueError:continue  # May see the last incomplete line during a live scan.
                if not isinstance(row,dict):continue
                row=self.classify_row(row,index)
                scanned+=1
                if action and row.get('action')!=action:continue
                if query.casefold() not in str(row.get('path','')).casefold():continue
                if offset<=total<offset+limit:
                    results.append(row)
                total+=1
        return dict(rows=results,total=total,offset=offset,scanned=scanned,scan=identifier)

    @staticmethod
    def classify_row(row,index):
        row['id']=index
        if row.get('video_codec'):
            from library_planner import classify
            from types import SimpleNamespace
            row['action'],row['reason']=classify(SimpleNamespace(**row))
        return row

    def row(self,scan,identifier):
        if not isinstance(identifier,int) or identifier<0:raise ValueError('Invalid row')
        path=self.scans().get(scan)
        if path is None:raise ValueError('Unknown scan')
        with path.open(encoding='utf-8') as stream:
            for index,line in enumerate(stream):
                if index==identifier:
                    row=json.loads(line)
                    if not isinstance(row,dict):raise ValueError('Invalid scan row')
                    return self.classify_row(row,index)
        raise ValueError('Unknown row')

    def loop(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda:self.pending or self.stopping)
                if self.stopping:return
                identifier=self.pending.popleft();self.active=identifier
                folder=self.folder(identifier);data=read_json(folder/'job.json')
                data.update(state='running',phase='Starting worker',started=time.time(),updated=time.time())
                save(folder/'job.json',data)
                try:
                    log=(folder/'terminal.log').open('x',encoding='utf-8')
                    child=subprocess.Popen([sys.executable,'-B','-u',str(Path(__file__).with_name('workflow_worker.py')),
                        str(folder),'--parent-pid',str(os.getpid())],stdout=log,stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,cwd=self.root)
                    data['pid']=child.pid;save(folder/'job.json',data)
                    (folder/'READY').touch(exist_ok=False)
                except Exception as exc:
                    data.update(state='failed',phase='Worker launch failed',error=str(exc),updated=time.time())
                    save(folder/'job.json',data);self.active=None
                    if 'log' in locals():log.close()
                    continue
            child.wait();log.close()
            with self.cv:
                data=read_json(folder/'job.json')
                if data.get('state')=='running':
                    data.update(state='interrupted',phase='Worker ended without a final record',updated=time.time(),exit_code=child.returncode)
                    save(folder/'job.json',data)
                self.active=None

    def close(self):
        with self.cv:
            self.stopping=True
            if self.active:(self.folder(self.active)/'STOP').touch(exist_ok=True)
            self.cv.notify_all()
        if self.thread.is_alive():self.thread.join(timeout=10)
        self.owner.close()


def handler(manager):
    catalog=Catalog(manager.root)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def respond(self,data,status=200,kind='application/json; charset=utf-8'):
            body=data.encode() if isinstance(data,str) else json.dumps(data).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if not self.valid_host():self.respond({'error':'Invalid Host'},403);return
            url=urlparse(self.path);q=parse_qs(url.query)
            try:
                if url.path=='/':self.respond(PAGE,kind='text/html; charset=utf-8')
                elif url.path=='/history':self.respond(HISTORY_HTML,kind='text/html; charset=utf-8')
                elif url.path=='/api/session':self.respond({'token':manager.token})
                elif url.path=='/api/queue':self.respond({'jobs':manager.jobs()})
                elif url.path=='/api/scans':self.respond({'scans':[{'id':k,'name':v.parent.name} for k,v in manager.scans().items()]})
                elif url.path=='/api/rows':self.respond(manager.rows(q.get('scan',[''])[0],max(0,int(q.get('offset',['0'])[0])),100,q.get('action',[''])[0],q.get('q',[''])[0]))
                elif url.path=='/api/queue-log':self.respond({'text':tail(manager.folder(q.get('id',[''])[0])/'terminal.log')})
                elif url.path=='/api/jobs':self.respond({'jobs':catalog.snapshot(),'now':time.time()})
                elif url.path=='/api/log':
                    catalog.snapshot();path=catalog.logs.get(q.get('id',[''])[0])
                    if not path or not contained(path,manager.root):raise ValueError('Unknown log')
                    self.respond({'text':tail(path)})
                else:self.respond({'error':'Not found'},404)
            except (OSError,ValueError,KeyError,TypeError) as exc:self.respond({'error':str(exc)},400)
        def do_POST(self):
            origin='http://'+self.headers.get('Host','')
            if not self.valid_host() or self.headers.get('Origin')!=origin or not secrets.compare_digest(self.headers.get('X-MuxMender-Token',''),manager.token):
                self.respond({'error':'Local origin and session token required'},403);return
            try:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384:raise ValueError('Invalid request size')
                self.connection.settimeout(10)
                data=json.loads(self.rfile.read(size))
                if not isinstance(data,dict):raise ValueError('Expected object')
                if self.path=='/api/enqueue':self.respond({'id':manager.enqueue(data)},201)
                elif self.path=='/api/cancel':manager.cancel(data.get('id'));self.respond({'ok':True})
                else:self.respond({'error':'Not found'},404)
            except (OSError,ValueError,KeyError,TypeError) as exc:self.respond({'error':str(exc)},400)
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--ffmpeg',default='ffmpeg');parser.add_argument('--ffprobe',default='ffprobe')
    args=parser.parse_args()
    manager=Manager(args.root,args.ffmpeg,args.ffprobe)
    try:
        server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(manager))
        print(f'MuxMender Web UI: http://127.0.0.1:{server.server_port}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
    finally:manager.close()


if __name__=='__main__':main()
