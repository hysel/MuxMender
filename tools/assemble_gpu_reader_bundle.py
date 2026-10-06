"""Assemble a reader artifact from finished research; never publishes an app."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'python'),str(ROOT/'tools')]
from job_tracking import Job
from gpu_reader_receipt import qualified_scope
from build_app_release import inspect_gpu_reader_bundle


def report(directory):
    record=json.loads((directory/'job.json').read_text())
    if record.get('state')!='completed':raise ValueError('Research execution is not complete')
    return json.loads(record['detail'])


def attested_pair(real,controls,witness):
    """Combine immutable provenance and complete evidence without rewriting it."""
    if witness.get('before_gpu_pass') is not True or witness.get('read_only_mount') is not True:
        raise ValueError('Before-GPU immutable artifact provenance is missing')
    digest=witness.get('binary_sha256')
    if digest!=controls.get('binary_sha256'):
        raise ValueError('Reader artifact changed between real-file and damaged controls')
    if real.get('binary_sha256') not in (None,digest):
        raise ValueError('Whole-file report identifies a different reader artifact')
    derived=dict(real,binary_sha256=digest)
    return dict(real=derived,controls=controls),qualified_scope(derived,controls)


def combine_pairs(entries):
    """Accept multiple codec scopes only for one exact binary/runtime binding."""
    pairs=[];scopes=[];witnesses=[];binding=None
    for real,controls,witness in entries:
        pair,scope=attested_pair(real,controls,witness)
        current={key:witness.get(key) for key in ('binary_sha256','adapter','visibility')}
        if binding is not None and current!=binding:
            raise ValueError('Reader scopes cover different artifacts or runtime bindings')
        if any((item['codec'],item['hdr_modes'])==(scope['codec'],scope['hdr_modes']) for item in scopes):
            raise ValueError('Duplicate codec qualification scope')
        binding=current;pairs.append(pair);scopes.append(scope);witnesses.append(witness)
    if not pairs:raise ValueError('No complete reader qualification pairs')
    return pairs,scopes,witnesses,binding


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-job',type=Path,required=True)
    parser.add_argument('--controls-job',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--dependencies',type=Path,required=True)
    parser.add_argument('--additional-pair',nargs=2,type=Path,action='append',default=[],
                        metavar=('REAL_JOB','CONTROLS_JOB'),help='Include another fully qualified codec for the same artifact/runtime')
    args=parser.parse_args()
    job=Job('E:/MuxMender-TestOutputs/performance-followup-20261001/reports','Qualified GPU reader artifact assembly')
    try:
        entries=[]
        for real_job,controls_job in [(args.real_job,args.controls_job),*args.additional_pair]:
            entries.append((report(real_job),report(controls_job),
                json.loads((real_job/'reader-artifact-before-gpu.json').read_text())))
        pairs,scopes,witnesses,binding=combine_pairs(entries)
        destination=args.destination.resolve()
        destination.mkdir(parents=True,exist_ok=False)
        (destination/'source').mkdir()
        job.save(phase='Copying qualified reader and complete source/license artifacts',detail='No media copies; installed app unchanged')
        hostroot='/mnt/FR4G/Apps/muxmender/output/hdr-gpu-reader-build-20261002-r3/binary-r3'
        for remote,local in [('bin/ffprobe-cuda',destination/'ffprobe-cuda'),
                *[(f'source/{name}',destination/'source'/name) for name in
                  ('ffmpeg-8.0.1.tar.xz','patch_cuda_ffprobe.py','COPYING.LGPLv2.1','LICENSE.md')]]:
            copied=subprocess.run(['scp','-i','C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519',
                '-o','BatchMode=yes','-o','ConnectTimeout=5','muxmender@192.168.1.232:'+hostroot+'/'+remote,str(local)],
                text=True,capture_output=True,timeout=60)
            if copied.returncode:raise RuntimeError('Artifact copy failed: '+copied.stderr[-1200:])
        shutil.copyfile(args.dependencies/'nv-codec-headers-n13.0.19.0.tar.gz',
                        destination/'source/nv-codec-headers-n13.0.19.0.tar.gz')
        if hashlib.sha256((destination/'ffprobe-cuda').read_bytes()).hexdigest()!=binding['binary_sha256']:
            raise ValueError('Downloaded reader does not match before/after GPU qualification')
        receipt=dict(schema=1,**binding,scopes=scopes)
        (destination/'qualification.json').write_text(json.dumps(receipt,indent=2))
        (destination/'evidence.json').write_text(json.dumps(dict(pairs=pairs,
            before_gpu_provenance=witnesses),indent=2))
        inspected=inspect_gpu_reader_bundle(destination)
        job.save(state='completed',phase='Qualified reader artifact prepared; not deployed',
            detail=json.dumps(dict(files=len(inspected),scopes=scopes,bundle=str(destination),production_enabled=False)),finished=time.time())
        print('Qualified reader bundle prepared: '+str(destination))
        return 0
    except BaseException as exc:
        job.save(state='failed',phase='Reader bundle was not approved',error=str(exc),finished=time.time())
        raise


if __name__=='__main__':raise SystemExit(main())
