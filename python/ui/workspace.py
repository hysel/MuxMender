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
userEl('toggle-updates').addEventListener('click',()=>{globalThis.liveUpdatesPaused=!globalThis.liveUpdatesPaused;userEl('toggle-updates').setAttribute('aria-pressed',String(globalThis.liveUpdatesPaused));userEl('toggle-updates').textContent=globalThis.liveUpdatesPaused?'Resume display updates':'Freeze display only';userEl('connection-state').textContent=globalThis.liveUpdatesPaused?'Display paused · jobs continue':'Reconnecting…';if(!globalThis.liveUpdatesPaused){refreshUserJobs();if(typeof refreshControls==='function')refreshControls()}});
function userReason(job){const raw=String(job.reason||job.detail||job.error||'');const s=job.state;
 if(s==='pending')return 'Waiting for its turn. See Current work for queue status.';
 if(s==='running')return 'Work is in progress. See Current work for the current step.';
 if(s==='replaced')return 'Original replaced after automated checks and verified copying. No playback review was required.';
 if(/source audio preflight|quant_step_size/i.test(raw))return 'The source audio could not be decoded. Original kept. Check the source audio before retrying.';
 if(raw.startsWith('Unsupported input:'))return raw;
 if(['verified','awaiting-playback','playback-approved'].includes(s))return 'Automated checks passed. Review playback before replacing the original.';
 if(s==='kept-original')return 'You chose to keep the original. No conversion was started.';
 if(s==='skipped'){
 if(job.decision_code==='full_output_insufficient_savings'&&job.evidence?.full_size){const f=job.evidence.full_size;if(Number.isFinite(f.source_bytes)&&Number.isFinite(f.output_bytes)&&Number.isFinite(f.saved_percent)&&Number.isFinite(f.minimum_savings_percent)){return 'Original kept: full conversion saved '+((f.source_bytes-f.output_bytes)/1e9).toFixed(3)+' GB ('+f.saved_percent.toFixed(1)+'%), below the required '+f.minimum_savings_percent.toFixed(1)+'%. '+(f.full_validation_performed?'':'Full validation was not performed.');}}
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
 if(['failed','stale','unknown','completed-with-errors'].includes(s)){
  if(raw.startsWith('Replacement needs attention:'))return raw+' Inspect the publication journal; the source path may already contain the new copy.';
  if(/processing (?:time )?limit|timed out|timeout/i.test(raw))return 'A check reached your time limit. The original was kept. Review the limit before retrying.';
  if(/out of memory|cannot allocate memory|oom/i.test(raw))return 'Processing ran out of available memory. Open details before retrying.';
  if(/decoder|corrupt|invalid data|decode reported/i.test(raw))return 'A decoding check failed. Open details to see whether the problem was in the source or the new copy.';
  return 'Processing needs attention. Open details for the recorded reason.';
 }
 return raw||'Processing finished. Open details to check the outcome.';
}
function userStatus(state){return ({replaced:'Replaced',pending:'Queued',running:'Running',verified:'Ready for review','awaiting-playback':'Ready for review','playback-approved':'Playback approved',skipped:'Original kept','kept-original':'Original kept',analyzed:'Inspection complete',tested:'Samples tested',completed:'Finished — review details',failed:'Needs attention',interrupted:'Interrupted',stale:'Update overdue',unknown:'Needs attention'})[state]||'Needs attention'}
function resultGroup(state){return state==='replaced'?'replaced':['pending','running'].includes(state)?'active':['verified','awaiting-playback','playback-approved'].includes(state)?'ready':['skipped','kept-original'].includes(state)?'kept':['analyzed','tested','completed'].includes(state)?'complete':'attention'}
function sourceBytes(job){return [job.original_bytes,job.source_bytes,job.signature?.[0]].find(v=>Number.isFinite(v)&&v>=0)??null}
function fileSizeText(bytes){return bytes>=1e9?(bytes/1e9).toFixed(2)+' GB':bytes>=1e6?(bytes/1e6).toFixed(2)+' MB':bytes>=1e3?(bytes/1e3).toFixed(2)+' KB':bytes+' bytes'}
function sizeSummary(job){
 const source=sourceBytes(job),output=job.output_bytes;
 let text=source===null?'Source size unavailable':'Source: '+fileSizeText(source);
 if(Number.isFinite(output)&&output>=0){
  text+=' → Output: '+fileSizeText(output);
  if(source>0){const change=100*(1-output/source);text+=' · '+Math.abs(change).toFixed(1)+'% '+(change<0?'larger':'smaller')}
 }
 return text;
}
function activityLabel(value){const s=String(value||'').toLowerCase();if(s.startsWith('waiting for ')&&s.includes('resources'))return 'Waiting for resources · this check has not started';if(s.endsWith(' · gpu reader')&&/^(checking hdr frame timing:|checking hdr frames:|checking original hdr metadata)/.test(s))return 'GPU validation · checking every frame and HDR metadata; not encoding';if(s==='inspect every source frame for hdr and dv metadata'||s.startsWith('checking original hdr metadata'))return 'CPU inspection · reading HDR and Dolby Vision metadata; not encoding';if(s.startsWith('checking hdr frame timing:')||s==='compare every decoded output frame and static hdr value')return 'CPU validation · checking decoded frames and HDR metadata';if(/^(hevc|av1|h264)_nvenc full encode$/.test(s))return 'GPU encoding · NVIDIA';if(s==='full-encode')return 'Encoding · creating a separate video copy';return ''}
function friendlyStage(value){const s=String(value||'');const activity=activityLabel(s);if(activity)return activity;if(s==='full-decode')return 'Checking the full copy plays without decode errors';if(s.includes('Checking frame timing'))return 'Checking resolution and frame timing';if(s.includes('Checking copied track'))return 'Verifying audio or subtitles';if(s.includes('self-'))return 'Checking the quality measurement';if(s.includes('quality'))return 'Measuring visual quality';if(/nvenc|amf|qsv|vaapi/.test(s))return 'Comparing encoding options';return s.replaceAll('-',' ')||'Preparing the video'}
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
function progressFreshness(job,now=Date.now()/1000,connected=true,displayPaused=false){
 if(displayPaused)return 'Live display paused · jobs may still be running';
 if(!connected)return 'Dashboard connection lost · current job progress is unavailable';
 if(job.telemetry_state==='interrupted')return 'Worker stopped · last reported progress is historical';
 if(job.telemetry_state==='stale'||(Number.isFinite(job.updated)&&now-job.updated>=90))return 'Update overdue · no worker update for at least 90 seconds; last reported progress may be stale';
 if(!Number.isFinite(job.updated))return 'Waiting for the first worker progress update';
 return '';
}
const activeDetailViews=new Set();
function renderActiveCard(job){
 const card=userNode('article',null,'active-job'),view=stagePresentation(job);
 card.append(userNode('h3',resultName(job)),userNode('p',sizeSummary(job),'result-meta'));
 const freshness=progressFreshness(job,Date.now()/1000,catalogConnected,globalThis.liveUpdatesPaused===true);
 const measuredPercent=Number.isFinite(job.stage_percent)&&job.stage_percent>=0&&job.stage_percent<=100?job.stage_percent:null;
 const percent=freshness?null:measuredPercent;
 const head=userNode('div',null,'job-progress-head');
 head.append(userNode('p',view.title,'stage-title'),userNode('p',freshness?'Progress unavailable':percent===null?'Measuring…':percent===100?'Check complete · finishing':percent.toFixed(0)+'% of current check','check-progress'));
 const track=userNode('div',null,'job-progress-track'),fill=userNode('div',null,'job-progress-fill');
 track.setAttribute('role','progressbar');track.setAttribute('aria-label','Current check for '+resultName(job));
 track.setAttribute('aria-valuemin','0');track.setAttribute('aria-valuemax','100');
 if(percent!==null){track.setAttribute('aria-valuenow',String(percent));track.setAttribute('aria-valuetext',percent.toFixed(0)+'% of the current check; not overall video progress');fill.style.width=percent+'%';if(percent===100)track.classList.add('is-complete')}
 else{track.classList.add(freshness?'is-stale':'is-measuring');track.setAttribute('aria-valuetext',freshness||'Working; a percentage has not been reported');fill.style.width=freshness?(measuredPercent??0)+'%':'100%'}
 fill.setAttribute('aria-hidden','true');track.append(fill);
 card.append(head,track,userNode('p',friendlyStage(job.phase),'job-phase'));
 const steps=userNode('ol',null,'stage-list');steps.setAttribute('aria-label','Workflow stages');
 view.steps.forEach((stage,index)=>{const item=userNode('li',(index+1)+'. '+view.labels[stage]);if(index===view.index){item.setAttribute('aria-current','step');item.className='current-step'}else if(index<view.index){item.className='completed-step';item.setAttribute('aria-label',view.labels[stage]+' step finished')}steps.append(item)});
 const timing=userNode('p',null,'job-timing');
 timing.textContent=(Number.isFinite(job.started)?'Elapsed '+Math.max(0,Math.floor((Date.now()/1000-job.started)/60))+' min':'')+
   (!freshness&&Number.isFinite(job.stage_eta)?' · Current check ETA '+Math.max(1,Math.ceil(job.stage_eta/60))+' min':'');
 card.append(timing);
 if(freshness)card.append(userNode('p',freshness,'attention'));
 const detail=userNode('details'),summary=userNode('summary','Details');
 summary.setAttribute('aria-label','Steps and details for '+resultName(job));detail.append(summary,steps);
 const detailKey=job.requestId||job.id||job.source;
 detail.open=activeDetailViews.has(detailKey);
 detail.addEventListener('toggle',()=>{if(detail.open)activeDetailViews.add(detailKey);else activeDetailViews.delete(detailKey)});
 if(job.detail)detail.append(userNode('p',job.detail,'control-note'));
 detail.append(userNode('p','Percent and ETA apply to the current check only. Stages contain multiple checks; their durations are not equal.','control-note'));
 const measured=Object.entries(job.performance_seconds||{}).filter(([,v])=>Number.isFinite(v)&&v>0);
 if(measured.length&&job.performance_schema>=2){
  const waiting=['validation_wait','gpu_wait','publication_wait'].reduce((n,k)=>n+(job.performance_seconds[k]||0),0),paused=job.performance_seconds.gpu_pause||0,total=measured.reduce((n,[,v])=>n+v,0);
  detail.append(userNode('p','Observed time: '+Math.round(Math.max(0,total-waiting-paused)/60)+' min outside measured waits/pauses · '+Math.round(waiting/60)+' min waiting for resources'+(job.performance_schema>=3?' · '+Math.round(paused/60)+' min yielding to other apps':''),'result-meta'));
 }
 if(measured.length&&!(job.performance_schema>=2))detail.append(userNode('p','Legacy timings: validation waiting was not measured separately.','control-note'));
 for(const [name,seconds] of measured)detail.append(userNode('p',name.replaceAll('_',' ')+': '+Math.round(seconds)+' sec'));
 card.append(detail);return card;
}
function mergedResults(){const rows=requestJobs.map(job=>{const candidates=catalogJobs.filter(c=>(String(c.directory).replaceAll('\\','/')+'/').includes('request-'+job.id+'/'));const tracked=candidates.filter(c=>/\/job-[^/]+$/.test(String(c.directory).replaceAll('\\','/')));const detail=(tracked.length?tracked:candidates).sort((a,b)=>(b.updated||b.started||0)-(a.updated||a.started||0))[0];return {...detail,...job,telemetry_state:detail?.state,phase:detail?.phase,workflow_stage:detail?.workflow_stage,stage_started:detail?.stage_started,updated:detail?.updated,stage_percent:detail?.stage_percent,stage_eta:detail?.stage_eta,file_savings_percent:detail?.file_savings_percent,detail:detail?.detail,logId:detail?.id,requestId:job.id,sort:job.created||0}});
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
 renderOutcomeSummary(requestJobs);
 receiveHistory(body);
 if(typeof renderWorkspaceSummary==='function')renderWorkspaceSummary(body);
 const savings=body.lifetime_savings;if(savings){const bytes=savings.saved_bytes||0;userEl('lifetime-saved').textContent=(bytes/(bytes>=1e12?1e12:1e9)).toFixed(2)+(bytes>=1e12?' TB':' GB');userEl('lifetime-detail').textContent=savings.replaced_files+' files replaced'+(Number.isFinite(savings.percent)?' · '+savings.percent.toFixed(1)+'% smaller overall':'')}
 renderUserResults()}
function renderUserResults(force=false){const rows=mergedResults(),running=rows.filter(j=>j.state==='running'),active=running[0],current=userEl('current-work');current.replaceChildren();
 if(active){for(const active of running)current.append(renderActiveCard(active));}else current.append(userNode('p',queueState.wait_reason|| (queueState.paused?(queueState.pause_reason||'Queue paused. Resume when ready.'):(queueState.error|| (rows.some(j=>j.state==='pending')?'Videos are queued. Checking worker availability…':'You’re all caught up. Choose Add videos to start another batch.')))));
 const counts=queueState.counts||{},total=Object.values(counts).reduce((a,b)=>a+b,0),processed=total-(counts.pending||0)-(counts.running||0);
 current.append(userNode('p',processed+' of '+total+' requests finished · '+(counts.analyzed||0)+' inspected · '+((counts.skipped||0)+(counts['kept-original']||0))+' kept · '+(counts.failed||0)+' failed','result-meta'));
 if(counts.pending&&active)current.append(userNode('p','Queued videos: '+(queueState.wait_reason||'Waiting for an available worker slot')+'. Running work finishes normally.','control-note'));
 const batch=userEl('result-batch').value;if(batch){const selected=rows.filter(j=>(j.batch_id||'folder:'+String(j.source||'').replaceAll('\\','/').split('/').slice(0,-1).join('/'))===batch),finished=selected.filter(j=>!['pending','running'].includes(j.state)).length;current.append(userNode('p','Selected batch: '+finished+' of '+selected.length+' requests finished. Skips and failures count as finished, not successful.','result-meta'))}
 if(requestJobs.length&&requestJobs.every(j=>j.settings?.mode==='analyze'))current.append(userNode('p','Inspection only — no videos will be converted.','control-note'));
 const message=active?'Running: '+active.source.replaceAll('\\','/').split('/').pop()+' · '+friendlyStage(active.phase):rows.filter(j=>resultGroup(j.state)==='ready').length+' copies ready for review';
 if(message!==lastAnnouncement){userEl('activity-announcement').textContent=message;lastAnnouncement=message}
 renderHistoryResults(rows,force);
}
userEl('result-search').addEventListener('input',()=>{resultLimit=20;renderUserResults(true)});userEl('result-filter').addEventListener('change',()=>{resultLimit=20;renderUserResults(true)});userEl('show-results').addEventListener('click',()=>{resultLimit+=20;renderUserResults(true)});
userEl('result-sort').addEventListener('change',()=>{resultLimit=20;renderUserResults(true)});
let userTimer=null,userPollBusy=false;
async function refreshUserJobs(){if(userPollBusy)return;userPollBusy=true;let received=false;try{if(globalThis.liveUpdatesPaused)return;const r=await fetch('/api/jobs',{signal:AbortSignal.timeout(30000)});if(!r.ok)throw Error('Connection lost. Displayed results may be out of date.');const body=await r.json();received=true;catalogJobs=body.jobs||[];connectionUpdate('catalog',true);renderUserResults();if(body.catalog_error)userEl('connection-state').textContent='Connected · progress refresh failed; showing last-known data';else if(!body.catalog_updated)userEl('connection-state').textContent='Connected · loading job progress; processing is unaffected'}catch(e){if(received){console.error(e);userEl('connection-state').textContent='Display update failed · retrying; processing is unaffected'}else{connectionUpdate('catalog',false);renderUserResults()}}finally{userPollBusy=false;clearTimeout(userTimer);userTimer=setTimeout(refreshUserJobs,10000)}}wireHistory();refreshUserJobs();
</script>'''
