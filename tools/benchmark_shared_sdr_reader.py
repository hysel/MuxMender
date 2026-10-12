"""Generated serial CPU/GPU shared-engine comparison; no production changes.

Measures full encoding plus validation and quality scoring, excluding source
generation and codec discovery/trials. Does not authorize a production receipt.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))


def main():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Shared SDR research runs only on Linux')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--codec',choices=('av1','hevc'),default='av1')
    parser.add_argument('--pixel-format',choices=('yuv420p','yuv420p10le'),default='yuv420p')
    parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--installed-profile',action='store_true',help='Require the image/host receipt loader, not harness injection')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    from job_tracking import Job,isolated_progress
    from auto_optimize import Workflow
    import auto_optimize
    from savings_policy import requirement,meets_requirement
    from benchmark_sdr_gpu_reader import file_digest,exact_pair
    job=Job(args.output/'reports','Shared SDR encoding and validation comparison')
    fixture=args.output/'generated-source.mkv';owned=[fixture];original_probe=auto_optimize.run_probe
    report=dict(production_enabled=False,qualification_installed=False,controls_passed=False,
        package_loader_tested=args.installed_profile,package_loader_passed=False,
        scope='Generated full encode, validation and quality; excludes discovery/trials',
        mean_floor=94,p5_floor=90,measurements=[])
    try:
        report['binary_sha256']=hashlib.sha256(args.binary.read_bytes()).hexdigest()
        profile=dict(binary=str(args.binary.resolve()),scopes=[dict(codec=args.codec,pixel_format=args.pixel_format,
            hdr_modes=['sdr'],full_eof=True,every_frame_cpu_gpu_equal=True,corrupt_controls_rejected=True,time_reduction_percent=1)])
        if args.installed_profile:
            from gpu_frame_reader import load_qualification,select_reader
            profile=load_qualification()
            if (profile is None or profile.get('binary_sha256')!=report['binary_sha256']
                    or Path(profile['binary']).resolve()!=args.binary.resolve()
                    or select_reader(dict(codec_name=args.codec,pix_fmt=args.pixel_format),61,'sdr',profile)['backend']!='cuda'):
                raise ValueError('Installed image/host receipt was not accepted for this SDR scope')
            report['package_loader_passed']=True
        job.save(phase='Generating isolated SDR source with audio')
        subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-filter_threads','2',
            '-f','lavfi','-i','testsrc2=size=1280x720:rate=24:duration=61,format='+args.pixel_format,
            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=61',
            '-map','0:v','-map','1:a','-c:v',args.codec+'_nvenc','-preset','p4','-cq','12',
            '-pix_fmt',args.pixel_format,'-color_primaries','bt709','-color_trc','bt709',
            '-colorspace','bt709','-color_range','tv','-c:a','aac','-b:a','128k',str(fixture)],
            check=True,capture_output=True,timeout=180)
        source_hash=file_digest(fixture);source_bytes=fixture.stat().st_size
        frame_paths={}
        for backend in ('cpu','cuda'):
            directory=args.output/backend;directory.mkdir()
            output=directory/'converted.mkv';owned.append(output)
            settings=SimpleNamespace(hdr_mode=None,ffmpeg='ffmpeg',ffprobe=args.ffprobe,
                timeout=600,vmaf_mean=94,vmaf_p5=90,source=fixture)
            workflow=Workflow(settings,directory,lambda:None)
            workflow.frame_reader_checked=not (args.installed_profile and backend=='cuda')
            workflow.frame_reader_qualification=profile if backend=='cuda' and not args.installed_profile else None
            dispatch=[]
            def observe(command,*arguments,**options):
                if '-show_frames' in command:
                    dispatch.append(dict(native=(options.get('env') or {}).get('MUXMENDER_RESEARCH_CUDA_READER')=='1',
                        complete='-read_intervals' not in command,binary=str(command[0])))
                return original_probe(command,*arguments,**options)
            auto_optimize.run_probe=observe
            started=time.monotonic()
            with isolated_progress(lambda values:job.save(**values)):
                job.save(phase='Shared '+backend+' encode and full validation')
                before=workflow.probe(fixture)
                frames=workflow.frame_file(fixture,'source',before['format']);frame_paths[backend]=frames
                info=auto_optimize.mm.probe(fixture,args.ffprobe)
                workflow.encode_preserving_color(fixture,output,
                    dict(codec=args.codec,encoder=args.codec+'_nvenc',quality='compact',
                         nvenc_cq=24,nvenc_preset='p4'),info,before,'full-encode',61)
                count=workflow.validate(fixture,output,before,args.codec,'converted',frames)
                calibration=workflow.quality(fixture,fixture,'self',count,61)
                quality=workflow.quality(fixture,output,'converted',count,61)
            elapsed=time.monotonic()-started
            if len(dispatch)<2 or any(not d['complete'] or d['native']!=(backend=='cuda') for d in dispatch):
                raise ValueError('Shared workflow did not use the requested full readers')
            output_bytes=output.stat().st_size
            if count!=1464 or not calibration.get('passed') or not quality.get('passed'):
                raise ValueError('Full frame or unchanged quality checks failed')
            if not meets_requirement(source_bytes,output_bytes,requirement(source_bytes)):
                raise ValueError('Generated output missed unchanged savings policy')
            if file_digest(fixture)!=source_hash:raise ValueError('Source changed')
            report['measurements'].append(dict(backend=backend,seconds=elapsed,frames=count,
                dispatch=dispatch,calibration=calibration,quality=quality,source_bytes=source_bytes,
                output_bytes=output_bytes,source_unchanged=True))
        report['exact_pairwise_proof']=exact_pair(frame_paths['cpu'],frame_paths['cuda'])
        cpu,gpu=report['measurements']
        report.update(controls_passed=True,time_reduction_percent=100*(1-gpu['seconds']/cpu['seconds']))
    except Exception as exc:report['error']=str(exc)
    finally:
        auto_optimize.run_probe=original_probe
        # Only this fresh run's owned fixture/output and known frame evidence.
        for backend in ('cpu','cuda'):
            from artifact_manifest import registered_outputs
            directory=args.output/backend
            if directory.is_dir():owned.extend(registered_outputs(directory))
            for name in ('source-frames.jsonl','source-frames.jsonl.stderr','converted-frames.jsonl',
                         'converted-frames.jsonl.stderr','self-vmaf.json','converted-vmaf.json'):
                owned.append(args.output/backend/name)
        removed=0
        try:
            for path in owned:
                if path.is_symlink() or not path.resolve().is_relative_to(args.output.resolve()):
                    raise ValueError('Unsafe generated-artifact cleanup target')
            for path in owned:
                if path.is_file():removed+=path.stat().st_size;path.unlink()
        except Exception as exc:
            report.update(controls_passed=False,cleanup_error=str(exc))
        report['temporary_bytes_removed']=removed
        try:(args.output/'benchmark.json').write_text(json.dumps(report,indent=2))
        except Exception as exc:report.update(controls_passed=False,evidence_error=str(exc))
        job.save(state='completed' if report['controls_passed'] else 'failed',
            phase='Shared comparison completed' if report['controls_passed'] else 'Shared comparison needs investigation',
            detail=json.dumps(report),finished=time.time())
    return 0 if report['controls_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
