"""Generated shared-workflow CPU/NVDEC encode, preservation and quality comparison."""
import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux qualification only')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ffmpeg',required=True);parser.add_argument('--ffprobe',required=True)
    parser.add_argument('--controls-status',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(exist_ok=False,parents=True)
    from job_tracking import Job,isolated_progress
    from auto_optimize import Workflow,mm
    from task_progress import digest
    job=Job(args.output/'reports','Shared workflow GPU input qualification')
    report=dict(production_enabled=False,generated_only=True,outputs={})
    source=args.output/'generated-av1.mkv';paths=[source]
    def guard():
        state=json.loads(args.controls_status.read_text())
        if not state.get('ready') or not 0<=time.time()-state.get('updated',0)<=12 or any(state['counts'].get(k,0) for k in ('pending','running')):
            raise RuntimeError('Fresh production-idle proof unavailable; isolated research stopped')
    try:
        options=SimpleNamespace(ffmpeg=args.ffmpeg,ffprobe=args.ffprobe,timeout=180,
                                vmaf_mean=94,vmaf_p5=90,source=source,output_preset='original')
        work=Workflow(options,args.output,guard)
        with isolated_progress(lambda values:job.save(**values)):
            work.execute([args.ffmpeg,'-hide_banner','-nostdin','-v','error','-n','-f','lavfi','-i',
                          'testsrc2=size=1920x1080:rate=24:duration=20','-c:v','av1_nvenc','-preset','p5',
                          '-cq','20','-b:v','0','-pix_fmt','yuv420p','-color_primaries','bt709',
                          '-color_trc','bt709','-colorspace','bt709','-color_range','tv',str(source)],'Generate fixture',20)
            source_hash=digest(source,guard)
            before=work.probe(source);info=mm.probe(source,args.ffprobe)
            frames=work.frame_file(source,'source',before['format'])
            for mode in ('cpu','cuda'):
                options.research_gpu_encode_input=mode=='cuda'
                output=args.output/(mode+'.mkv');paths.append(output)
                start=time.monotonic()
                work.encode_preserving_color(source,output,dict(codec='av1',encoder='av1_nvenc',quality='balanced',nvenc_cq=25),info,before,mode+'-encode',20)
                elapsed=time.monotonic()-start
                count=work.validate(source,output,before,'av1',mode,frames)
                quality=work.quality(source,output,mode,count,20)
                if count!=480 or not quality.get('passed'):raise RuntimeError(mode+' shared quality/preservation checks failed')
                report['outputs'][mode]=dict(encode_seconds=elapsed,frames=count,quality=quality,bytes=output.stat().st_size)
            if digest(source,guard)!=source_hash:raise RuntimeError('Generated source changed')
            report['source_unchanged']=True
    except Exception as exc:report['error']=str(exc)
    finally:
        removed=0
        for path in paths:
            if path.is_file() and not path.is_symlink():removed+=path.stat().st_size;path.unlink()
        report['temporary_bytes_removed']=removed
        (args.output/'qualification.json').write_text(json.dumps(report,indent=2))
        job.save(state='failed' if 'error' in report else 'completed',phase='Shared encode qualification finished',detail=json.dumps(report),finished=time.time())
    return int('error' in report)


if __name__=='__main__':raise SystemExit(main())
