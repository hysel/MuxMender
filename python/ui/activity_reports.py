"""Read-only outcome reports over the same saved history as the Results view."""
PANEL = '''<section class="panel" id="reports" aria-labelledby="reports-title"><div class="panel-head"><h2 id="reports-title">Activity reports</h2></div><div class="panel-body">
<p class="control-note">What happened to your videos. One latest result per video, including archived results.</p>
<div class="report-overview" role="group" aria-label="Filter activity by outcome">
<button type="button" data-report-group="converted" id="report-converted" aria-pressed="false">Converted · 0</button>
<button type="button" data-report-group="kept" id="report-kept" aria-pressed="false">Original kept · 0</button>
<button type="button" data-report-group="problems" id="report-problems" aria-pressed="false">Needs attention · 0</button>
<button type="button" data-report-group="active" id="report-active" aria-pressed="false">In progress · 0</button></div>
<div class="control-grid"><div><label for="report-outcome">Show</label><select id="report-outcome"><option value="all">All videos</option><option value="converted">Converted</option><option value="kept">Original kept</option><option value="problems">Needs attention</option><option value="active">In progress</option></select></div>
<div><label for="report-search">Find a video or folder</label><input type="search" id="report-search" placeholder="Search videos"></div></div>
<details class="report-options"><summary>History and export</summary>
<label for="report-scope">History</label><select id="report-scope"><option value="latest">Latest result per video</option><option value="attempts">Every attempt, including earlier failures</option></select>
<button type="button" id="report-download">Download matching report (CSV)</button>
<p class="control-note">Exports include all matching records and full media paths. Treat them as private. Copies do not count as reclaimed space.</p></details>
<p id="report-count" role="status" aria-live="polite">Waiting for history…</p><p id="report-freshness" class="control-note"></p>
<div id="report-rows" class="report-list" role="list" aria-label="Video activity, newest first"></div>
<button type="button" id="report-more" hidden>Show more report rows</button></div></section>'''

