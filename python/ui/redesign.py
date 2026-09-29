"""Three-view workspace using the existing live controls and shared backend."""

STYLE = '''<style>
:root{--bg:#f5f6f3;--panel:#ffffff;--text:#19271e;--muted:#536359;--soft:#e9efe6;--accent:#204d35;--accent-text:#ffffff;--hairline:#dbe2da}
:root[data-theme=dark]{--bg:#121713;--panel:#1b221d;--text:#edf3ed;--muted:#afbeb2;--soft:#28362b;--accent:#c2e8a3;--accent-text:#173021;--hairline:#38473c}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121713;--panel:#1b221d;--text:#edf3ed;--muted:#afbeb2;--soft:#28362b;--accent:#c2e8a3;--accent-text:#173021;--hairline:#38473c}}
.masthead{max-width:none;padding:18px max(24px,calc((100vw - 1100px)/2));background:var(--panel);border-bottom:1px solid var(--hairline);gap:24px}
.masthead nav{gap:6px}.masthead nav a{padding:10px 16px;border-radius:8px;text-decoration:none;color:var(--muted)}.masthead nav a[aria-current=page]{background:var(--soft);color:var(--text);font-weight:650}
.brand::before{content:'▥';display:inline-grid;place-items:center;width:34px;height:34px;background:var(--accent);color:var(--accent-text);border-radius:9px;margin-right:10px}
main{max-width:1100px;padding-top:24px}.page-heading{display:flex;justify-content:space-between;align-items:center;gap:20px}.page-heading h1{font-size:1.75rem;font-weight:550}.page-heading .safety-note{font-weight:400;font-size:.9rem}
.panel{border-color:var(--hairline);border-radius:14px}.panel-head{border-color:var(--hairline)}.panel-head h2{font-weight:600}.savings-hero{border:0;background:transparent;padding:18px 0 22px;margin-bottom:0;border-radius:0;border-bottom:1px solid var(--hairline)}.savings-number{font-weight:500;font-size:clamp(2.8rem,6vw,4rem);letter-spacing:-.04em;margin:8px 0}.savings-symbol{display:none}.savings-hero .eyebrow{font-size:.72rem;margin-bottom:6px}.savings-hero details{font-size:.82rem;color:var(--muted)}.savings-hero summary{font-weight:400;min-height:32px;padding:4px 0}
#live-resources{background:transparent;border:0;margin:0 0 22px}#live-resources .panel-head{display:none}#live-resources .panel-body{padding:12px 0}#resource-status{margin:0;font-size:.82rem}
.workspace-enhanced [data-workspace-view]:not(.is-active){display:none!important}
#workflow{max-width:800px;margin:0 auto 28px}#workflow .guide-content{padding:26px}#workflow .folder-workspace{border-left:0;padding:22px}#workflow .control-preview{border:1px solid var(--hairline)}#workflow .control-grid{gap:20px}
.setup-steps{display:flex;flex-wrap:wrap;gap:10px;list-style:none;padding:0;margin:0 0 22px;color:var(--muted);font-size:.85rem}.setup-steps li{padding:7px 12px;border-radius:7px;background:var(--soft)}
.active-job{border-color:var(--hairline);padding:22px}.active-job h3{font-size:1.2rem;font-weight:550}.stage-list li{border:0}.stage-list .current-step{border:1px solid var(--focus)}.result-card{border-color:var(--hairline);padding:18px 0}.result-card h3{font-size:1rem;font-weight:600}.result-meta{font-size:.83rem}
.result-card .badge{border:1px solid var(--hairline)}#result-tools{padding-bottom:12px}#reports{margin-top:20px}#reports>.panel-head{cursor:pointer}#results>.panel-body>.control-note{font-size:.83rem}#gpu-yield-status{font-size:.85rem;color:var(--muted)}footer{margin-top:24px}
@media(max-width:650px){.masthead{padding:14px 16px}.masthead nav a{padding:10px 12px}.page-heading{align-items:flex-start;flex-wrap:wrap}.page-heading h1{font-size:1.5rem}#workflow .guide-content{padding:16px}.theme-control label{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}}
</style>'''

