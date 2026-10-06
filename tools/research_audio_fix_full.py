"""Serial, read-only-source qualification of two historical audio mux failures."""
import json
import os
from pathlib import Path
import sys
import time


def run_cases(root,job):
    from auto_optimize import main as convert
    from media_workflow import automatic_arguments
    os.nice(10)
    requests=json.loads(Path('/output/ui-requests/requests.json').read_text())['jobs']
    if any(j.get('state') in ('pending','running') for j in requests):
        raise RuntimeError('Keep the production queue idle during isolated GPU qualification')
    results=[]
    for number,identifier in enumerate(('8e26c17d027541ebb7634387e659589c','2dc99ebad7aa4c87a2104dc24282dea9')):
        request=next(j for j in requests if j['id']==identifier)
        source=Path(request['source']).resolve(strict=True)
        if not source.is_relative_to('/media'):raise ValueError('Source outside read-only media mount')
        info=source.stat();identity=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
        output=root/'cases'/('case-'+str(number));output.mkdir(parents=True,exist_ok=False)
        job.save(phase='Full conversion and validation: case '+str(number+1),completed=number,total=2,
                 detail='Serial NVIDIA work; original resolution; unchanged 90/90 quality checks; no publication')
        settings=dict(mode='encode',hardware='nvidia',quality='auto',output_preset='original',hdr_policy='preserve',
                      codecs=['hevc'] if number==0 else ['hevc','av1'],minimum_savings=25,savings_mode='size-aware')
        code=convert(automatic_arguments(source,output,settings,min_free_gib=8))
        latest=source.stat()
        if identity!=(latest.st_dev,latest.st_ino,latest.st_size,latest.st_mtime_ns):
            raise ValueError('Source identity changed during qualification')
        paths=list(output.glob('*/status.json'))
        states=[json.loads(p.read_text()) for p in paths]
        passed=any(s.get('state')=='validated-copy-awaiting-playback' for s in states)
        results.append(dict(case=number,exit_code=code,full_validation_passed=passed,
                            source_stat_unchanged=True,states=[s.get('state') for s in states]))
        (root/'full-qualification-result.json').write_text(json.dumps(dict(results=results,publication_authorized=False),indent=2))
    success=all(r['exit_code']==0 and r['full_validation_passed'] for r in results)
    job.save(state='completed' if success else 'failed',phase='Full-source qualification finished',
             completed=2,total=2,finished=time.time(),detail=json.dumps(results))
    return 0 if success else 1


def main(root):
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only qualification')
    root=Path(root).resolve(strict=True)
    sys.path[:0]=[str(root/'python')]
    from job_tracking import Job
    job=Job(root/'reports','Full-source audio mux fix qualification')
    try:return run_cases(root,job)
    except BaseException as exc:
        job.save(state='failed',phase='Full-source qualification needs inspection',error=str(exc),finished=time.time())
        raise


if __name__=='__main__':raise SystemExit(main(Path(__file__).resolve().parent))
