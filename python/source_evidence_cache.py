"""Small authenticated positive source proofs; never retains media or failures."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import time
import uuid


class SourceEvidenceCache:
    def __init__(self,root):
        self.root=Path(root)
        if os.name!='posix':raise ValueError('Protected source cache requires POSIX ownership')
        if not self.root.is_absolute() or any(p.is_symlink() for p in (self.root,*self.root.parents)):
            raise ValueError('Unsafe source cache path')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        info=self.root.stat()
        if info.st_uid!=os.getuid() or info.st_mode&0o077:
            raise ValueError('Source cache must be private to the app user')
        keypath=self.root/'.key'
        try:
            fd=os.open(keypath,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:pass
        else:
            with os.fdopen(fd,'wb') as stream:
                stream.write(os.urandom(32))
        self.secret=self._read(keypath,32)
        if len(self.secret)!=32:raise ValueError('Invalid source cache key')

    @staticmethod
    def _json(value):
        return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

    @staticmethod
    def _read(path,limit):
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>limit:
                raise ValueError('Unsafe or oversized source cache record')
            return stream.read(limit+1)

    def _path(self,context):
        return self.root/(hashlib.sha256(self._json(context)).hexdigest()+'.json')

    def load(self,context):
        try:
            envelope=json.loads(self._read(self._path(context),65536))
            payload=envelope['payload']
            signature=hmac.new(self.secret,self._json(payload),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature,envelope['signature']):return None
            if payload['context']!=context or not 0<=time.time()-payload['created']<=30*86400:return None
            proof=payload['proof']
            if (proof.get('state')!='passed' or proof.get('complete_decode') is not True or
                    proof.get('strict_decode') is not True or proof.get('tracks')!=context['tracks']):return None
            return proof
        except (OSError,ValueError,KeyError,TypeError):return None

    def store(self,context,proof):
        if (proof.get('state')!='passed' or proof.get('complete_decode') is not True or
                proof.get('strict_decode') is not True or proof.get('tracks')!=context['tracks']):
            raise ValueError('Only complete passing source audio proofs are cacheable')
        payload=dict(context=context,created=time.time(),proof=proof)
        envelope=dict(payload=payload,signature=hmac.new(self.secret,self._json(payload),hashlib.sha256).hexdigest())
        content=self._json(envelope)
        if len(content)>65536:raise ValueError('Source proof too large')
        destination=self._path(context)
        temporary=self.root/('write-'+uuid.uuid4().hex+'.tmp')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(content)
            os.replace(temporary,destination)
        finally:temporary.unlink(missing_ok=True)
        entries=sorted(self.root.glob('[0-9a-f]'*64+'.json'),key=lambda p:p.stat().st_mtime)
        for path in entries[:-2048]:
            if path.is_symlink():continue
            info=path.stat()
            if stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid():path.unlink(missing_ok=True)