SCRIPT = r'''<script>
let reportLimit=25,reportMatched=[],reportSignature='';
const reportCards=new Map(),reportGroups={converted:'Converted',kept:'Original kept',problems:'Needs attention',active:'In progress'};
function reportGroup(j){const c=outcomeCategory(j);return ['replaced','copies'].includes(c)?'converted':['errors','attention'].includes(c)?'problems':c==='active'?'active':'kept'}
const reportLabels={replaced:'Successful replacement',copies:'Validated copy — original retained',benefit:'Unchanged — size or quality checks not met',errors:'Error / interrupted',cancelled:'Cancelled',attention:'Needs attention',other:'Kept / inspected / tested',active:'Queued / running'};
function reportRows(rows,scope,category,query){
 const selected=scope==='attempts'?rows:groupedAttempts(rows.filter(j=>!j.superseded_by)).map(g=>g.latest);
 return sortedResults(selected.filter(j=>(category==='all'||(category in reportGroups?reportGroup(j)===category:outcomeCategory(j)===category))&&String(j.source||'').toLowerCase().includes(query.toLowerCase())),'newest');
}
function reportReason(j){
 const reason=String(j.reason||j.error||j.detail||'');
 if(/source audio preflight|quant_step_size/i.test(reason))return userReason(j);
 if(/Dolby Vision|confirmed RPU/i.test(reason)&&reportGroup(j)==='problems')return 'Dolby Vision information needs inspection. Original kept.';
 if(j.state==='replaced')return 'The validated smaller file replaced the original.';
 if(outcomeCategory(j)==='copies')return 'A validated copy is ready. The original is still in place.';
 if(j.state==='pending')return 'Waiting for a processing slot.';
 if(j.state==='running')return friendlyStage(j.phase)||'Processing this video.';
 return userReason(j);
}
function reportDate(j){const t=outcomeTime(j);return t?new Date(t*1000).toISOString():'Not recorded'}
function csvCell(value){let s=String(value??'');if(/^[\s]*[=+@-]/.test(s)||/^[\t\r\n]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'}
function activityCsv(rows){const header=['File','Activity','State','Outcome date (UTC)','Reason','Original bytes','Output bytes','Confirmed replacement reduction bytes','Request ID','App version'];
 const records=rows.map(j=>[j.source,reportLabels[outcomeCategory(j)],j.state,reportDate(j),j.reason||j.error||j.detail||userReason(j),sourceBytes(j),j.output_bytes,j.state==='replaced'?j.saved_bytes:'',j.requestId||j.id,j.app_version]);
 return [header,...records].map(r=>r.map(csvCell).join(',')).join('\r\n');
}
function renderActivityReports(rows){
 reportMatched=reportRows(rows,userEl('report-scope').value||'latest',userEl('report-outcome').value||'all',userEl('report-search').value||'');
 const counts={};for(const j of reportRows(rows,userEl('report-scope').value||'latest','all',userEl('report-search').value||'')){const c=reportGroup(j);counts[c]=(counts[c]||0)+1}
 for(const [key,label] of Object.entries(reportGroups)){const button=userEl('report-'+key);button.textContent=label+' · '+(counts[key]||0);button.setAttribute('aria-pressed',String(userEl('report-outcome').value===key))}
 userEl('report-count').textContent=reportMatched.length+' '+(userEl('report-scope').value==='attempts'?'attempts':'videos')+' · newest first';
 userEl('report-freshness').textContent=controlsConnected?'Based on loaded saved history; updated '+new Date(lastControlsUpdate).toLocaleString():'Connection unavailable — this report may be stale.';
 const shown=reportMatched.slice(0,reportLimit),signature=JSON.stringify(shown);
 if(signature!==reportSignature){reportSignature=signature;const body=userEl('report-rows'),wanted=[];
  for(const j of shown){const key=j.id||j.requestId||j.source;let card=reportCards.get(key);
   if(!card){const node=userNode('article',null,'report-card');node.setAttribute('role','listitem');
    const head=userNode('div',null,'report-card-head'),name=userNode('h3'),badge=userNode('span',null,'report-badge'),date=userNode('time',null,'control-note'),reason=userNode('p'),size=userNode('p',null,'control-note'),details=userNode('details'),path=userNode('p',null,'report-path'),technical=userNode('p',null,'report-path');
    head.append(name,badge);details.append(userNode('summary','Details'),path,technical);node.append(head,date,reason,size,details);card={node,name,badge,date,reason,size,path,technical};reportCards.set(key,card)}
   card.name.textContent=resultName(j);card.badge.textContent=userStatus(j.state);card.node.setAttribute('data-outcome',reportGroup(j));
   const timestamp=outcomeTime(j);card.date.textContent=timestamp?new Date(timestamp*1000).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):'Date not recorded';if(timestamp)card.date.setAttribute('datetime',reportDate(j));
   card.reason.textContent=reportReason(j);card.size.textContent=sizeSummary(j)+(j.state==='replaced'&&Number.isFinite(j.saved_bytes)?' · Library reduced by '+fileSizeText(j.saved_bytes):'');
   card.path.textContent=j.source||'';card.technical.textContent=j.reason||j.error||j.detail||'';wanted.push(card.node);
  }
  for(const child of [...body.children])if(!wanted.includes(child))child.remove();
  wanted.forEach((node,i)=>{if(body.children[i]!==node)body.insertBefore(node,body.children[i]||null)});
  if(!wanted.length)body.append(userNode('p','No videos match. Try another category or search.','control-note'));
  const visible=new Set(shown.map(j=>j.id||j.requestId||j.source));for(const key of reportCards.keys())if(!visible.has(key))reportCards.delete(key);
 }
 userEl('report-more').hidden=reportMatched.length<=reportLimit;
 userEl('report-download').disabled=!reportMatched.length;
}
function wireActivityReports(){
 for(const id of ['report-outcome','report-scope','report-search'])userEl(id).addEventListener(id==='report-search'?'input':'change',()=>{reportLimit=25;renderActivityReports(mergedResults())});
 for(const key of Object.keys(reportGroups))userEl('report-'+key).addEventListener('click',()=>{userEl('report-outcome').value=userEl('report-outcome').value===key?'all':key;reportLimit=25;renderActivityReports(mergedResults())});
 userEl('report-more').addEventListener('click',()=>{reportLimit+=25;renderActivityReports(mergedResults())});
 userEl('report-download').addEventListener('click',()=>{const blob=new Blob(['\ufeff',activityCsv(reportMatched)],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='muxmender-activity-'+new Date().toISOString().replaceAll(':','-')+'.csv';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)});
}
</script>'''

STYLE = '''<style>.report-overview{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:24px}.report-overview button{min-height:64px;text-align:left;font-weight:600}.report-overview button[aria-pressed=true]{outline:3px solid var(--accent);outline-offset:2px}.report-options{margin:16px 0}.report-options select,.report-options button{margin:12px 12px 0 0}.report-list{display:grid;gap:12px;margin-top:16px}.report-card{border:1px solid var(--border);border-radius:12px;padding:20px;min-width:0}.report-card-head{display:flex;align-items:baseline;justify-content:space-between;gap:16px}.report-card h3{margin:0 0 8px;overflow-wrap:anywhere;font-size:1rem}.report-card p{margin:10px 0}.report-badge{font-weight:600;white-space:nowrap}.report-card[data-outcome=problems]{border-inline-start:4px solid var(--text)}.report-path{overflow-wrap:anywhere;white-space:pre-wrap}.report-card details{margin-top:12px}.report-card summary,.report-options summary{cursor:pointer;min-height:32px}.report-overview button:focus-visible,.report-card summary:focus-visible,.report-options summary:focus-visible{outline:3px solid var(--accent);outline-offset:3px}@media(max-width:700px){.report-overview{grid-template-columns:repeat(2,minmax(0,1fr))}.report-card-head{flex-direction:column;gap:0}.report-card{padding:16px}}</style>'''
