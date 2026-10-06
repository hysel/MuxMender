"""Presentation-only refinement. No workflow, queue or publication policy."""

STYLE = '''<style>
:root{--bg:#f6f8f7;--panel:#ffffff;--text:#172b25;--muted:#48615a;--soft:#eaf3f0;--accent:#14685d;--accent-text:#ffffff;--border:#74847d;--hairline:#dce3e0;--focus:#00655c;--danger:#99251d;--success:#14685d}
:root[data-theme=dark]{--bg:#101916;--panel:#172321;--text:#eff6f2;--muted:#b5c8c0;--soft:#21332d;--accent:#a5e0cd;--accent-text:#12392e;--border:#8b9f99;--hairline:#354840;--focus:#9ee4d3;--danger:#ffc2b9;--success:#a5e0cd}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#101916;--panel:#172321;--text:#eff6f2;--muted:#b5c8c0;--soft:#21332d;--accent:#a5e0cd;--accent-text:#12392e;--border:#8b9f99;--hairline:#354840;--focus:#9ee4d3;--danger:#ffc2b9;--success:#a5e0cd}}
body{font-size:15px;line-height:1.6}main{max-width:1180px;padding:28px 28px 48px}.masthead{padding:16px max(28px,calc((100vw - 1124px)/2));gap:24px}.brand{font-size:1.2rem;letter-spacing:-.03em}.brand::before{content:'↘';width:32px;height:32px}.masthead nav{justify-content:center}.masthead nav a{min-height:44px;padding:9px 16px;border-radius:10px;font-size:.92rem}.masthead nav a[aria-current=page]{background:var(--soft);color:var(--accent)}.theme-control select{font-size:.85rem;min-height:44px}.page-heading{padding:30px 0 18px;align-items:flex-start;margin:0}.page-heading h1{font-size:clamp(1.65rem,4vw,2rem);font-weight:650;margin:0 0 5px;letter-spacing:-.04em}.page-heading p{margin:0;max-width:62ch;color:var(--muted)}.page-heading>.button{flex-shrink:0}.button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 18px;border-radius:10px;text-decoration:none;border:1px solid var(--border)}.primary{border-color:var(--accent);background:var(--accent);color:var(--accent-text);font-weight:650}.primary:hover:not(:disabled){background:var(--accent);filter:brightness(.94)}
.connection-bar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px;color:var(--muted);font-size:.83rem}.connection-bar p{margin:0}.connection-bar #connection-state{font-weight:600;max-width:65ch}.connection-bar .local-tag{border:1px solid var(--hairline);border-radius:999px;padding:3px 10px;white-space:nowrap}
.savings-hero{background:var(--panel);border:1px solid var(--hairline);border-radius:20px;padding:28px 32px;margin:0;display:flex;align-items:center;justify-content:space-between;gap:24px}.savings-hero .eyebrow{letter-spacing:.08em;font-size:.75rem;margin:0;color:var(--muted)}.savings-number{font-size:clamp(3.2rem,7vw,5rem);font-weight:600;line-height:1.12;letter-spacing:-.055em;margin:12px 0;color:var(--text);font-variant-numeric:tabular-nums}#lifetime-detail{margin:0;color:var(--muted)}.savings-hero details{margin-top:10px}.savings-hero summary{padding:4px 0;min-height:44px;font-size:.82rem}.savings-message{max-width:230px;border-inline-start:1px solid var(--hairline);padding-left:24px}.savings-message strong{display:block;font-weight:600;margin-bottom:6px}.savings-message p{color:var(--muted);font-size:.9rem;margin:0}
#live-resources{margin:0;border:0;background:transparent}#live-resources .panel-body{padding:16px 0 0}.resource-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0}.resource-strip>div{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;background:var(--panel);border:1px solid var(--hairline);border-radius:12px}.resource-strip dt{color:var(--muted);font-size:.85rem}.resource-strip dd{margin:0;font-weight:650;font-variant-numeric:tabular-nums}.resource-strip small{font-weight:400;font-size:.78rem;color:var(--muted)}#resource-status{font-size:.8rem;line-height:1.6;margin:10px 4px 0;color:var(--muted)}
.queue-glance{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:20px}.queue-glance>div{border:1px solid var(--hairline);border-radius:12px;padding:16px 18px;background:var(--panel)}.queue-glance span{display:block;color:var(--muted);font-size:.83rem}.queue-glance strong{display:block;font-size:1.8rem;line-height:1.3;font-weight:600;font-variant-numeric:tabular-nums}.queue-glance a{font-size:.8rem;display:inline-block;margin-top:6px}.panel{border-color:var(--hairline);border-radius:16px;margin-bottom:20px}.panel-head{padding:20px 24px;border-color:var(--hairline)}.panel-head h2{font-size:1.05rem;font-weight:650}.panel-body,.guide-content{padding:24px}.control-note{line-height:1.6}.control-actions{gap:10px;align-items:center}.control-actions button{font-size:.9rem}.queue-actions{padding-bottom:12px;border-bottom:1px solid var(--hairline);margin:0 0 16px}#clear-waiting-queue{color:var(--danger);margin-left:auto}#control-state{font-weight:600;margin-bottom:12px}.queue-support{margin-top:20px;padding-top:12px;border-top:1px solid var(--hairline)}.queue-support>summary{font-size:.88rem}.queue-support .control-note{font-size:.82rem}.active-job{border:1px solid var(--hairline);border-radius:14px;padding:22px;margin:14px 0;background:var(--panel)}.active-job h3{font-size:1.05rem;line-height:1.5;overflow-wrap:anywhere}.stage-title{font-size:1rem;margin:18px 0 10px}.stage-list{display:flex;flex-wrap:wrap;gap:6px;list-style:none;padding:0;margin:10px 0 14px}.stage-list li{padding:6px 9px;border-radius:7px;background:var(--bg);color:var(--muted);font-size:.78rem;border:1px solid transparent}.stage-list .current-step{border:1px solid var(--focus);background:var(--soft);color:var(--text);font-weight:650}.stage-list .completed-step{color:var(--success)}.check-progress{font-size:1rem;font-weight:650;margin-bottom:5px}.active-job details{border-top:1px solid var(--hairline);margin-top:14px;padding-top:6px}.active-job .result-meta{font-size:.82rem}.active-job details summary{font-size:.83rem}
#workflow{max-width:860px;margin:0 auto 24px}.setup-steps{margin:0 0 22px;gap:8px}.setup-steps li{font-size:.82rem;padding:8px 12px;border:1px solid var(--hairline);background:var(--bg)}.setup-steps li[aria-current=step]{background:var(--soft);border-color:var(--focus);color:var(--text);font-weight:650}.folder-workspace{border:1px dashed var(--border);background:var(--bg);border-radius:12px;padding:24px!important}.folder-workspace h3{font-size:1rem}.folder-picker{background:var(--panel);border-color:var(--hairline)}.control-grid{gap:20px}.control-grid label{font-size:.88rem}.control-advanced{border-color:var(--hairline)}.control-advanced>summary{font-size:.88rem}.control-preview{background:var(--soft);border:1px solid var(--border);padding:22px}#request-preview ul{background:var(--panel);padding:14px 18px 14px 34px;border-radius:9px}#replacement-confirmation{padding:12px;border:1px solid var(--danger);border-radius:8px;margin:16px 0}#replacement-confirmation label{margin:0;font-weight:600}
.results-intro{max-width:70ch;color:var(--muted);margin:0 0 20px}.result-card{border:1px solid var(--hairline);border-radius:12px;padding:20px;margin:12px 0;background:var(--panel)}.result-card:first-child{margin-top:14px}.result-card h3{font-size:1rem}.result-card .reason{font-weight:400;margin-top:8px;color:var(--text)}.result-card .badge{border:1px solid var(--hairline);font-weight:600;white-space:normal}.result-card details{border-top:1px solid var(--hairline);padding-top:5px}.result-meta{font-size:.82rem}.result-card details summary{font-size:.85rem}.result-summary{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.result-summary button{font-size:.85rem;border-color:var(--hairline);border-radius:999px;min-height:44px;padding:9px 14px}.result-summary button[aria-pressed=true]{background:var(--soft);border-color:var(--focus);font-weight:650}.result-count-label{font-size:.83rem;color:var(--muted)}#result-tools{border-top:1px solid var(--hairline);padding-top:4px}#result-tools>summary{font-size:.88rem}#results .panel-body>.control-actions{margin:12px 0}.report-overview{gap:8px}.report-overview button{font-size:.86rem;min-height:54px}.report-card{border-color:var(--hairline)}#reports{margin-top:20px}#reports summary{min-height:44px}.help{margin-top:28px;background:transparent}.help summary{font-size:.9rem}.help p{font-size:.88rem}footer{font-size:.78rem;padding-top:12px;color:var(--muted)}
button,input,select{border-radius:9px}button,input:not([type=checkbox]),select{min-height:44px}summary{min-height:44px}button:disabled{opacity:.65}*:focus-visible{outline:3px solid var(--focus);outline-offset:3px}.attention{color:var(--danger)}.preview-notice{padding:10px 24px;background:var(--soft);color:var(--text);text-align:center;font-weight:600}.queue-dialog-heading button{flex-shrink:0}
@media(max-width:700px){main{padding:20px 16px 32px}.masthead{padding:12px 16px;gap:12px}.masthead nav{order:3;flex-basis:100%;justify-content:space-between}.masthead nav a{flex:1;text-align:center;padding:9px 6px}.theme-control{margin-left:auto}.page-heading{padding:24px 0 16px;gap:14px}.savings-hero{padding:22px;align-items:flex-start}.savings-message{display:none}.resource-strip{gap:8px}.resource-strip>div{display:block;padding:12px}.resource-strip dd{margin-top:4px}.resource-strip small{display:block}.queue-glance{gap:8px}.queue-glance>div{padding:12px}.queue-glance a{font-size:.75rem}.panel-body,.guide-content,.panel-head{padding:18px}#workflow .guide-content{padding:18px}.control-grid{grid-template-columns:minmax(0,1fr);gap:8px}.queue-actions button{flex:1 1 130px}#clear-waiting-queue{margin-left:0}.active-job{padding:16px}.result-header{flex-direction:column;gap:8px}.result-summary{gap:6px}.connection-bar{align-items:flex-start}.connection-bar .local-tag{display:none}}
@media(forced-colors:active){.resource-strip>div,.queue-glance>div,.stage-list li,.result-card{border:1px solid CanvasText}.primary{border:1px solid ButtonText}}
.settings-row{display:grid;grid-template-columns:minmax(0,380px) minmax(180px,auto);align-items:end;gap:14px;width:min(100%,640px);margin:18px 0 10px}.settings-row .setting-field{min-width:0}.settings-row .setting-field label{margin:0 0 6px}.settings-row .setting-field select{width:100%}.settings-row button{width:100%;margin:0;min-height:44px}.settings-row label[for=gpu-yield-enabled]{display:flex;align-items:center;gap:10px;min-height:44px;margin:0}.settings-row input[type=checkbox]{flex:0 0 24px;margin:0}.queue-support #gpu-yield-status{margin:10px 0 0}@media(max-width:600px){.settings-row{grid-template-columns:minmax(0,1fr);gap:10px}.settings-row button{justify-self:start;width:auto;min-width:180px}}
</style>'''

