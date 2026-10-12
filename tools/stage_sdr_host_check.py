"""Stage an administrator-run isolated image check, never start Docker."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from job_tracking import Job


def main():
    local=Path('E:/MuxMender-TestOutputs/sdr-host-check-20261012-r1')
    local.mkdir(exist_ok=False)
    bundle=Path('E:/MuxMender-TestOutputs/private-host-reader-qualification-20261012-r1')
    reports=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    job=Job(reports,'Stage isolated installed-image SDR check')
    host='muxmender@192.168.1.232';key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519'
    remote='/mnt/FR4G/Apps/muxmender/output/sdr-host-check-20261012-r1'
    ssh=['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host]
    try:
        files={str(p.relative_to(ROOT)).replace('\\','/'):p.read_bytes() for p in (ROOT/'python').rglob('*.py')}
        for name in ('benchmark_shared_sdr_reader.py','benchmark_sdr_gpu_reader.py'):
            files['tools/'+name]=(ROOT/'tools'/name).read_bytes()
        files['deploy/truenas/install_reader_qualification.py']=(ROOT/'deploy/truenas/install_reader_qualification.py').read_bytes()
        files['run-isolated-check.sh']=(ROOT/'deploy/truenas/run-sdr-host-check.sh').read_bytes().replace(b'\r\n',b'\n')
        for name in ('ffprobe-cuda','qualification.json','evidence.json'):files['private-reader/'+name]=(bundle/name).read_bytes()
        files['SHA256SUMS']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(files.items())).encode()
        archive=local/'check.tar'
        with tarfile.open(archive,'w') as out:
            for name,data in files.items():
                info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644
                out.addfile(info,io.BytesIO(data))
        subprocess.run([*ssh,'mkdir '+remote],check=True,timeout=20)
        subprocess.run(['scp','-i',key,'-o','BatchMode=yes',str(archive),host+':'+remote+'/check.tar'],check=True,timeout=120)
        expected=hashlib.sha256(archive.read_bytes()).hexdigest()
        actual=subprocess.check_output([*ssh,'sha256sum '+remote+'/check.tar'],text=True,timeout=30).split()[0]
        if actual!=expected:raise ValueError('Staged archive checksum differs')
        subprocess.run([*ssh,'tar -xf '+remote+'/check.tar -C '+remote+' && mkdir '+remote+'/results'],check=True,timeout=60)
        config=local/'monitor-config.json'
        config.write_text(json.dumps([dict(id='sdr-host-check-20261012-r1',title='Installed-image SDR qualification',
            host=host,key=key,command=['sudo','-n','/root/muxmender-research-access'],
            roots=['/output/sdr-host-check-20261012-r1/results'],kind='tracked',
            cross_namespace=True,pending_launch=True)]))
        subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),
            '--config',str(config),'--output',str(reports),'--interval','10'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        job.save(state='completed',phase='Staged; administrator launch required',detail=remote,finished=time.time())
        print('sudo bash '+remote+'/run-isolated-check.sh')
    except Exception as exc:
        job.save(state='failed',phase='Image-check staging needs investigation',error=str(exc),finished=time.time())
        raise


if __name__=='__main__':main()
