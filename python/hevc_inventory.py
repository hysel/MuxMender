"""Bounded-memory, read-only HEVC NAL evidence shared by CLI and app routing."""
from collections import Counter
import hashlib
import math
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import uuid
from job_tracking import progress

START=re.compile(b'\x00\x00\x01')

class Inventory:
    def __init__(self, *, track_pictures=False):
        self.tail=b'';self.bytes=0;self.last=-1;self.counts=Counter();self.digest=hashlib.sha256()
        self.track_pictures=track_pictures;self.picture_types=[]

    def feed(self,block):
        base=self.bytes-len(self.tail);data=self.tail+block
        self.bytes+=len(block);self.digest.update(block)
        for match in START.finditer(data):
            pos=match.start();absolute=base+pos
            if absolute<=self.last:continue
            if pos+5>len(data):break
            first,second=data[pos+3:pos+5]
            if first&128 or not second&7:raise ValueError('Invalid HEVC NAL header')
            kind,layer=(first>>1)&63,((first&1)<<5)|(second>>3)
            picture=self.track_pictures and kind<32 and layer==0
            if picture and pos+6>len(data):break
            self.counts[(kind,layer)]+=1
            if picture and data[pos+5]&128:self.picture_types.append(kind)
            self.last=absolute
        self.tail=data[-6:]

    def result(self):
        return dict(bytes=self.bytes,bitstream_sha256=self.digest.hexdigest(),
                    nal_counts=[dict(type=t,layer=l,count=n) for (t,l),n in sorted(self.counts.items())],
                    rpu_nals=sum(n for (t,l),n in self.counts.items() if t==62),
                    potential_enhancement_nals=sum(n for (t,l),n in self.counts.items() if l or t==63))

    def finish(self):
        base=self.bytes-len(self.tail)
        if any(base+m.start()>self.last for m in START.finditer(self.tail)):
            raise ValueError('Incomplete final HEVC NAL header')
        if not any(kind<32 for kind,layer in self.counts):raise ValueError('No HEVC picture NALs')
        return self.result()

def identity(source):
    stat=source.stat()
    return dict(size=stat.st_size,mtime_ns=stat.st_mtime_ns,device=stat.st_dev,inode=stat.st_ino)

def inspect_source(ffmpeg,source,directory,guard=lambda:None,*,timeout=600,stop_on_presence=True):
    """Absence requires complete clean demux; positive presence may stop early."""
    if not math.isfinite(timeout) or timeout<=0:raise ValueError('Positive finite timeout required')
    source=Path(source).resolve(strict=True);before=identity(source)
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    error_path=directory/('hevc-reader-'+uuid.uuid4().hex+'.stderr')
    command=[str(ffmpeg),'-v','error','-nostdin','-i',str(source),'-map','0:V:0',
             '-c','copy','-bsf:v','hevc_mp4toannexb','-f','hevc','pipe:1']
    start=last=time.monotonic();inventory=Inventory();complete=False
    messages=queue.Queue(maxsize=2);stop=threading.Event()
    with error_path.open('xb') as errors:
        child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors,bufsize=0)
        def send(value):
            while not stop.is_set():
                try:messages.put(value,timeout=.2);return
                except queue.Full:pass
        def read():
            try:
                while not stop.is_set():
                    block=child.stdout.read(1024*1024)
                    send(block)
                    if not block:return
            except BaseException as exc:send(exc)
        reader=threading.Thread(target=read,daemon=True);reader.start()
        try:
            while True:
                guard();now=time.monotonic()
                if now-start>timeout:raise TimeoutError('Whole-bitstream inspection timeout')
                if now-last>=2:
                    progress('Checking Dolby Vision bitstream evidence',directory=directory,
                             detail=f'{inventory.bytes/1e9:.2f} GB inspected; stream copy, no GPU decode')
                    last=now
                try:block=messages.get(timeout=.5)
                except queue.Empty:continue
                if isinstance(block,BaseException):raise block
                if not block:
                    if child.wait(timeout=10):raise ValueError('Bitstream demux failed')
                    complete=True;break
                inventory.feed(block)
                if stop_on_presence and any(t in (62,63) or layer for t,layer in inventory.counts):break
        finally:
            stop.set()
            if child.poll() is None:child.kill();child.wait()
            reader.join(timeout=2);child.stdout.close()
    if complete and error_path.stat().st_size:raise ValueError('Reader reported errors; absence is not established')
    guard()
    if before!=identity(source):raise ValueError('Source changed during bitstream inspection')
    result=inventory.finish() if complete else inventory.result()
    result.update(complete_bitstream=complete,source_unchanged=True,source_identity=before,
                  elapsed_seconds=time.monotonic()-start,
                  scope='Primary HEVC NAL inventory only; not decode, color or replacement approval')
    return result

def absent_dv(evidence):
    return (evidence.get('complete_bitstream') is True and evidence.get('source_unchanged') is True
            and type(evidence.get('bytes')) is int and evidence['bytes']>0
            and type(evidence.get('rpu_nals')) is int and evidence['rpu_nals']==0
            and type(evidence.get('potential_enhancement_nals')) is int and evidence['potential_enhancement_nals']==0)