SCRIPT = r'''<script>
function renderSetupGuide(){
 const selected=typeof activeFolder!=='undefined'&&activeFolder!==null;
 const reviewing=!document.getElementById('request-preview').hidden;
 document.querySelectorAll('.setup-steps li').forEach((item,index)=>{
  if(index===(reviewing?2:selected?1:0))item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');
 });
}
function renderWorkspaceSummary(body){
 const counts=body.counts||{},metrics=body.resources?.telemetry||{};
 const put=(id,value)=>{const node=document.getElementById(id);if(node)node.textContent=value};
 put('queue-running',counts.running||0);put('queue-waiting',counts.pending||0);
 const latest=groupedAttempts((body.jobs||[]).filter(j=>!j.superseded_by)).map(g=>g.latest);
 put('queue-attention',latest.filter(j=>['errors','attention'].includes(outcomeCategory(j))).length);
 const number=(key,suffix,digits=0)=>Number.isFinite(metrics[key])?metrics[key].toFixed(digits)+suffix:'Unavailable';
 put('resource-cpu',number('cpu_percent','%'));put('resource-gpu',number('gpu_encode_percent','%'));put('resource-ram',number('available_gib',' GiB',1));
 document.querySelectorAll('[data-result-shortcut]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.resultShortcut===document.getElementById('result-filter').value)));
 const filter=document.getElementById('result-filter');
 const names={all:'Completed results',active:'Queued & running',ready:'Copies ready for review',kept:'Original kept',attention:'Needs attention',replaced:'Space saved',complete:'Inspections and tests',history:'All requests'};
 put('result-view-description','Viewing: '+(names[filter.value]||'Filtered results')+'. This filter does not indicate whether the queue has finished.'+(filter.value==='all'?' Ongoing retries of completed attempts are included.':''));
}
(function(){
 renderSetupGuide();
 if(typeof MutationObserver!=='undefined'){
  new MutationObserver(renderSetupGuide).observe(document.getElementById('request-preview'),{attributes:true,attributeFilter:['hidden']});
  new MutationObserver(renderSetupGuide).observe(document.getElementById('folder-actions'),{attributes:true,attributeFilter:['hidden']});
 }
 document.querySelectorAll('[data-result-shortcut]').forEach(button=>button.addEventListener('click',()=>{
  const filter=document.getElementById('result-filter');filter.value=button.dataset.resultShortcut;
  filter.dispatchEvent(new Event('change',{bubbles:true}));
 }));
 document.getElementById('result-filter').addEventListener('change',()=>renderWorkspaceSummary(queueState));
 document.querySelectorAll('[data-attention-link]').forEach(link=>link.addEventListener('click',()=>{
  const filter=document.getElementById('result-filter');filter.value='attention';filter.dispatchEvent(new Event('change',{bubbles:true}));
 }));
})();
</script>'''


