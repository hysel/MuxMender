"""Review and restart a cancelled queue without selecting its folders again."""
HTML='''<dialog id="queue-restart-dialog" aria-labelledby="queue-restart-title" aria-describedby="queue-restart-description">
<div class="queue-dialog-heading"><h2 id="queue-restart-title">Restart cancelled jobs?</h2><button id="queue-restart-close" type="button" aria-label="Close restart cancelled jobs dialog">×</button></div>
<p id="queue-restart-description" role="status">Checking the cancelled jobs…</p>
<p id="queue-restart-policy"></p><details><summary>Videos and exclusions</summary><ul id="queue-restart-files" class="restart-files" tabindex="0" aria-label="Cancelled jobs and exclusions"></ul></details>
<p id="queue-restart-error" role="alert"></p><div class="control-actions"><button id="queue-restart-back" type="button" autofocus>Go back</button><button id="queue-restart-confirm" type="button" disabled>Restart jobs</button></div>
</dialog><style>.restart-files{max-height:240px;overflow:auto;padding-left:22px}.restart-files li{overflow-wrap:anywhere;margin:6px 0}</style>'''

SCRIPT=r'''<script>
let restartGeneration=0,restartDraft=null,restartBusy=false;
function renderCancelledRestart(body,unavailable=false){
 const button=controlElement('restart-cancelled-queue');if(!button)return;
 const summary=body?.cancelled_queue_restart,hasWork=(body?.counts?.running||0)+(body?.counts?.pending||0)>0;
 button.hidden=hasWork||!summary?.count;
 button.disabled=unavailable||!body?.ready||!summary?.available||queueActionBusy||restartBusy;
 button.title=button.disabled?'Wait for jobs and cancellation cleanup to finish, and for the queue connection to be available.':'Review and restart the last cancelled queue using its previous settings';
}
function closeRestartDialog(){restartGeneration++;restartDraft=null;if(!queueActionBusy)restartBusy=false;controlElement('queue-restart-dialog').close();renderCancelledRestart(lastQueueControl,queueStatusUnavailable);const button=controlElement('restart-cancelled-queue');if(!button.hidden&&!button.disabled)button.focus({preventScroll:true})}
controlElement('restart-cancelled-queue').addEventListener('click',async()=>{
 if(restartBusy||controlElement('restart-cancelled-queue').disabled)return;
 const generation=++restartGeneration;restartBusy=true;restartDraft=null;
 const dialog=controlElement('queue-restart-dialog'),confirm=controlElement('queue-restart-confirm');
 confirm.disabled=true;controlElement('queue-restart-description').textContent='Checking the cancelled jobs…';
 controlElement('queue-restart-policy').textContent='';controlElement('queue-restart-error').textContent='';controlElement('queue-restart-files').replaceChildren();
 dialog.showModal();
 try{
  const body=await controlCall('restart-cancelled-preview');
  if(generation!==restartGeneration||!dialog.open)return;
  restartDraft=body;
  controlElement('queue-restart-description').textContent=body.count?'Restart '+body.count+' cancelled '+(body.count===1?'job':'jobs')+' with the previous settings?':'No cancelled jobs can be restarted. See the exclusions below.';
  controlElement('queue-restart-policy').textContent=body.message+(body.replacement_count?' '+body.replacement_count+' '+(body.replacement_count===1?'job will replace its original':'jobs will replace their originals')+' only after full validation and verified publication.':'')+(body.legacy?' Older history: only the most recently cancelled batch is available.':'');
  const names={analyze:'Inspect',test:'Test samples',encode:'Create smaller copy',replace:'Replace after validation','replace-approved-copy':'Publish approved copy without re-encoding'};
  for(const row of body.files||[]){const li=document.createElement('li');li.textContent=String(row.source).split(/[\\/]/).pop()+' · '+(names[row.mode]||row.mode);controlElement('queue-restart-files').append(li)}
  for(const row of body.excluded||[]){const li=document.createElement('li');li.textContent=String(row.source).split(/[\\/]/).pop()+' · Not restarted: '+row.reason;controlElement('queue-restart-files').append(li)}
  confirm.textContent='Restart '+body.count+' '+(body.count===1?'job':'jobs');confirm.disabled=!body.count;
 }catch(error){if(generation===restartGeneration)controlElement('queue-restart-error').textContent=error.message}
 finally{if(generation===restartGeneration)restartBusy=false;renderCancelledRestart(lastQueueControl,queueStatusUnavailable)}
});
for(const id of ['queue-restart-close','queue-restart-back'])controlElement(id).addEventListener('click',closeRestartDialog);
controlElement('queue-restart-dialog').addEventListener('cancel',event=>{event.preventDefault();closeRestartDialog()});
controlElement('queue-restart-dialog').addEventListener('close',()=>{restartGeneration++;restartDraft=null});
controlElement('queue-restart-dialog').addEventListener('click',event=>{
 const dialog=controlElement('queue-restart-dialog');if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();
 if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeRestartDialog();
});
controlElement('queue-restart-confirm').addEventListener('click',async()=>{
 if(restartBusy||queueActionBusy||!restartDraft?.count)return;
 const draft=restartDraft;restartBusy=true;queueActionBusy=true;queueActionVersion++;queueActionError='';
 controlElement('queue-restart-confirm').disabled=true;
 try{
  const body=await controlCall('restart-cancelled-confirm',{confirmation_id:draft.confirmation_id,confirm_replace:!!draft.replacement_count});
  if(lastQueueControl)lastQueueControl={...lastQueueControl,paused:false,counts:{...lastQueueControl.counts,pending:body.queued},cancelled_queue_restart:{count:0,available:false}};
  closeRestartDialog();controlMessage(body.message);
  controlElement('queue-clear-feedback').textContent=body.message;
  if(typeof collapseSubmittedSetup==='function')collapseSubmittedSetup(body);
 }catch(error){if(controlElement('queue-restart-dialog').open)controlElement('queue-restart-error').textContent=error.message;else controlMessage(error.message)}
 finally{restartBusy=false;queueActionBusy=false;renderQueueActions(lastQueueControl,queueStatusUnavailable);refreshControls()}
});
</script>'''
