"""Run tracked Linux copied-audio diagnostics; do not execute native payloads locally."""
import base64
import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from job_tracking import Job


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--passthrough',action='store_true')
    parser.add_argument('--complete',action='store_true')
    parser.add_argument('--case',type=int,choices=(0,1))
    parser.add_argument('--original-clock',action='store_true')
    parser.add_argument('--decode-clock',action='store_true')
    parser.add_argument('--retain-lacing',action='store_true')
    parser.add_argument('--pyav-wheel',type=Path)
    parser.add_argument('--assembly',action='store_true')
    parser.add_argument('--regressions',action='store_true')
    parser.add_argument('--fixtures-only',action='store_true')
    parser.add_argument('--gpu-fixtures',action='store_true')
    args=parser.parse_args()
    jobs=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    job=Job(jobs,'Copied track failures — real-source mux diagnosis')
    remote='/work/copied-mux-'+uuid.uuid4().hex
    key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519'
    host='muxmender@192.168.1.232'
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in (ROOT/'python').rglob('*.py'):
            bundle.write(path,'python/'+path.relative_to(ROOT/'python').as_posix())
        bundle.write(ROOT/'tools/research_copied_track_mux.py','research.py')
        if args.regressions:
            for name in ('test_dv_full_file.py','test_copied_audio_relay.py','test_matroska_audio_recovery.py','test_output_presets.py'):
                bundle.write(ROOT/'tests'/name,'tests/'+name)
        if args.pyav_wheel:
            import hashlib
            if hashlib.sha256(args.pyav_wheel.read_bytes()).hexdigest() not in (
                    '1bea5b6134209305199bce7627ac3d33964de2cf2b09c77d08e7f67cf8bd4170',
                    '8a032e8d8ebc73dec079364b9b4a6837638a2d106e8472314e685ffbf163e700'):
                raise ValueError('Research PyAV wheel checksum mismatch')
            bundle.write(args.pyav_wheel,'pyav.whl')
    payload="""import base64,io,pathlib,sys,zipfile
if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only research')
root=pathlib.Path(REMOTE);root.mkdir(exist_ok=False)
import atexit,shutil
def cleanup_runtime():
 folder=root/'pyav'
 if folder.is_dir() and not folder.is_symlink() and folder.resolve().parent==root.resolve():
  shutil.rmtree(folder)
 wheel=root/'pyav.whl'
 if wheel.is_file() and not wheel.is_symlink():wheel.unlink()
 (root/'temporary-runtime-cleanup.json').write_text(__import__('json').dumps(dict(owned_runtime_removed=True,reports_retained=True)))
atexit.register(cleanup_runtime)
bundle=zipfile.ZipFile(io.BytesIO(base64.b64decode(ARCHIVE)))
for name in bundle.namelist():
 p=pathlib.PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive')
bundle.extractall(root);sys.path[:0]=[str(root/'python'),str(root)]
if DIRECTPACKETS:
 wheel=zipfile.ZipFile(root/'pyav.whl')
 for name in wheel.namelist():
  p=pathlib.PurePosixPath(name)
  if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe wheel')
 wheel.extractall(root/'pyav');sys.path.insert(0,str(root/'pyav'))
import research
if not ONLYFIXTURES:
 research.main(root,PASSTHROUGH,COMPLETE,ONLYCASE,ORIGINALCLOCK,DECODECLOCK,RETAINLACING,DIRECTPACKETS,ASSEMBLY)
if REGRESSIONS:
 import os,unittest,time
 from job_tracking import Job
 testjob=Job(root/'reports','End-to-end generated audio mux and quality qualification')
 testjob.save(phase='Running full generated media preservation and quality checks')
 os.environ['PYTHONPATH']=os.pathsep.join([str(root/'python'),str(root/'pyav')])
 if GPUFIXTURES:os.environ['MUXMENDER_QUALIFY_GPU']='1'
 os.environ['MUXMENDER_FIXTURE_RESULTS']=str(root/'preset-fixture-results.json')
 sys.path.insert(0,str(root/'tests'))
 suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in
  ('test_dv_full_file','test_copied_audio_relay','test_matroska_audio_recovery','test_output_presets'))
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 testjob.save(state='completed' if result.wasSuccessful() else 'failed',
  phase='Generated full conversion qualification complete',finished=time.time(),
  detail=str(result.testsRun)+' tests; '+str(len(result.skipped))+' skipped')
 if not result.wasSuccessful():raise RuntimeError('Generated conversion qualification failed')
 if ONLYFIXTURES:print('MUX_RESULT='+__import__('json').dumps(dict(generated_tests=result.testsRun,skipped=len(result.skipped),passed=True,gpu_presets=GPUFIXTURES,preset_receipts=__import__('json').loads((root/'preset-fixture-results.json').read_text()),publication_authorized=False)))
""".replace('REMOTE',repr(remote)).replace('ARCHIVE',repr(base64.b64encode(archive.getvalue()).decode())).replace('PASSTHROUGH',repr(args.passthrough)).replace('COMPLETE',repr(args.complete)).replace('ONLYCASE',repr(args.case)).replace('ORIGINALCLOCK',repr(args.original_clock)).replace('DECODECLOCK',repr(args.decode_clock)).replace('RETAINLACING',repr(args.retain_lacing)).replace('DIRECTPACKETS',repr(bool(args.pyav_wheel)))
    payload=payload.replace('ASSEMBLY',repr(args.assembly))
    payload=payload.replace('REGRESSIONS',repr(args.regressions))
    payload=payload.replace('ONLYFIXTURES',repr(args.fixtures_only))
    payload=payload.replace('GPUFIXTURES',repr(args.gpu_fixtures))
    config=job.directory/'monitor-config.json'
    config.write_text(json.dumps([dict(id=remote,title='Live copied audio timestamp diagnosis',host=host,key=key,
        command=['sudo','-n','/root/muxmender-research-access'],roots=[remote],kind='tracked')]))
    observer=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),
        '--config',str(config),'--output',str(jobs),'--interval','10'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    terminal=False
    try:
        job.save(phase='Diagnosing full source audio remux',detail='Low CPU priority; read-only sources; no GPU or publication')
        run=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
            'sudo -n /root/muxmender-research-access'],input=payload,text=True,encoding='utf-8',capture_output=True,timeout=1800)
        terminal=True
        (job.directory/'research.log').write_text(run.stdout+run.stderr)
        rows=[line.split('=',1)[1] for line in run.stdout.splitlines() if line.startswith('MUX_RESULT=')]
        if run.returncode or not rows:raise RuntimeError('Mux research failed: '+run.stderr[-1500:])
        report=json.loads(rows[-1]);(job.directory/'result.json').write_text(json.dumps(report,indent=2))
        job.save(state='completed',phase='Real-source mux diagnosis complete',detail=json.dumps(report),finished=time.time())
        print(json.dumps(report))
    except BaseException as exc:
        job.save(state='failed' if terminal else 'stale',phase='Mux diagnosis needs inspection',error=str(exc),finished=time.time() if terminal else None)
        raise
    finally:
        if terminal:
            try:observer.wait(timeout=20)
            except subprocess.TimeoutExpired:observer.terminate();observer.wait(timeout=5)


if __name__=='__main__':main()
