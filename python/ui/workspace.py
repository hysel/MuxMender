"""Accessible end-user presentation; technical details are progressive disclosure."""
STYLE = '''<style>
:root{color-scheme:light;--bg:#f4f6f9;--panel:#ffffff;--text:#182230;--muted:#475569;--border:#64748b;--soft:#eaf3e2;--accent:#d2efab;--accent-text:#18320c;--focus:#005fcc;--danger:#99251d;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:16px;line-height:1.55}
:root[data-theme=dark]{color-scheme:dark;--bg:#0f172a;--panel:#182338;--text:#f1f5f9;--muted:#b5c2d5;--border:#8191a8;--soft:#22342a;--accent:#d2efab;--accent-text:#18320c;--focus:#93c5fd;--danger:#ffc2b9}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;--bg:#0f172a;--panel:#182338;--text:#f1f5f9;--muted:#b5c2d5;--border:#8191a8;--soft:#22342a;--accent:#d2efab;--accent-text:#18320c;--focus:#93c5fd;--danger:#ffc2b9}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text)}[hidden]{display:none!important}button,input,select,summary{font:inherit}button,select,summary{cursor:pointer}button,input,select{min-height:44px;border:1px solid var(--border);border-radius:8px;background:var(--panel);color:var(--text);padding:9px 14px;max-width:100%}button{white-space:normal}button:disabled{cursor:not-allowed;opacity:.65}button:hover:not(:disabled),summary:hover{background:var(--soft)}input,select{width:100%}a{color:inherit;text-underline-offset:4px}a:hover{text-decoration-thickness:2px}*:focus-visible{outline:3px solid var(--focus);outline-offset:3px}h1,h2,h3,p{margin-top:0}h1{font-size:clamp(1.8rem,4vw,2.7rem);line-height:1.15;letter-spacing:-.035em;margin-bottom:14px}h2{font-size:1.25rem;margin:0}h3{font-size:1.1rem}label{display:block;font-weight:600;margin:12px 0 6px}.masthead{max-width:1160px;margin:auto;display:flex;align-items:center;gap:28px;flex-wrap:wrap;padding:22px 24px}.brand{font-weight:800;font-size:1.4rem;text-decoration:none}.masthead nav{display:flex;gap:20px;flex:1;flex-wrap:wrap}.masthead nav a{padding:10px 0}.theme-control{display:flex;align-items:center;gap:10px}.theme-control label{margin:0;font-size:.9rem}.theme-control select{width:auto}main{max-width:1100px;margin:auto;padding:12px 24px 40px}.page-heading{padding:20px 0 24px}.eyebrow{font-size:.78rem;letter-spacing:.13em;font-weight:700;color:var(--muted)}.safety-note{color:var(--muted);font-weight:600}.panel{border:1px solid var(--border);background:var(--panel);border-radius:14px;margin-bottom:24px;min-width:0}.panel-head{display:flex;justify-content:space-between;gap:14px;align-items:center;flex-wrap:wrap;padding:20px 24px;border-bottom:1px solid var(--border)}.guide-content,.panel-body{padding:24px}.badge{font-size:.85rem;background:var(--soft);border-radius:6px;padding:5px 10px;font-weight:600}.control-note,#control-availability{font-size:.9rem;color:var(--muted)}.control-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px}.control-actions{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.primary{background:var(--accent);color:var(--accent-text);font-weight:700}.folder-workspace{background:var(--soft);border-left:4px solid var(--border);border-radius:8px;padding:20px}.folder-workspace h3,.result-card h3{overflow-wrap:anywhere}.folder-picker{border:1px solid var(--border);padding:20px;border-radius:8px;margin-top:20px}.browser-list{max-height:320px;overflow:auto;margin-top:12px}.browser-row button{width:100%;text-align:left;margin-bottom:6px;overflow-wrap:anywhere}.control-advanced{border-top:1px solid var(--border);margin-top:20px;padding-top:12px}summary{min-height:44px;padding:10px 4px;font-weight:600}.control-preview{margin-top:20px;border:2px solid var(--border);background:var(--soft);border-radius:8px;padding:20px}.control-preview ul{max-height:240px;overflow:auto;padding-left:22px}.control-preview li{overflow-wrap:anywhere;margin-bottom:5px}.control-feedback{white-space:pre-wrap;overflow-wrap:anywhere;margin:16px 0 0}.control-feedback:empty{display:none}.result-card{border-top:1px solid var(--border);padding:22px 0}.result-card:first-child{margin-top:16px}.result-header{display:flex;align-items:start;justify-content:space-between;gap:16px;flex-wrap:wrap}.result-card h3{margin-bottom:6px}.result-card p{margin-bottom:8px}.result-card .reason{font-weight:600}.result-meta{color:var(--muted);font-size:.9rem}.result-card details{margin-top:10px}.result-card pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto;border:1px solid var(--border);padding:14px;border-radius:8px}.attention{color:var(--danger)}.metrics{display:flex;flex-wrap:wrap;gap:24px}.metrics p{margin:12px 0}.metrics strong{display:block;font-size:1.25rem}.help summary{padding:20px 24px}.help .panel-body{padding-top:0}footer{color:var(--muted);font-size:.85rem}.skip-link{position:absolute;top:-100px;left:16px;background:var(--panel);padding:12px;z-index:5}.skip-link:focus{top:8px}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:650px){main{padding:8px 12px 24px}.masthead{padding:16px 12px;gap:12px}.masthead nav{order:3;flex-basis:100%}.theme-control{margin-left:auto}.control-grid{grid-template-columns:minmax(0,1fr);gap:8px}.guide-content,.panel-body,.panel-head{padding:16px}.folder-picker{padding:12px}.control-actions button{flex:1 1 160px}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}@media(forced-colors:active){button,.panel,.badge,.folder-workspace{border:1px solid ButtonText}*:focus-visible{outline:3px solid Highlight}}
/* Allow long media names to wrap at every layout boundary, including summaries. */
main,.panel,.panel-body,.guide-content,.control-grid>*,.result-header>*,#current-work,details{min-width:0;max-width:100%}
h3,p,summary,.result-meta,#connection-state{overflow-wrap:anywhere}
.page-heading{padding:8px 0 12px}.page-heading h1{font-size:1.6rem;margin-bottom:6px}.page-heading p{margin-bottom:10px}
.sr-only{left:0;top:0;clip-path:inset(50%)}
input[type=checkbox]{width:24px;min-height:24px;vertical-align:middle;margin-right:8px}
.savings-hero{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:28px 32px;background:var(--soft);border-color:var(--border)}.savings-hero>div{min-width:0}.savings-number{font-size:clamp(2.6rem,7vw,5.5rem);font-weight:800;letter-spacing:-.045em;line-height:1.1;margin:8px 0 16px;overflow-wrap:anywhere}.savings-symbol{font-size:6rem;line-height:1;color:var(--text)}.savings-hero .control-note{max-width:65ch;margin-bottom:0}@media(max-width:650px){.savings-hero{padding:20px}.savings-symbol{display:none}}
.active-job{border:1px solid var(--border);border-radius:12px;padding:18px;margin:12px 0}.active-job h3{margin:0;overflow-wrap:anywhere}.stage-title{font-size:1.15rem;font-weight:700;margin:8px 0}.stage-list{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:12px 0}.stage-list li{padding:5px 10px;border:1px solid var(--border);border-radius:6px;color:var(--muted)}.stage-list .current-step{background:var(--accent);color:var(--accent-text);font-weight:700;border:2px solid var(--focus)}.check-progress{font-weight:700;margin:8px 0}.active-job details{margin-top:8px}.active-job summary{cursor:pointer}#activity{scroll-margin-top:16px}
</style>'''

