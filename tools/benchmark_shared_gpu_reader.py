"""Linux-only generated test of the shared Workflow frame-reader integration.

The research receipt is explicitly injected into a Workflow instance. This tests
the shared dispatch and validation path, not image-owned receipt installation.
It neither approves a conversion nor grants permission to replace source media.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace


def finish_report(job,report,output,paths):
    """Publish success only after exact owned cleanup and evidence persistence."""
    removed=0
    try:
        for path in paths:
            if path.is_file() and not path.is_symlink():
                removed+=path.stat().st_size;path.unlink()
        report['temporary_bytes_removed']=removed
        (output/'benchmark.json').write_text(json.dumps(report,indent=2))
    except Exception as exc:
        report['temporary_bytes_removed']=removed
        report['cleanup_or_evidence_error']=str(exc)
        job.save(state='failed',phase='Shared reader evidence or cleanup needs investigation',
                 error=str(exc),finished=time.time())
        raise
    if 'error' not in report:
        job.save(state='completed',phase='Shared engine reader integration passed',
                 detail=json.dumps(report),finished=time.time())


def main():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Shared native-reader research runs on Linux only')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--installed-profile',action='store_true',help='Require the production image-owned profile loader instead of research injection')
    parser.add_argument('--full-validation',action='store_true',help='Also exercise complete output, metadata, quality and default savings checks on a generated conversion')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    from job_tracking import Job,isolated_progress
    job=Job(args.output/'reports','Shared engine GPU reader integration')
    fixture=args.output/'generated-pq-av1.mkv'
    report=dict(production_enabled=False,package_loader_tested=args.installed_profile,
                package_loader_passed=False,quality_approved=False,replacement_authorized=False)
    try:
        receipt=json.loads(args.receipt.read_text())
        if hashlib.sha256(args.binary.read_bytes()).hexdigest()!=receipt.get('binary_sha256'):
            raise ValueError('Research reader does not match the qualified executable')
        report['binary_sha256']=receipt['binary_sha256']
        from gpu_frame_reader import select_reader
        profile=dict(receipt,binary=str(args.binary))
        if args.installed_profile:
            from gpu_frame_reader import load_qualification
            profile=load_qualification()
            if profile is None or Path(profile['binary']).resolve()!=args.binary.resolve():
                raise ValueError('Installed image did not accept the qualified reader')
            if profile.get('binary_sha256')!=receipt['binary_sha256'] or profile.get('scopes')!=receipt.get('scopes'):
                raise ValueError('Installed image receipt differs from the requested qualification')
            report['package_loader_passed']=True
        video=dict(codec_name='av1',pix_fmt='yuv420p10le',width=1280,height=720)
        if select_reader(video,61,'pq',profile)['backend']!='cuda':
            raise ValueError('Receipt does not cover the generated PQ integration control')
        import auto_optimize
        from auto_optimize import Workflow
        from hdr10plus_preserve import frame_records
        from hdr10plus_validation import validate_frames
        job.save(phase='Generating a 61-second integration control')
        result=subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-filter_threads','2',
            '-f','lavfi','-i','testsrc2=size=1280x720:rate=24:duration=61,format=yuv420p10le,setparams=range=limited:color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc',
            '-c:v','av1_nvenc','-preset','p4','-cq','12' if args.full_validation else '24','-pix_fmt','yuv420p10le',
            '-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc',
            '-color_range','tv',str(fixture)],capture_output=True,text=True,timeout=180)
        if result.returncode or result.stderr:
            raise ValueError('Generated integration control failed: '+result.stderr[-1500:])
        paths={};timings={}
        dispatch=[]
        original_probe=auto_optimize.run_probe
        def observe_probe(command,*arguments,**options):
            dispatch.append(dict(binary=str(command[0]),complete='-show_frames' in command and '-read_intervals' not in command,
                native=(options.get('env') or {}).get('MUXMENDER_RESEARCH_CUDA_READER')=='1'))
            return original_probe(command,*arguments,**options)
        for backend in ('cpu','cuda'):
            workflow=Workflow(SimpleNamespace(hdr_mode='pq',ffprobe='ffprobe',timeout=180),args.output,lambda:None)
            # Explicit harness injection only. Production still requires the
            # image-owned receipt, exact executable hash, adapter and driver.
            workflow.frame_reader_checked=not (args.installed_profile and backend=='cuda')
            workflow.frame_reader_qualification=profile if backend=='cuda' and not args.installed_profile else None
            started=time.monotonic()
            auto_optimize.run_probe=observe_probe
            try:
                with isolated_progress(lambda values:job.save(**values)):
                    paths[backend]=workflow.frame_file(fixture,'integration-'+backend)
            finally:auto_optimize.run_probe=original_probe
            timings[backend]=time.monotonic()-started
        if (len(dispatch)!=2 or any(row['complete'] is not True for row in dispatch)
                or dispatch[0]['native'] or dispatch[1]['native'] is not True
                or Path(dispatch[1]['binary']).resolve()!=args.binary.resolve()):
            raise ValueError('Shared engine did not dispatch the expected complete CPU/GPU readers')
        proof=validate_frames(frame_records(paths['cpu']),frame_records(paths['cuda']),mode='pq')
        if proof.get('frames')!=1464 or proof.get('frame_timestamps_exact') is not True:
            raise ValueError('Complete integration frames/timing did not match')
        report.update(shared_engine_passed=True,proof=proof,reader_seconds=timings,dispatch=dispatch)
        if args.full_validation:
            from task_progress import digest
            from savings_policy import requirement,meets_requirement
            converted=args.output/'generated-converted-av1.mkv'
            original_hash=digest(fixture,lambda:None)
            settings=SimpleNamespace(hdr_mode='pq',ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=600,
                                     vmaf_mean=90,vmaf_p5=90,source=fixture)
            workflow=Workflow(settings,args.output,lambda:None)
            if not args.installed_profile:
                workflow.frame_reader_checked=True;workflow.frame_reader_qualification=profile
            with isolated_progress(lambda values:job.save(**values)):
                before=workflow.probe(fixture)
                workflow.execute(['ffmpeg','-v','error','-nostdin','-n','-i',str(fixture),
                    '-map','0:V:0','-c:v','av1_nvenc','-preset','p4','-cq','24','-pix_fmt','yuv420p10le',
                    '-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc',
                    '-color_range','tv',str(converted)],'full-encode',61)
                auto_optimize.run_probe=observe_probe
                try:count=workflow.validate(fixture,converted,before,'av1','converted',paths['cuda'])
                finally:auto_optimize.run_probe=original_probe
                calibration=workflow.quality(fixture,fixture,'self',count,61)
                quality=workflow.quality(fixture,converted,'converted',count,61)
            source_bytes=fixture.stat().st_size;output_bytes=converted.stat().st_size
            policy=requirement(source_bytes)
            if (not dispatch[2:] or any(row['native'] is not True or row['complete'] is not True for row in dispatch[2:])
                    or count!=1464 or calibration.get('passed') is not True or quality.get('passed') is not True
                    or not meets_requirement(source_bytes,output_bytes,policy)
                    or digest(fixture,lambda:None)!=original_hash):
                raise ValueError('Generated full conversion did not meet unchanged quality, preservation, source and savings checks')
            report.update(full_validation_passed=True,source_unchanged=True,
                generated_source_bytes=source_bytes,generated_output_bytes=output_bytes,
                calibration=calibration,quality=quality,savings_policy=policy,
                file_savings_percent=100*(1-output_bytes/source_bytes))
        return 0
    except BaseException as exc:
        report['error']=str(exc)
        job.save(state='failed',phase='Shared reader integration needs investigation',error=str(exc),finished=time.time())
        raise
    finally:
        # Exact owned filenames only; never enumerate or delete /media files.
        paths=[fixture,args.output/'generated-converted-av1.mkv',
                args.output/'converted-frames.jsonl',args.output/'converted-frames.jsonl.stderr',
                args.output/'self-vmaf.json',args.output/'converted-vmaf.json',
                args.output/'integration-cpu-frames.jsonl',args.output/'integration-cuda-frames.jsonl',
                args.output/'integration-cpu-frames.jsonl.stderr',args.output/'integration-cuda-frames.jsonl.stderr']
        finish_report(job,report,args.output,paths)


if __name__=='__main__':raise SystemExit(main())
