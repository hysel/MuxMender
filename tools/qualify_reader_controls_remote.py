"""Run owned reader pause/cancellation tests on Linux, never on the Windows host."""
import base64
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
    job=Job('E:/MuxMender-TestOutputs/performance-followup-20261001/reports',
            'Linux owned reader pause and cancellation qualification')
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in (ROOT/'python').rglob('*.py'):
            bundle.write(path,'python/'+path.relative_to(ROOT/'python').as_posix())
        for name in ('test_cooperative_pause','test_gpu_frame_reader','test_gpu_reader_receipt','test_validation_resources',
                     'test_gpu_admission','test_hdr10plus_validation','test_quality_thread_budget',
                     'test_sdr_thread_budget','test_sdr_worker_integration','test_source_audio_preflight'):
            bundle.write(ROOT/('tests/'+name+'.py'),name+'.py')
        bundle.write(ROOT/'tests/test_reader_image_stage.py','tests/test_reader_image_stage.py')
        for name in ('stage_reader_integration','build_app_release','benchmark_shared_gpu_reader'):
            bundle.write(ROOT/('tools/'+name+'.py'),'tools/'+name+'.py')
        bundle.write(ROOT/'tools/benchmark_shared_gpu_reader.py','benchmark_shared_gpu_reader.py')
        for name in ('Dockerfile.reader-integration','launch-reader-integration.sh'):
            bundle.write(ROOT/('deploy/truenas/'+name),'deploy/truenas/'+name)
    remote='/work/reader-controls-'+uuid.uuid4().hex
    payload="""import base64,io,pathlib,sys,unittest,zipfile
if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only tests')
root=pathlib.Path(REMOTE);root.mkdir(exist_ok=False)
bundle=zipfile.ZipFile(io.BytesIO(base64.b64decode(ARCHIVE)))
for name in bundle.namelist():
 p=pathlib.PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive')
bundle.extractall(root)
sys.path[:0]=[str(root/'python'),str(root/'tests'),str(root)]
import os
os.environ['PYTHONPATH']=str(root/'python')
suite=unittest.defaultTestLoader.loadTestsFromNames(['test_cooperative_pause','test_gpu_frame_reader','test_gpu_reader_receipt',
 'test_validation_resources','test_gpu_admission','test_hdr10plus_validation','test_reader_image_stage',
 'test_quality_thread_budget','test_sdr_thread_budget','test_sdr_worker_integration','test_source_audio_preflight'])
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
""".replace('REMOTE',repr(remote)).replace('ARCHIVE',repr(base64.b64encode(archive.getvalue()).decode()))
    try:
        job.save(phase='Testing only owned synthetic Linux workers',detail='No GPU/media work; production unchanged')
        result=subprocess.run(['ssh','-i','C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519',
            '-o','BatchMode=yes','-o','ConnectTimeout=5','muxmender@192.168.1.232',
            'sudo -n /root/muxmender-research-access'],input=payload,text=True,capture_output=True,timeout=60)
        log=result.stdout+result.stderr
        (job.directory/'research.log').write_text(log,encoding='utf-8')
        job.save(state='completed' if result.returncode==0 else 'failed',phase='Linux reader controls passed' if result.returncode==0 else 'Linux reader controls need investigation',detail=log[-3000:],finished=time.time())
        print(log)
        return result.returncode
    except BaseException as exc:
        job.save(state='failed',phase='Linux reader controls unavailable',error=str(exc),finished=time.time())
        raise


if __name__=='__main__':raise SystemExit(main())