SCRIPT = r'''<script>
const userEl=id=>document.querySelector('#'+id),userNode=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n};
let catalogJobs=[],requestJobs=[],resultLimit=20,lastAnnouncement='',resultSignature='',queueState={};
const resultCards=new Map();
globalThis.liveUpdatesPaused=false;
function applyTheme(value){if(!['system','light','dark'].includes(value))value='system';document.documentElement?.setAttribute('data-theme',value);try{localStorage.setItem('muxmender-theme',value)}catch(e){}userEl('theme').value=value}
try{applyTheme(localStorage.getItem('muxmender-theme')||'system')}catch(e){applyTheme('system')}
userEl('theme').addEventListener('change',()=>applyTheme(userEl('theme').value));
userEl('toggle-updates').addEventListener('click',()=>{globalThis.liveUpdatesPaused=!globalThis.liveUpdatesPaused;userEl('toggle-updates').setAttribute('aria-pressed',String(globalThis.liveUpdatesPaused));userEl('toggle-updates').textContent=globalThis.liveUpdatesPaused?'Resume live updates':'Pause live updates';userEl('connection-state').textContent=globalThis.liveUpdatesPaused?'Display paused · jobs continue':'Reconnecting…';if(!globalThis.liveUpdatesPaused){refreshUserJobs();if(typeof refreshControls==='function')refreshControls()}});
function userReason(job){const raw=String(job.reason||job.detail||job.error||'');const s=job.state;
 if(s==='replaced')return 'Original replaced after automated checks and verified copying. No playback review was required.';
 if(raw.startsWith('Unsupported input:'))return raw;
 if(['verified','awaiting-playback','playback-approved'].includes(s))return 'Automated checks passed. Review playback before replacing the original.';
 if(s==='kept-original')return 'You chose to keep the original. No conversion was started.';
 if(s==='skipped'){
 if(job.decision_code==='already_efficient_for_settings'||raw.startsWith('Already efficient for current settings:'))return raw;
 if(raw.startsWith('Already processed'))return raw+'; saved history avoided repeating the work.';
 if(/destination.*(?:exists|appeared)|filename.*conflict/i.test(raw))return raw;
 const quality=/quality_pass|quality.*(?:fail|not met|threshold)/i.test(raw),size=/insufficient_savings|did not.*sav|savings requirement|savings threshold/i.test(raw);
 if(/unsupported|not supported|HDR|Dolby Vision/i.test(raw))return 'Original kept: this video format is not supported by the selected workflow.';
 if(quality&&size)return 'Original kept: none of the tested settings met both quality and space-saving requirements.';
 if(quality)return 'Original kept: the tested conversion did not pass quality checks.';
 if(size)return 'Original kept: the tested conversion would not save enough space.';
 return 'Original kept: no tested conversion met the requirements.';
 }
 if(s==='analyzed')return 'Inspection finished. No video was converted. Open details for the plan.';
 if(s==='tested')return 'Sample tests passed. No full video was created. Choose Create smaller copies to continue.';
 if(s==='pending')return 'Waiting for its turn. Originals remain protected.';
 if(s==='running')return 'Processing a separate copy. The original is unchanged.';
 if(s==='interrupted')return 'Processing was interrupted. Inspect details and any publication recovery journal before retrying.';
 if(['failed','stale','unknown','completed-with-errors'].includes(s))return raw.startsWith('Replacement needs attention:')?raw+' Inspect the publication journal; the source path may already contain the new copy.':'Processing needs attention. Open details for the recorded reason.';
 return raw||'Processing finished. Open details to check the outcome.';
}
function userStatus(state){return ({replaced:'Replaced',pending:'Queued',running:'Running',verified:'Ready for review','awaiting-playback':'Ready for review','playback-approved':'Playback approved',skipped:'Original kept','kept-original':'Original kept',analyzed:'Inspection complete',tested:'Samples tested',completed:'Finished — review details',failed:'Needs attention',interrupted:'Interrupted',stale:'Update overdue',unknown:'Needs attention'})[state]||'Needs attention'}
function resultGroup(state){return state==='replaced'?'replaced':['pending','running'].includes(state)?'active':['verified','awaiting-playback','playback-approved'].includes(state)?'ready':['skipped','kept-original'].includes(state)?'kept':['analyzed','tested','completed'].includes(state)?'complete':'attention'}
function sizeSummary(job){return Number.isFinite(job.original_bytes)&&Number.isFinite(job.output_bytes)?(job.original_bytes/1e9).toFixed(2)+' GB → '+(job.output_bytes/1e9).toFixed(2)+' GB · '+(100*(1-job.output_bytes/job.original_bytes)).toFixed(1)+'% smaller':''}
function friendlyStage(value){const s=String(value||'');if(s==='full-encode')return 'Creating the full video copy';if(s==='full-decode')return 'Checking the full copy plays without decode errors';if(s.includes('Checking frame timing'))return 'Checking resolution and frame timing';if(s.includes('Checking copied track'))return 'Verifying audio or subtitles';if(s.includes('self-'))return 'Checking the quality measurement';if(s.includes('quality'))return 'Measuring visual quality';if(/nvenc|amf|qsv|vaapi/.test(s))return 'Comparing encoding options';return s.replaceAll('-',' ')||'Preparing the video'}
function workflowStep(value){const s=String(value||'').toLowerCase();if(/publish|publication|staged|flushing/.test(s))return 'Replacement · copying and verifying publication';if(s==='full-encode')return 'Encoding · creating a separate full copy';if(/full-|frame|track|timestamp|digest|hash|verif/.test(s))return 'Validation · checking integrity and preservation';return 'Inspection / sample trials · testing candidates'}
function stagePresentation(job){
 const labels={inspect:'Inspect',compare:'Compare options',encode:'Encode',validate:'Validate',publish:'Replace',cleanup:'Clean up'};
 const mode=job.settings?.mode;
 const steps=mode==='analyze'?['inspect']:mode==='test'?['inspect','compare']:mode==='replace'?Object.keys(labels):['inspect','compare','encode','validate'];
 let stage=job.workflow_stage;
 if(!steps.includes(stage)){const p=String(job.phase||'').toLowerCase();stage=/cleaning completed/.test(p)?'cleanup':/publish|publication|flushing/.test(p)?'publish':p==='full-encode'?'encode':/^full-|checking frame timing|checking copied track/.test(p)?'validate':/nvenc|amf|qsv|reference-|quality|trial/.test(p)?'compare':null}
 const index=steps.indexOf(stage),pct=job.stage_percent;
 const percent=Number.isFinite(pct)&&pct>=0&&pct<=100?pct:null;
 return {steps,labels,index,stage,title:index<0?'Preparing · stage not reported':'Step '+(index+1)+' of '+steps.length+' · '+labels[stage],
         check:percent===null?'Current check: measuring':percent===100?'Current check complete · finishing this stage':'Current check: '+percent.toFixed(0)+'%'};
}
function renderActiveCard(job){
 const card=userNode('article',null,'active-job'),view=stagePresentation(job);
 card.append(userNode('h3',resultName(job)),userNode('p',view.title,'stage-title'));
 const steps=userNode('ol',null,'stage-list');steps.setAttribute('aria-label','Workflow stages');
 view.steps.forEach((stage,index)=>{const item=userNode('li',(index+1)+'. '+view.labels[stage]);if(index===view.index){item.setAttribute('aria-current','step');item.className='current-step'}steps.append(item)});
 card.append(steps,userNode('p',view.check,'check-progress'),userNode('p',friendlyStage(job.phase),'control-note'));
 const timing=userNode('p',null,'result-meta');
 timing.textContent=(Number.isFinite(job.started)?'Elapsed '+Math.max(0,Math.floor((Date.now()/1000-job.started)/60))+' min':'')+
   (Number.isFinite(job.stage_eta)?' · Current check ETA '+Math.max(1,Math.ceil(job.stage_eta/60))+' min':'');
 card.append(timing);
 if(Number.isFinite(job.updated)&&Date.now()/1000-job.updated>30)card.append(userNode('p','Update overdue · last reported progress may be stale','attention'));
 const detail=userNode('details');detail.append(userNode('summary','Technical details'));
 if(job.detail)detail.append(userNode('p',job.detail,'control-note'));
 detail.append(userNode('p','Percent and ETA apply to the current check only. Stages contain multiple checks; their durations are not equal.','control-note'));
 const measured=Object.entries(job.performance_seconds||{}).filter(([,v])=>Number.isFinite(v)&&v>0);
 for(const [name,seconds] of measured)detail.append(userNode('p',name.replaceAll('_',' ')+': '+Math.round(seconds)+' sec'));
 card.append(detail);return card;
}
function mergedResults(){const rows=requestJobs.map(job=>{const detail=catalogJobs.filter(c=>(String(c.directory).replaceAll('\\','/')+'/').includes('request-'+job.id+'/')).sort((a,b)=>(b.updated||b.started||0)-(a.updated||a.started||0))[0];return {...detail,...job,phase:detail?.phase,workflow_stage:detail?.workflow_stage,stage_started:detail?.stage_started,updated:detail?.updated,stage_percent:detail?.stage_percent,stage_eta:detail?.stage_eta,file_savings_percent:detail?.file_savings_percent,detail:detail?.detail,logId:detail?.id,requestId:job.id,sort:job.created||0}});
 // The workspace shows submitted requests, not legacy development catalog runs.
 return rows.sort((a,b)=>b.sort-a.sort);
}
function outcomeTime(job){return [job.finished,job.started,job.created].find(v=>Number.isFinite(v)&&v>0)||0}
function resultName(job){return String(job.source||'Video').replaceAll('\\','/').split('/').pop()}
function sortedResults(rows,mode='newest'){return [...rows].sort((a,b)=>{
 const aTime=outcomeTime(a),bTime=outcomeTime(b),name=resultName(a).localeCompare(resultName(b),undefined,{numeric:true,sensitivity:'base'});
 const aSaved=a.state==='replaced'&&Number.isFinite(a.saved_bytes)?a.saved_bytes:-Infinity,bSaved=b.state==='replaced'&&Number.isFinite(b.saved_bytes)?b.saved_bytes:-Infinity;
 const primary=mode==='name'?name:mode==='saved'?(aSaved===bSaved?0:aSaved>bSaved?-1:1):mode==='oldest'?(aTime&&bTime?aTime-bTime:aTime?-1:bTime?1:0):bTime-aTime;
 return primary||bTime-aTime||name||String(a.requestId||a.id).localeCompare(String(b.requestId||b.id));
})}
function resultMeta(job){const t=outcomeTime(job),label=Number.isFinite(job.finished)&&job.finished>0?'Finished':Number.isFinite(job.started)&&job.started>0?'Started':'Queued';const action=({analyze:'Inspection',test:'Sample test',encode:'Create copy',replace:'Replace after validation',keep:'Keep original'})[job.settings?.mode]||'Request';return action+' · '+(t?label+' '+new Date(t*1000).toLocaleString():'Date unavailable')}
function receiveControls(body){requestJobs=body.jobs||[];queueState=body;
 receiveHistory(body);
 const savings=body.lifetime_savings;if(savings){const bytes=savings.saved_bytes||0;userEl('lifetime-saved').textContent=(bytes/(bytes>=1e12?1e12:1e9)).toFixed(2)+(bytes>=1e12?' TB':' GB');userEl('lifetime-detail').textContent=savings.replaced_files+' files replaced'+(Number.isFinite(savings.percent)?' · '+savings.percent.toFixed(1)+'% smaller overall':'')}
 renderUserResults()}
function renderUserResults(force=false){const rows=mergedResults(),running=rows.filter(j=>j.state==='running'),active=running[0],current=userEl('current-work');current.replaceChildren();
 if(active){for(const active of running)current.append(renderActiveCard(active));}else current.append(userNode('p',queueState.wait_reason|| (queueState.paused?(queueState.pause_reason||'Queue paused. Resume when ready.'):(queueState.error|| (rows.some(j=>j.state==='pending')?'Videos are queued. Checking worker availability…':'No video is running. Use Set up to start.')))));
 const counts=queueState.counts||{},total=Object.values(counts).reduce((a,b)=>a+b,0),processed=total-(counts.pending||0)-(counts.running||0);
 current.append(userNode('p',processed+' of '+total+' requests processed · '+(counts.analyzed||0)+' inspected · '+((counts.skipped||0)+(counts['kept-original']||0))+' kept · '+(counts.failed||0)+' failed','result-meta'));
 if(counts.pending&&active)current.append(userNode('p','Queued videos: '+(queueState.wait_reason||'Waiting for an available worker slot')+'. Running work finishes normally.','control-note'));
 const batch=userEl('result-batch').value;if(batch){const selected=rows.filter(j=>(j.batch_id||'folder:'+String(j.source||'').replaceAll('\\','/').split('/').slice(0,-1).join('/'))===batch),finished=selected.filter(j=>!['pending','running'].includes(j.state)).length;current.append(userNode('p','Selected batch: '+finished+' of '+selected.length+' requests finished. Skips and failures count as finished, not successful.','result-meta'))}
 if(requestJobs.length&&requestJobs.every(j=>j.settings?.mode==='analyze'))current.append(userNode('p','Inspection only — no videos will be converted.','control-note'));
 const message=active?'Running: '+active.source.replaceAll('\\','/').split('/').pop()+' · '+friendlyStage(active.phase):rows.filter(j=>resultGroup(j.state)==='ready').length+' copies ready for review';
 if(message!==lastAnnouncement){userEl('activity-announcement').textContent=message;lastAnnouncement=message}
 renderHistoryResults(rows,force);
}
userEl('result-search').addEventListener('input',()=>{resultLimit=20;renderUserResults(true)});userEl('result-filter').addEventListener('change',()=>{resultLimit=20;renderUserResults(true)});userEl('show-results').addEventListener('click',()=>{resultLimit+=20;renderUserResults(true)});
userEl('result-sort').addEventListener('change',()=>{resultLimit=20;renderUserResults(true)});
let userTimer=null;
async function refreshUserJobs(){try{if(globalThis.liveUpdatesPaused)return;const r=await fetch('/api/jobs',{signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error('Connection lost. Displayed results may be out of date.');const body=await r.json();catalogJobs=body.jobs||[];connectionUpdate('catalog',true);renderUserResults()}catch(e){connectionUpdate('catalog',false)}finally{clearTimeout(userTimer);userTimer=setTimeout(refreshUserJobs,10000)}}wireHistory();refreshUserJobs();
</script>'''
