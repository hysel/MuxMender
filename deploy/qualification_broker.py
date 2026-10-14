"""Fixed-operation Linux qualification broker. Install root-owned; no CLI args.

Only signed hosted candidates are loaded. There is no shell, media mount,
production-container command, registry publication or caller-supplied command.
The broker remains inactive until an administrator installs it and its harness.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid

BASE=Path('/var/lib/muxmender-qualification')
CONFIG=BASE/'config.json'
IMAGE_LIMIT=3*1024**3


def trusted(path):
    path=Path(path)
    for part in (path,*path.parents):
        info=part.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid!=0 or info.st_mode & 0o022:
            raise ValueError('Root-owned, non-writable installation required: '+str(part))
    return path


def copy_input(source,target,limit):
    # The parent inbox is fixed under a root-owned directory; reject link files.
    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError('Invalid or oversized input')
        with Path(target).open('xb') as output:
            copied=0
            while block:=stream.read(1024**2):
                copied+=len(block)
                if copied>limit:raise ValueError('Input grew beyond limit')
                output.write(block)
        if copied!=info.st_size:raise ValueError('Input changed during staging')


def validate_image_archive(path,image_id):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',image_id):raise ValueError('Invalid image ID')
    with tarfile.open(path) as archive:
        names=set()
        for member in archive:
            if member.name in names:raise ValueError('Duplicate archive member')
            names.add(member.name)
            name=member.name.rstrip('/')
            allowed=name in ('manifest.json','index.json','oci-layout','blobs','blobs/sha256') or re.fullmatch(r'blobs/sha256/[a-f0-9]{64}',name)
            if not allowed or not (member.isfile() or member.isdir()):raise ValueError('Unexpected Docker archive member')
        manifest=json.load(archive.extractfile('manifest.json'))
        if len(manifest)!=1 or manifest[0].get('RepoTags'):
            raise ValueError('Only one untagged image may be loaded')
        config='blobs/sha256/'+image_id.removeprefix('sha256:')
        if manifest[0]['Config']!=config:raise ValueError('Image config identity mismatch')
        with archive.extractfile(config) as stream:
            if 'sha256:'+hashlib.file_digest(stream,'sha256').hexdigest()!=image_id:raise ValueError('Image config checksum mismatch')


def idle(url):
    with urllib.request.urlopen(url,timeout=10) as response:data=json.load(response)
    now=data.get('server_time');updated=data.get('queue_snapshot_updated')
    if (data.get('ready') is not True or data.get('error') or not isinstance(data.get('jobs'),list)
            or not isinstance(now,(int,float)) or not isinstance(updated,(int,float)) or not 0<=now-updated<=15):
        raise RuntimeError('Cannot establish a fresh production queue state')
    if any(j.get('state') in ('pending','queued','running') for j in data['jobs']):
        raise RuntimeError('Production is busy; qualification deferred')


def docker_command(image,name,token,harness,scratch,gpu,arguments):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',image):raise ValueError('Immutable image required')
    if not re.fullmatch(r'GPU-[a-fA-F0-9-]+',gpu):raise ValueError('Explicit GPU UUID required')
    return ['docker','run','--rm','--name',name,'--label','muxmender.qualification='+token,
            '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--pids-limit','512','--cpus','4','--memory','12g','--memory-swap','12g',
            '--user','568:568','--gpus','device='+gpu,'--tmpfs','/tmp:rw,nosuid,nodev,size=256m',
            '--tmpfs','/run:rw,nosuid,nodev,size=16m',
            '--mount',f'type=bind,src={harness},dst=/qualification,readonly',
            '--mount',f'type=bind,src={scratch},dst=/work','--env','TMPDIR=/work',
            '--entrypoint','/usr/bin/tini',image,'--',*arguments]


def stop_owned(name,token):
    result=subprocess.run(['docker','inspect','--format','{{index .Config.Labels "muxmender.qualification"}}',name],capture_output=True,text=True,timeout=15)
    if result.returncode==0 and result.stdout.strip()==token:
        subprocess.run(['docker','rm','--force',name],check=True,timeout=30,capture_output=True)


def run_stage(config,image,work,arguments,log):
    idle(config['controls_url'])
    token=uuid.uuid4().hex;name='muxmender-qual-'+token
    command=docker_command(image,name,token,config['harness'],work,config['gpu_uuid'],arguments)
    process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+600
    try:
        while process.poll() is None:
            if time.monotonic()>deadline:raise TimeoutError('Qualification stage exceeded ten minutes')
            idle(config['controls_url'])
            time.sleep(5)
        if process.returncode:raise RuntimeError('Qualification stage failed; see log')
    finally:
        stop_owned(name,token)
        if process.poll() is None:process.terminate()
        process.wait(timeout=30)


def main():
    if sys.platform!='linux' or os.geteuid()!=0 or len(sys.argv)!=1:
        raise RuntimeError('Root-owned Linux broker accepts no arguments')
    import fcntl
    trusted(Path(__file__))
    config=json.loads(trusted(CONFIG).read_text())
    trusted(BASE);trusted(config['harness']);trusted(config['gh'])
    # Never inherit caller-controlled Docker endpoints, Python paths or tokens.
    os.environ.clear()
    os.environ.update(PATH='/usr/bin:/bin',LANG='C.UTF-8',HOME=str(BASE/'home'),GH_CONFIG_DIR=str(BASE/'home/gh'))
    (BASE/'home').mkdir(mode=0o700,exist_ok=True)
    if not stat.S_ISDIR((BASE/'inbox').lstat().st_mode):raise ValueError('Inbox must be a real directory')
    if not config.get('enabled'):raise RuntimeError('Broker disabled by administrator')
    # Fixed root-owned harness only, never test code supplied in the inbox.
    for path in Path(config['harness']).rglob('*'):
        if path.is_symlink() and path.name=='python' and os.readlink(path)=='/opt/muxmender':continue
        trusted(path)
    with (BASE/'broker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        idle(config['controls_url'])
        private=Path(tempfile.mkdtemp(prefix='run-',dir=BASE))
        private.chmod(0o755)
        result=dict(state='verifying',publication_approved=False)
        status=private/'result.json'
        try:
            for name,limit in [('candidate.json',1024**2),('attestation.jsonl',16*1024**2),('candidate-image.tar',IMAGE_LIMIT)]:
                copy_input(BASE/'inbox'/name,private/name,limit)
            receipt=json.loads((private/'candidate.json').read_text())
            version=receipt.get('version','')
            if not re.fullmatch(r'\d{8}-v\d+',version):raise ValueError('Candidate version required')
            sys.path.insert(0,str(Path(__file__).parent))
            from verify_candidate_origin import verify
            verify(private/'candidate-image.tar',receipt,private/'attestation.jsonl',config['gh'])
            validate_image_archive(private/'candidate-image.tar',receipt['image_id'])
            subprocess.run(['docker','load','--input',str(private/'candidate-image.tar')],check=True,timeout=180)
            image=receipt['image_id']
            result.update(image_id=image,revision=receipt['revision'],archive_sha256=receipt['sha256'],state='running')
            work=private/'work';work.mkdir();os.chown(work,568,568)
            with (private/'run.log').open('w') as log:
                # The runtime suite asserts the supplied version equals the pinned image's version.
                for mode in ('runtime','reaper','gpu'):
                    result['phase']=mode;status.write_text(json.dumps(result))
                    run_stage(config,image,work,['python3','-B','/qualification/tools/smoke_app_release.py',mode,'--version',version,'--public-runtime'],log)
                result['phase']='resource-integration';status.write_text(json.dumps(result))
                run_stage(config,image,work,['python3','-B','/qualification/tools/qualify_resource_release.py','--output','/work/integration'],log)
                for kind in ('copy','cancel'):
                    scratch=private/kind;scratch.mkdir();os.chown(scratch,568,568)
                    for step in ('initialize','upgrade'):
                        result['phase']=step+'-'+kind;status.write_text(json.dumps(result))
                        run_stage(config,image,scratch,['python3','-B','/qualification/tools/check_public_installation.py',step+'-'+kind,'--work','/work'],log)
            result.update(state='passed',phase='Generated qualification passed')
        except Exception as exc:
            result.update(state='failed',error=str(exc));raise
        finally:
            result['finished']=time.time();status.write_text(json.dumps(result,indent=2))
            # No image prune, source cleanup, production action or registry write.
            print(str(status),flush=True)


if __name__=='__main__':main()
