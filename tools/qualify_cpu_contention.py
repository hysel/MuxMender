"""Linux-only generated CPU-contention qualification; no media mounts required."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def competitor():
    # Separate container, finite CPU-only work. Never consume unbounded RAM.
    os.nice(19)
    count=len(os.sched_getaffinity(0))
    if not 1<=count<=64:raise RuntimeError('Host CPU count outside reviewed test range')
    code='import time\nend=time.monotonic()+18\nwhile time.monotonic()<end: sum(range(10000))'
    children=[]
    try:
        for _ in range(count):children.append(subprocess.Popen([sys.executable,'-c',code]))
        deadline=time.monotonic()+23
        for child in children:child.wait(timeout=max(.1,deadline-time.monotonic()))
    finally:
        for child in children:
            if child.poll() is None:child.kill()
        for child in children:child.wait(timeout=5)


def qualify(output,gpu=False):
    from cooperative_pause import launch_owned,OwnedStagePause
    from resource_governor import Governor
    from resource_yield import CPUYieldPolicy
    from gpu_activity import YieldController
    from job_tracking import Job
    output.mkdir(parents=True,exist_ok=False)
    kind='GPU' if gpu else 'CPU'
    job=Job(output/'reports',f'Real external {kind} contention: generated frame preservation')
    baseline=output/'baseline.md5';actual=output/'yielded.md5'
    child=None;pause=None;samples=[];saw_pause=False;saw_resume=False
    start=time.monotonic()
    try:
        job.save(phase='Creating generated baseline')
        source=['-f','lavfi','-i','testsrc2=size=640x360:rate=24:duration=30' if gpu else 'testsrc2=size=64x64:rate=24:duration=30']
        prefix=['ffmpeg','-nostdin','-v','error','-threads','1']
        baseline_media=output/'baseline.mkv';actual_media=output/'yielded.mkv'
        encoder=['-c:v','hevc_nvenc','-preset','p4','-cq','24','-an']
        subprocess.run([*prefix,*source,*(encoder+[str(baseline_media)] if gpu else ['-f','framemd5',str(baseline)])],check=True,timeout=20)
        child=launch_owned([*prefix,'-re',*source,*(encoder+[str(actual_media)] if gpu else ['-f','framemd5',str(actual)])])
        pause=OwnedStagePause(child,output/'lease.json')
        controller=YieldController(output/'lease.json');policy=CPUYieldPolicy();governor=Governor()
        governor.sample(include_gpu=False)
        (output/'ready').write_text('Waiting for separately owned competing load\n')
        while child.poll() is None:
            if time.monotonic()-start>130:raise TimeoutError('Bounded contention test expired')
            time.sleep(1)
            telemetry=governor.sample(include_gpu=False) if not gpu else {}
            if gpu:state=controller.tick(True)
            else:
                state=policy.decide(telemetry)
                controller.tick(False,resource=state)
            stopped=pause.update()
            if stopped:saw_pause=True
            elif saw_pause:saw_resume=True
            samples.append(dict(elapsed=time.monotonic()-start,telemetry=telemetry,decision=state,stopped=stopped))
            job.save(phase=f'Yielding to competing {kind} work' if stopped else 'Generated task running',
                     detail='Actual ownership telemetry; unchanged yielding thresholds')
        if child.returncode:raise RuntimeError('Generated task failed')
        if gpu:
            for media,hashes in ((baseline_media,baseline),(actual_media,actual)):
                subprocess.run([*prefix,'-i',str(media),'-f','framemd5',str(hashes)],check=True,timeout=20)
        identical=baseline.read_bytes()==actual.read_bytes()
        passed=saw_pause and saw_resume and identical
        report=dict(passed=passed,observed_pause=saw_pause,observed_resume=saw_resume,
                    frame_hashes_equal=identical,samples=samples,
                    scope=f'Real external {kind} load; generated frame preservation, not all workloads')
        (output/'result.json').write_text(json.dumps(report,indent=2))
        if not passed:raise RuntimeError('Pause/resume or frame preservation was not demonstrated; inspect samples')
        job.save(state='completed',phase=f'Real {kind} contention qualification passed',finished=time.time())
    except BaseException as error:
        (output/'failure.json').write_text(json.dumps(dict(error=str(error),samples=samples),indent=2))
        job.save(state='failed',phase=f'{kind} contention qualification incomplete',detail=str(error),finished=time.time())
        raise
    finally:
        if pause:pause.resume()
        if child:
            if child.poll() is None:child.kill()
            child.wait(timeout=5)


def main():
    if sys.platform!='linux':raise RuntimeError('Run only on Linux, never the desktop host')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('qualify','competitor','qualify-gpu','gpu-competitor'))
    parser.add_argument('--output',type=Path,default=Path('/work/cpu-contention'))
    args=parser.parse_args()
    if args.mode=='competitor':competitor()
    elif args.mode=='gpu-competitor':
        subprocess.run(['ffmpeg','-nostdin','-v','error','-filter_threads','2','-re','-f','lavfi','-i',
            'testsrc2=size=1920x1080:rate=120:duration=18','-c:v','hevc_nvenc','-preset','p7',
            '-rc-lookahead','32','-f','null','-'],check=True,timeout=25)
    else:qualify(args.output,args.mode=='qualify-gpu')


if __name__=='__main__':main()
