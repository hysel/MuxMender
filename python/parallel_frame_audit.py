"""Optional paired readers using existing complete frame evidence and admission."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

from job_tracking import isolated_progress,progress


def collect_pair(workflow,reference,output,before,*,label='full'):
    from auto_optimize import Workflow
    actual=workflow.probe(output)
    identity=(workflow.audit_identity(reference),workflow.audit_identity(output))
    stop=threading.Event();lock=threading.Lock();states=[{},{}]
    def guard():
        workflow.guard()
        if stop.is_set():raise InterruptedError('Paired frame audit stopped')
    def read(index,source,label,metadata):
        def observe(values):
            with lock:states[index].update(values)
        worker=Workflow(workflow.args,workflow.directory,guard)
        worker.performance_video=workflow.performance_video
        with isolated_progress(observe):
            return worker.frame_file(source,label,metadata)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(read,0,reference,label+'-source',before['format']),
                 pool.submit(read,1,output,label+'-output-paired',actual['format'])]
        try:
            while True:
                guard()
                completed=sum(f.done() for f in futures)
                for future in futures:
                    if future.done():future.result()  # Abort both on the first failure.
                with lock:current=[dict(s) for s in states]
                percentages=[100 if f.done() else s.get('stage_percent')
                             for f,s in zip(futures,current)]
                waiting=completed==0 and all(s.get('phase','').startswith('Waiting for validation') for s in current)
                detail='; '.join(name+': '+('complete' if f.done() else
                    ('waiting for resources' if s.get('phase','').startswith('Waiting for validation') else
                     (f"{s['stage_percent']:.1f}%" if s.get('stage_percent') is not None else 'starting')))
                    for name,f,s in zip(('source','output'),futures,current))
                progress('Checking source and output frames together',completed=completed,total=2,unit='frame readers',
                    stage_percent=sum(percentages)/2 if all(p is not None for p in percentages) else None,
                    detail=detail,performance_category='validation_wait' if waiting else 'frame_validation')
                if completed==2:break
                time.sleep(.25)
            if identity!=(workflow.audit_identity(reference),workflow.audit_identity(output)):
                raise ValueError('Media changed during paired frame validation')
            return futures[0].result(),futures[1].result(),actual
        except BaseException:
            stop.set()
            for future in futures:future.cancel()
            raise
        finally:
            progress('Paired frame readers finished',performance_category=None)