def refine(html):
    """Keep all IDs and action values; change only layout, help and view state."""
    html=html.replace('<p class="safety-note">Keep originals by default. Replacement requires an explicit choice and confirmation.</p>',
                      '<p class="safety-note" id="workspace-description">Follow your queue. We only replace videos after the checks pass and you approve replacement.</p></div>')
    html=html.replace('<h1 id="workspace-title"','<div class="workspace-intro"><h1 id="workspace-title"',1)
    html=html.replace('<main id="main" tabindex="-1">','<main id="main" tabindex="-1"><div class="connection-bar"><p id="connection-state" role="status">Connecting…</p><span class="local-tag">Your server · your media</span></div>')
    html=html.replace('<span id="connection-state" role="status">Connecting…</span>','')
    html=html.replace('<div class="savings-symbol" aria-hidden="true">↓</div>',
                      '<div class="savings-message"><strong>What counts here?</strong><p>Only originals replaced with smaller files. Test copies don’t count.</p></div>')
    html=html.replace('<p id="resource-status" class="control-note">',
                      '<dl class="resource-strip" aria-label="Server resources"><div><dt>CPU <small>host use</small></dt><dd id="resource-cpu">—</dd></div><div><dt>GPU <small>encoding use</small></dt><dd id="resource-gpu">—</dd></div><div><dt>RAM <small>available</small></dt><dd id="resource-ram">—</dd></div></dl><details class="resource-details"><summary>Resource details</summary><p id="resource-status" class="control-note">')
    html=html.replace('Collecting CPU, GPU and available RAM measurements…</p></div></section>',
                      'Collecting CPU, GPU and available RAM measurements…</p></details></div></section>',1)
    html=html.replace('<section class="panel" id="activity"',
                      '<section id="queue-overview" aria-label="Queue at a glance"><div class="queue-glance"><div><span>Running now</span><strong id="queue-running">—</strong></div><div><span>Waiting their turn</span><strong id="queue-waiting">—</strong></div><div><span>Needs attention</span><strong id="queue-attention">—</strong><a href="#results" data-workspace-link="results" data-attention-link>See what happened</a></div></div></section><section class="panel" id="activity"')
    html=html.replace('<p class="control-note">Follow the highlighted step. Percentages describe the current check—not the whole video.</p>',
                      '<p class="control-note">The highlighted step shows what is happening. Each percentage belongs to the current check.</p>')
    html=html.replace('<div class="control-actions"><button id="pause-selected"','<div class="control-actions queue-actions"><button id="pause-selected"')
    start=html.index('<details><summary>Resource settings</summary>')
    end=html.index('<div id="current-work">',start)
    support=html[start:end].replace('<details><summary>Resource settings</summary>','<details class="queue-support"><summary>Server sharing &amp; queue settings</summary>',1)
    support=support.replace('<div class="control-actions"><div><label for="resource-profile">',
                            '<div class="settings-row"><div class="setting-field"><label for="resource-profile">',1)
    support=support.replace('<select id="resource-profile">','<select id="resource-profile" aria-describedby="resource-profile-help">',1)
    support=support.replace('<p class="control-note">New workers start',
                            '<p id="resource-profile-help" class="control-note">New workers start',1)
    gpu_button='<button id="save-gpu-yield" type="button">Apply GPU sharing</button>'
    support=support.replace(gpu_button,'',1)
    support=support.replace('<label for="gpu-yield-enabled">','<div class="settings-row"><div class="setting-field"><label for="gpu-yield-enabled">',1)
    support=support.replace('</label><p id="gpu-yield-help" class="control-note">',
                            '</label></div>'+gpu_button+'</div><p id="gpu-yield-help" class="control-note">',1)
    status='<p id="gpu-yield-status" role="status" aria-live="polite">Automatic GPU yielding is off.</p>'
    support=support.replace(status,'',1).replace('</details>',status+'</details>',1)
    # Put secondary settings after current work, so live progress is first.
    html=html[:start]+html[end:]
    anchor='<p id="activity-announcement" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></p>'
    html=html.replace(anchor,anchor+support,1)
    html=html.replace('>Choose what to process</h2>','>Choose your videos</h2>')
    html=html.replace('>1 · Select source</li>','>1 · Choose videos</li>')
    html=html.replace('>2 · Choose options</li>','>2 · Choose what happens</li>')
    html=html.replace('>3 · Review and start</li>','>3 · Review &amp; start</li>')
    html=html.replace('>Folder scope</label>','>Include</label>')
    html=html.replace('>Work on</label>','>Videos to process</label>')
    html=html.replace('>Action</label>','>What would you like to do?</label>')
    html=html.replace('>Advanced settings · automatic by default</summary>','>Fine-tune settings (optional)</summary>')
    html=html.replace('>Review selection</button>','>Review before starting</button>')
    html=html.replace('>Start selected jobs</button>','>Add to queue</button>')
    html=html.replace('>Server folder path</label>','>Folder on your server</label>')
    html=html.replace('>Inspect videos — no conversion</option>','>Inspect only — don’t change files</option>')
    html=html.replace('>Test quality and size — samples only</option>','>Try a short test — keep originals</option>')
    html=html.replace('>Create smaller copies — only if checks pass</option>','>Create smaller copies — keep originals</option>')
    html=html.replace('>Convert and replace originals — only after all checks pass</option>','>Save space — replace after checks pass</option>')
    # Keep safety explanations and detailed evidence, but make them opt-in.
    first='<p class="control-note">Latest attempt per video, newest outcome first. Expand previous attempts to see history. Active retries stay visible. Times use your browser\'s local time zone.</p>'
    second='<p class="control-note">Ready for review means automated checks passed—not a guarantee of identical visual quality. Play the copy before replacing an original. Size reduction is not disk space freed while both copies are retained.</p>'
    html=html.replace(first,'<p class="results-intro">What happened, why it happened, and how much smaller each video became. Your latest attempt is shown first. <a href="#reports">Export a report</a></p><div class="result-summary" role="group" aria-label="Filter videos shown below" aria-describedby="result-view-description"><button type="button" data-result-shortcut="all" aria-pressed="true">Completed results</button><button type="button" data-result-shortcut="active" aria-pressed="false">Queued &amp; running</button><button type="button" data-result-shortcut="replaced" aria-pressed="false">Space saved</button><button type="button" data-result-shortcut="kept" aria-pressed="false">Original kept</button><button type="button" data-result-shortcut="attention" aria-pressed="false">Needs attention</button></div><p id="result-view-description" class="control-note" role="status">Viewing: Completed results. This filter does not indicate whether the queue has finished. Ongoing retries of completed attempts are included.</p>')
    html=html.replace('>Finished work</option>','>Completed results (including ongoing retries)</option>')
    html=html.replace('>Queued or running</option>','>Queued &amp; running</option>')
    html=html.replace('>Pause live updates</button>','>Freeze display only</button>')
    html=html.replace('>Pause after current job</button>','>Pause new starts</button>')
    html=html.replace('Pausing the queue lets its current job finish. Pausing live updates only freezes this display.',
                      'Pause new starts lets active jobs finish. Freeze display only stops screen updates; jobs continue.')
    html=html.replace(second,'<details><summary>Understanding results</summary>'+first+second+'</details>')
    html=html.replace('<div class="control-actions"><button id="archive-results"',
                      '<details class="history-options"><summary>Manage displayed results</summary><div class="control-actions"><button id="archive-results"',1)
    html=html.replace('<p id="history-feedback" role="status" aria-live="polite"></p>',
                      '</details><p id="history-feedback" role="status" aria-live="polite"></p>',1)
    html=html.replace('<span id="result-count">','<span class="result-count-label" id="result-count">')
    html=html.replace('>Activity reports</h2>','>Download a report or explore history</h2>')
    html=html.replace(' · Replacement is opt-in · History and preferences are stored on the /output mount.',
                      ' · Originals are replaced only with your approval.')
    return html.replace('</head>',STYLE+'</head>').replace('</body>',SCRIPT+'</body>')