SCRIPT = r'''<script>
(function(){
 const pages={overview:['activity'], 'add-videos':['workflow'], results:['results','reports']};
 const aliases={activity:'overview',workflow:'add-videos',reports:'results'};
 const names={overview:'Overview','add-videos':'Add videos',results:'Results'};
 function go(value,focus=false){
  const name=aliases[value]||value,selected=pages[name]?name:'overview';
  for(const [page,ids] of Object.entries(pages))for(const id of ids){const el=document.getElementById(id);if(el){el.dataset.workspaceView=page;el.classList.toggle('is-active',page===selected);el.hidden=page!==selected}}
  document.querySelectorAll('[data-workspace-link]').forEach(link=>{if(link.dataset.workspaceLink===selected)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current')});
  const title=document.getElementById('workspace-title');title.textContent=names[selected];
  if(selected==='add-videos')document.getElementById('workflow').open=true;
  if(value==='reports')document.getElementById('reports').open=true;
  document.body.classList.add('workspace-enhanced');
  if(focus){title.focus({preventScroll:true});title.scrollIntoView({block:'start',behavior:'instant'})}
 }
 globalThis.showWorkspaceView=function(name){if(location.hash==='#'+name)go(name,true);else location.hash=name};
 document.querySelectorAll('[data-workspace-link]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();showWorkspaceView(link.dataset.workspaceLink)}));
 window.addEventListener('hashchange',()=>go(location.hash.slice(1),true));
 go(location.hash.slice(1));
})();
</script>'''


def redesign(html):
    old='<nav aria-label="Main"><a href="#workflow">Set up</a><a href="#activity">Progress</a><a href="#results">Results</a><a href="#reports">Reports</a></nav>'
    nav='<nav aria-label="Main">'+''.join(
        f'<a href="#{key}" data-workspace-link="{key}">{name}</a>'
        for key,name in [('overview','Overview'),('add-videos','Add videos'),('results','Results')])+'</nav>'
    if old not in html:raise ValueError('Workspace navigation contract changed')
    html=html.replace(old,nav)
    html=html.replace('<h1>Media workspace</h1>','<h1 id="workspace-title" tabindex="-1">Overview</h1>')
    html=html.replace('</p></div>\n<section class="panel savings-hero"','</p><a class="button primary" href="#add-videos" data-workspace-link="add-videos">+ Add videos</a></div>\n<section class="panel savings-hero"',1)
    note='<p class="control-note">Confirmed replacements only. Retained output copies and snapshots still occupy disk space. Older work without a receipt is not included.</p>'
    html=html.replace(note,'<details><summary>About these savings</summary>'+note+'</details>')
    html=html.replace('>Processing dashboard</h2>','>Current work</h2>')
    html=html.replace('>1. Select and set up</h2>','>Choose what to process</h2>')
    html=html.replace('<p class="control-note" id="control-availability">','<ol class="setup-steps" aria-label="Setup steps"><li>1 · Select source</li><li>2 · Choose options</li><li>3 · Review and start</li></ol><p class="control-note" id="control-availability">')
    html=html.replace('>2. Review and start</h3>','>3 · Review and start</h3>')
    html=html.replace('<details id="result-tools" open>','<details id="result-tools">')
    # Keep all existing report controls, but avoid two competing result lists.
    start=html.index('<section class="panel" id="reports"')
    end=html.index('</section>',start)+len('</section>')
    report=html[start:end].replace('<section ', '<details ',1).replace('<div class="panel-head">','<summary class="panel-head">',1)
    report=report.replace('</h2></div>','</h2></summary>',1).removesuffix('</section>')+'</details>'
    html=html[:start]+html[end:]
    end_results=html.index('</section>',html.index('<section class="panel" id="results"'))+len('</section>')
    html=html[:end_results]+report+html[end_results:]
    return html.replace('</head>',STYLE+'</head>').replace('</body>',SCRIPT+'</body>')
