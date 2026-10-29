"""Restart a captured cancellation as fresh requests, retaining its history."""
import copy
import time
import uuid

from autonomous_queue import signature


class CancelledQueue:
    def cancelled_scope(self):
        scope=self.state.get('last_queue_cancellation')
        # Older versions did not record cancellation events. Never restore all
        # historical cancellations: offer only the most recently cancelled batch.
        rows=[j for j in self.state['jobs'] if j['state']=='cancelled' and isinstance(j.get('source'),str) and not j.get('removed_from_queue')]
        if not rows:return None
        latest=max(rows,key=lambda j:j.get('cancel_requested_at',j.get('finished',j.get('created',0))))
        if isinstance(scope,dict) and isinstance(scope.get('ids'),list):
            if latest['id'] in scope['ids'] or latest.get('cancel_requested_at',latest.get('finished',latest.get('created',0)))<=scope.get('created',0):return scope
        batch=latest.get('batch_id')
        return dict(id='legacy:'+str(batch or latest['id']),legacy=True,
            ids=[j['id'] for j in rows if j.get('batch_id')==batch] if batch else [latest['id']])

    def restart_idle(self):
        return (not any(j['state'] in ('pending','running') for j in self.state['jobs']) and
                not self.children and not any(w.is_alive() for w in self.workers))

    def cancelled_restart_summary(self):
        scope=self.cancelled_scope()
        ids=set(scope['ids']) if scope else set()
        latest={j['source']:j['id'] for j in self.state['jobs'] if isinstance(j.get('source'),str)}
        count=sum(j['id'] in ids and j['state']=='cancelled' and not j.get('removed_from_queue')
                  and not j.get('queue_restarted_as') and latest.get(j.get('source'))==j['id'] for j in self.state['jobs'])
        return dict(count=count,available=bool(count and self.restart_idle()),legacy=bool(scope and scope.get('legacy')))

    def restart_row(self,job,index):
        if job['state']!='cancelled' or job.get('removed_from_queue') or job.get('queue_restarted_as'):
            raise ValueError('This request is no longer a cancelled job awaiting restart.')
        related=index.get(job['source'],[])
        newer=[j for j in related if j['id']!=job['id'] and j.get('created',0)>=job.get('created',0)]
        if newer:raise ValueError('A newer request already exists for this video. Use that request instead.')
        if not self.recovery_info(job)['retry_allowed']:
            raise ValueError('Publication recovery must be resolved before restarting this video.')
        source=self.resolve(job['source'])
        if signature(source)!=job['signature'] or not self.identity_matches(job,str(source)):
            raise ValueError('The source changed. Select it again to review the new file.')
        if job.get('publication_only'):
            evidence=self.copy_evidence(job)
            if evidence!=job.get('approved_copy'):raise ValueError('The approved copy or its validation evidence changed.')
            return dict(previous_id=job['id'],source=str(source),signature=signature(source),
                source_identity=job.get('source_identity'),settings=copy.deepcopy(job['settings']),
                batch_folder=job.get('batch_folder'),publication_only=True,approved_copy=evidence,
                copy_request_of=job.get('copy_request_of',job['id']))
        settings=self.settings({k:v for k,v in job['settings'].items() if k!='codecs'})
        if settings['mode']=='keep':raise ValueError('Keep-original requests have no processing to restart.')
        settings.update(history_mode='retry',recheck=False)
        self.check_media_access(settings['mode'])
        if settings['mode']=='replace':
            from validated_replace import target_for
            target_for(source,self.media,self.replacement_root)
        previous=self.history_match(str(source),job['signature'],settings,exclude=job['id'],
                                    candidates=related)
        if previous and previous.get('state')!='not-selected':
            raise ValueError('This video already has a completed or active request.')
        from control_service import source_identity
        return dict(previous_id=job['id'],source=str(source),signature=signature(source),
            source_identity=source_identity(source),settings=settings,batch_folder=job.get('batch_folder'))

    def restart_cancelled(self,data):
        # Inspect files without holding up pause, cancellation or live polling.
        with self.mutex:
            if not self.ready or self.stop_event.is_set():raise ValueError('Control worker is not ready or the app is stopping')
            if not self.restart_idle():raise ValueError('Wait for current jobs and cancellation cleanup to finish before restarting.')
            now=time.time()
            drafts=getattr(self,'restart_drafts',{})
            self.restart_drafts={k:v for k,v in drafts.items() if v['expires']>now}
            scope=self.cancelled_scope()
            if not scope:raise ValueError('There is no cancelled queue to restart.')
            if data['action']=='restart-cancelled-preview':
                if len(self.restart_drafts)>=20:raise ValueError('Too many previews; close and try again later.')
                ids=set(scope['ids']);jobs=[copy.deepcopy(j) for j in self.state['jobs'] if j['id'] in ids]
                index=copy.deepcopy(self.history_index())
            else:
                token=data.get('confirmation_id')
                if not isinstance(token,str):raise ValueError('Review the cancelled queue before restarting.')
                draft=self.restart_drafts.get(token)
                if not draft:raise ValueError('Restart preview expired or was already used. Review again.')
                if draft['scope_id']!=scope['id']:raise ValueError('The cancelled queue changed. Review again.')
                if draft['replacement_count'] and data.get('confirm_replace') is not True:
                    raise ValueError('Confirm the original replacement settings before restarting.')
                # The queue is idle, so commit all rechecked rows in one durable
                # write. Never reuse old outputs, STOP files or publication jobs.
                index=self.history_index();records=[]
                by_id={j['id']:j for j in self.state['jobs']}
                for expected in draft['rows']:
                    old=by_id.get(expected['previous_id'])
                    if old is None or self.restart_row(old,index)!=expected:
                        raise ValueError('A request or source changed. Close and review the restart again.')
                    records.append(old)
                if not records:raise ValueError('No cancelled jobs can be restarted.')
                from app_version import VERSION
                updated=copy.deepcopy(self.state);copied={j['id']:j for j in updated['jobs']}
                batch_id=uuid.uuid4().hex;created=[]
                for row,old in zip(draft['rows'],records):
                    identifier=uuid.uuid4().hex
                    updated['jobs'].append(dict(id=identifier,source=row['source'],signature=row['signature'],
                        source_identity=row['source_identity'],settings=row['settings'],state='pending',created=now,
                        batch_id=batch_id,batch_folder=row['batch_folder'],app_version=VERSION,
                        retry_of=old['id'],restarted_cancellation=scope['id']))
                    if row.get('publication_only'):
                        updated['jobs'][-1].update(publication_only=True,approved_copy=row['approved_copy'],
                            copy_request_of=row['copy_request_of'],approved_at=now,
                            output=str(self.root/('request-'+identifier)))
                    copied[old['id']]['queue_restarted_as']=identifier;created.append(identifier)
                updated.update(paused=False,failures=0);updated.pop('pause_origin',None)
                from autonomous_queue import write
                write(self.file,updated)
                self.state=updated;del self.restart_drafts[data['confirmation_id']]
                return dict(queued=len(created),ids=created,batch_id=batch_id,
                    message=f'Restarted {len(created)} cancelled jobs with their original settings. History was kept; processing will start automatically.')
        rows=[];excluded=[]
        for job in jobs:
            if job['state']!='cancelled' or job.get('removed_from_queue') or job.get('queue_restarted_as'):continue
            try:rows.append(self.restart_row(job,index))
            except (OSError,ValueError) as exc:excluded.append(dict(source=job['source'],reason=str(exc)))
        with self.mutex:
            token=uuid.uuid4().hex;replacement_count=sum(r['settings']['mode']=='replace' or r.get('publication_only',False) for r in rows)
            self.restart_drafts[token]=dict(scope_id=scope['id'],rows=rows,expires=now+600,replacement_count=replacement_count)
        return dict(confirmation_id=token,count=len(rows),replacement_count=replacement_count,
            files=[dict(source=r['source'],mode='replace-approved-copy' if r.get('publication_only') else r['settings']['mode']) for r in rows],excluded=excluded,
            legacy=bool(scope.get('legacy')),
            message='Restart uses the previous job settings and creates fresh attempts. Completed jobs are not restarted. Work interrupted during a cancelled file starts again; it does not resume an encoding mid-file.')
