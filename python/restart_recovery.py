"""Automatic retry after a recorded service shutdown, never after cancellation.

This restarts the shared workflow; it is not frame- or stage-level checkpointing.
No media is deleted and interrupted publication is never blindly retried.
"""
import copy
import time
import uuid


def mark_shutdown(state):
    for job in state['jobs']:
        if job.get('state')=='running' and not job.get('cancel_requested'):
            job.setdefault('service_restart',dict(requested=time.time(),state='requested'))


def recover(state, check, version):
    """Caller holds the worker lease and queue mutex, then atomically saves."""
    recovered=[]
    for job in list(state['jobs']):
        marker=job.get('service_restart',{})
        if marker.get('state')!='requested':continue
        if job.get('cancel_requested') or job.get('state')=='cancelled':
            marker['state']='cancelled';continue
        if job.get('state') not in ('running','interrupted'):
            marker['state']='finished-before-restart';continue
        try:
            if job.get('publishing') or job.get('publication_only'):
                raise ValueError('Publication must be reconciled before retrying')
            check(job)
            if any(j is not job and j.get('source')==job['source'] and j.get('state') in ('pending','running') for j in state['jobs']):
                raise ValueError('Another request already owns this source')
        except (ValueError,OSError,KeyError) as exc:
            marker.update(state='blocked',reason=str(exc))
            job.update(state='interrupted',reason='Restart recovery needs attention: '+str(exc),finished=time.time())
            state.update(paused=True,pause_origin='restart-recovery')
            continue
        identifier=uuid.uuid4().hex
        retry={key:copy.deepcopy(job[key]) for key in
               ('source','signature','source_identity','settings','batch_id','batch_folder') if key in job}
        retry.update(id=identifier,state='pending',created=time.time(),app_version=version,
                     retry_of=job['id'],restart_of=job['id'],
                     reason='Continuing after app restart; interrupted workflow will restart with all checks.')
        marker.update(state='requeued',retry_id=identifier)
        job.update(state='interrupted',reason='App restarted; automatically continued in request '+identifier,finished=time.time())
        # Retain the old evidence/output directory under its original request ID.
        position=next((i for i,j in enumerate(state['jobs']) if j.get('state')=='pending'),len(state['jobs']))
        state['jobs'].insert(position,retry);recovered.append(identifier)
    return recovered
