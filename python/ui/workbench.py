"""A spacecraft-inspired media console. Presentation only; no job policy."""

STYLE = '''<style id="workbench-style">
:root{--bg:#f5f6f8;--panel:#ffffff;--text:#222b35;--muted:#586574;--soft:#edf0f3;--accent:#237746;--accent-text:#ffffff;--border:#7c8792;--hairline:#e2e6eb;--focus:#267147;--danger:#974839;--success:#237746;--lime:#c3ed72;--progress:#628e32}
:root[data-theme=dark]{--bg:#141b23;--panel:#1d2630;--text:#eef2f6;--muted:#b3bdc7;--soft:#28343f;--accent:#c3ed72;--accent-text:#203719;--border:#8896a4;--hairline:#3a4652;--focus:#c3ed72;--danger:#ffb4a4;--success:#c3ed72;--lime:#c3ed72;--progress:#c3ed72}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141b23;--panel:#1d2630;--text:#eef2f6;--muted:#b3bdc7;--soft:#28343f;--accent:#c3ed72;--accent-text:#203719;--border:#8896a4;--hairline:#3a4652;--focus:#c3ed72;--danger:#ffb4a4;--success:#c3ed72;--lime:#c3ed72;--progress:#c3ed72}}
body{background:var(--bg);font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.55}
main{max-width:1240px;padding:0 40px 48px;margin:auto}
.masthead{max-width:1240px;margin:auto;padding:20px 40px 0;background:transparent;border:0;gap:36px;align-items:center}
.brand{color:var(--text);font-size:1.35rem;letter-spacing:-.04em;font-weight:750;white-space:nowrap}
.brand::before{content:'';width:20px;height:24px;border:2px solid var(--accent);border-radius:2px;vertical-align:middle;margin-right:12px;background:repeating-linear-gradient(to bottom,transparent 0 6px,var(--accent) 6px 8px);transform:none}
.masthead nav{align-self:stretch;gap:22px;margin:0;justify-content:flex-start}
.masthead nav a{padding:12px 2px;min-height:48px;border-radius:0;border-bottom:2px solid transparent;font-size:.9rem;color:var(--muted);background:transparent!important}
.masthead nav a[aria-current=page]{border-color:var(--accent);color:var(--text);font-weight:700}
.theme-control{margin-left:auto;gap:8px}.theme-control label{font-size:.78rem;color:var(--muted)}.theme-control select{width:auto;min-height:40px;padding:6px 30px 6px 10px;font-size:.8rem;background:transparent;border-color:var(--border);border-radius:3px}
.connection-bar{margin:0;padding:10px 0;border-top:1px solid var(--hairline);font-size:.76rem;gap:16px}.connection-bar #connection-state{font-weight:400}.local-tag{padding:0!important;border:0!important;border-radius:0!important;letter-spacing:.04em}
.page-heading{padding:24px 0 20px;align-items:center;gap:20px}.workspace-intro{min-width:0}.page-heading h1{font-family:Georgia,Times New Roman,serif;font-size:clamp(2rem,4vw,2.7rem);font-weight:400;letter-spacing:-.045em;line-height:1.15;margin:0 0 9px}.page-heading p{font-size:.9rem;max-width:65ch}
button,.button,input:not([type=checkbox]),select{border-radius:3px;box-shadow:none;min-height:44px;font-size:.9rem}
button,.button{padding:10px 16px;border:1px solid var(--border);background:var(--panel);color:var(--text)}
button:hover:not(:disabled),.button:hover{background:var(--soft);filter:none}
.primary,.control-actions .primary{background:var(--accent);border-color:var(--accent);color:var(--accent-text);font-weight:650}.primary:hover:not(:disabled){background:var(--accent);filter:brightness(.94)}
input:not([type=checkbox]),select{border:1px solid var(--border);background:var(--panel);color:var(--text)}
button:disabled{opacity:.6;cursor:not-allowed}*:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
.workspace-status{display:grid;grid-template-columns:minmax(0,1fr) 310px;border-top:1px solid var(--text);border-bottom:1px solid var(--text);margin:0 0 26px;background:var(--panel)}
.savings-hero{border:0;border-radius:0;background:transparent;padding:20px 30px;display:block;margin:0}
.savings-hero .eyebrow{letter-spacing:.12em;font-size:.7rem;font-weight:650;margin:0;color:var(--muted)}
.savings-number{font-family:Georgia,Times New Roman,serif;font-size:clamp(3.2rem,6vw,4.4rem);font-weight:400;line-height:1.12;letter-spacing:-.045em;margin:9px 0;font-variant-numeric:tabular-nums}
#lifetime-detail{font-size:.85rem}.savings-message{display:none}.savings-hero details{margin:5px 0 0}.savings-hero summary{font-size:.75rem;padding:4px 0;min-height:32px}.savings-hero .control-note{font-size:.8rem;margin:8px 0;max-width:70ch}
#live-resources{background:transparent;margin:0;padding:20px 24px;border:0;border-left:1px solid var(--hairline);border-radius:0;align-self:stretch}
#live-resources .panel-body{padding:0}.resource-strip{display:block}.resource-strip>div{display:flex;justify-content:space-between;padding:10px 0;border:0;border-bottom:1px solid var(--hairline);border-radius:0;background:transparent;gap:16px}.resource-strip>div:last-child{border-bottom:0}.resource-strip dt{font-size:.79rem}.resource-strip small{display:inline;font-size:.71rem;margin-left:6px}.resource-strip dd{font-family:Consolas,monospace;font-size:1.1rem;font-weight:400;white-space:nowrap}.resource-details summary{font-size:.74rem;min-height:32px;padding:4px 0}#resource-status{font-size:.76rem;margin:6px 0;overflow-wrap:anywhere}
.queue-glance{display:flex;gap:0;border-bottom:1px solid var(--hairline);margin:0 0 28px}
.queue-glance>div{flex:1;display:grid;grid-template-columns:1fr auto;align-items:center;column-gap:12px;row-gap:2px;background:transparent;border:0;border-right:1px solid var(--hairline);border-radius:0;padding:0 22px 18px}
.queue-glance>div:first-child{padding-left:0}.queue-glance>div:last-child{border-right:0;padding-right:0}.queue-glance span{font-size:.83rem}.queue-glance strong{grid-column:2;grid-row:1 / span 2;font-family:Consolas,monospace;font-size:1.7rem;font-weight:400}.queue-glance a{font-size:.75rem;margin:0}
.panel{border:0;border-radius:0;background:transparent;margin:0 0 28px;box-shadow:none}
.panel-head{border:0;border-bottom:1px solid var(--hairline);padding:0 0 12px;gap:16px}.panel-head h2{font-size:1.05rem;font-weight:650;margin:0}.panel-body,.guide-content{padding:18px 0 0}
.control-note{font-size:.83rem;line-height:1.6}.control-actions{align-items:center;gap:10px}.queue-actions{margin:0 0 20px;padding:0;border:0}.queue-actions button{font-size:.82rem;padding:9px 14px}#clear-waiting-queue{margin-left:auto;color:var(--danger)}
#control-state{font-weight:600;font-size:.92rem;margin:0 0 14px}#activity>.panel-body>.control-note{margin:0 0 16px;max-width:70ch}.queue-support{border-top:1px solid var(--hairline);margin-top:26px;padding-top:8px}.queue-support>summary{font-size:.87rem}
.active-job{border:0;border-left:3px solid var(--accent);border-radius:0;background:var(--panel);padding:22px 26px;margin:0 0 18px}.active-job h3{font-size:1rem;line-height:1.45;font-weight:650;overflow-wrap:anywhere;margin:0}.active-job>.result-meta{margin:7px 0}.stage-title{font-size:.95rem;font-weight:600;margin:20px 0 9px}.stage-list{display:flex;gap:0;margin:0 0 18px;flex-wrap:wrap}.stage-list li{border:0;border-bottom:2px solid var(--hairline);border-radius:0;padding:8px 13px 8px 0;margin-right:14px;background:transparent;font-size:.76rem;color:var(--muted)}.stage-list .current-step{border:0;border-bottom:2px solid var(--accent);background:transparent;color:var(--text);font-weight:700}.stage-list .completed-step{color:var(--success)}.check-progress{font-family:Consolas,monospace;font-size:1.12rem;font-weight:400;margin:0 0 4px}.active-job details{border-top:1px solid var(--hairline);padding-top:6px;margin-top:16px}.active-job details summary{font-size:.78rem}.active-job>.control-note{margin:5px 0 14px}.result-meta{font-size:.78rem;color:var(--muted)}
.job-progress-head{display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin:16px 0 8px}.job-progress-head .stage-title{margin:0;font-size:.85rem}.job-progress-head .check-progress{margin:0;font-family:inherit;font-size:.81rem;white-space:nowrap}.job-progress-track{height:10px;background:var(--soft);border-radius:3px;overflow:hidden;position:relative}.job-progress-fill{height:100%;background:var(--progress);border-radius:3px;transition:width .6s ease;animation:progress-breathe 2.4s ease-in-out infinite}.job-progress-track.is-measuring .job-progress-fill{width:100%;opacity:.4}.job-progress-track.is-stale .job-progress-fill,.job-progress-track.is-complete .job-progress-fill{animation:none}.job-progress-track.is-stale .job-progress-fill{background:var(--border);opacity:.45}.active-job .job-phase{font-size:.85rem;margin:9px 0 4px;color:var(--muted)}.active-job .job-timing{font-size:.77rem;margin:0;color:var(--muted)}@keyframes progress-breathe{0%,100%{opacity:1}50%{opacity:.68}}
.job-progress-track.is-measuring .job-progress-fill{background:repeating-linear-gradient(135deg,var(--progress) 0 6px,var(--soft) 6px 12px)}
#workflow{max-width:960px;margin:0 0 28px}#workflow .guide-content{padding:20px 0}.setup-steps{gap:0;border-bottom:1px solid var(--hairline);margin:0 0 26px}.setup-steps li{background:transparent;border:0;border-bottom:2px solid transparent;border-radius:0;margin-right:24px;padding:9px 0;font-size:.79rem}.setup-steps li[aria-current=step]{background:transparent;border:0;border-bottom:2px solid var(--accent);color:var(--text);font-weight:700}
.folder-workspace{border:1px solid var(--border);border-left:3px solid var(--accent);background:var(--panel);border-radius:0;padding:22px 24px!important;margin-bottom:22px}.folder-workspace h3{font-size:1.05rem}.folder-picker{border:1px solid var(--border);border-radius:0;background:var(--panel);padding:22px}.browser-list{border:1px solid var(--hairline);border-radius:0}.browser-row{border-color:var(--hairline);padding:4px 8px}.browser-row button{border-radius:0;min-height:44px}.browser-row button:hover{background:var(--soft)!important}
.control-grid{gap:28px}.control-grid label{font-size:.86rem}.control-advanced{margin-top:24px;border-top:1px solid var(--hairline);padding-top:8px}.control-advanced>summary{font-size:.86rem}.control-preview{background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:0;padding:24px}.control-preview h3{font-size:1.1rem}#request-preview ul{background:transparent;border-radius:0;padding:0 0 0 20px;font-size:.85rem}#replacement-confirmation{border:1px solid var(--danger);border-radius:0;padding:16px}
.results-intro{font-size:.86rem;margin:0 0 14px}.result-summary{gap:0;border-bottom:1px solid var(--hairline);margin-bottom:16px}.result-summary button{border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;padding:10px 2px;margin-right:22px;min-height:44px;font-size:.82rem}.result-summary button[aria-pressed=true]{border:0;border-bottom:2px solid var(--accent);background:transparent;font-weight:700}.result-summary button:hover{background:var(--soft)}#result-view-description{font-size:.76rem}.result-count-label{font-size:.79rem}
.result-card{border:0;border-top:1px solid var(--hairline);border-radius:0;background:transparent;padding:20px 0;margin:0}.result-card:first-child{margin-top:8px}.result-card h3{font-size:.94rem;line-height:1.5;font-weight:600}.result-header{align-items:flex-start;gap:20px}.result-card .badge{background:transparent;border:1px solid var(--border);border-radius:3px;font-size:.72rem;padding:3px 8px;font-weight:500;white-space:normal;flex-shrink:0}.result-card .reason{font-size:.85rem;line-height:1.55;margin:8px 0;color:var(--text);max-width:92ch}.result-card details{border:0;padding:0;margin-top:10px}.result-card details summary{font-size:.78rem;min-height:32px}.result-card .result-meta{font-size:.77rem;margin:6px 0}#result-tools{border-top:1px solid var(--hairline);padding-top:4px}#result-tools>summary,.history-options>summary{font-size:.82rem}.report-overview{gap:8px}.report-overview button{min-height:44px;border-radius:3px}.report-card{border:0;border-top:1px solid var(--hairline);border-radius:0}.help{border-top:1px solid var(--hairline);padding-top:8px;background:transparent}.help summary{font-size:.83rem}.help p{font-size:.83rem}.settings-row{grid-template-columns:minmax(0,380px) 210px;align-items:end;gap:16px}.settings-row button{border-radius:3px}.settings-row .setting-field label{margin:0 0 6px}.settings-row label[for=gpu-yield-enabled]{min-height:44px;margin:0}.settings-row input[type=checkbox]{accent-color:var(--accent)}
dialog{border-radius:4px!important;box-shadow:0 12px 50px rgb(0 0 0 / .2);padding:28px!important}.queue-dialog-heading h2{font-family:Georgia,serif;font-weight:400;font-size:1.6rem}.queue-dialog-heading button{min-width:44px;border:0}.attention{color:var(--danger)}footer{border-top:1px solid var(--hairline);font-size:.74rem;padding-top:18px;margin-top:28px}.preview-notice{background:var(--soft);border-bottom:1px solid var(--border);font-size:.8rem;text-align:center;padding:9px 16px}
@media(max-width:760px){main{padding:0 20px 32px}.masthead{padding:16px 20px 0;gap:14px;flex-wrap:wrap}.masthead nav{order:3;flex-basis:100%;gap:28px;justify-content:flex-start}.theme-control{margin-left:auto}.theme-control label{position:absolute;width:1px;height:1px;clip-path:inset(50%);overflow:hidden}.page-heading{padding:26px 0 20px;align-items:flex-start}.page-heading .button{padding:9px 12px;font-size:.82rem}.page-heading h1{font-size:2rem}.page-heading p{font-size:.83rem}.connection-bar .local-tag{display:none}.workspace-status{grid-template-columns:1fr}.savings-hero{padding:22px}.savings-number{font-size:3.4rem}#live-resources{border-left:0;border-top:1px solid var(--hairline);padding:12px 22px}.resource-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.resource-strip>div{display:block;border-bottom:0;padding:0}.resource-strip dd{font-size:1rem;margin-top:4px}.resource-details{margin-top:6px}.queue-glance>div{padding:0 12px 14px;display:block}.queue-glance strong{font-size:1.5rem}.queue-glance span{font-size:.75rem}.queue-glance a{font-size:.72rem}.queue-actions{gap:8px}.queue-actions button{flex:1 1 130px}#clear-waiting-queue{margin-left:0}.active-job{padding:18px}.stage-list li{margin-right:10px;font-size:.72rem}.control-grid{grid-template-columns:minmax(0,1fr);gap:10px}.settings-row{grid-template-columns:1fr;gap:10px}.settings-row button{width:auto;justify-self:start}.result-header{flex-direction:column;gap:8px}.result-summary button{margin-right:16px;font-size:.78rem}.setup-steps li{margin-right:15px;font-size:.73rem}.panel-body,.guide-content,.panel-head{padding-left:0;padding-right:0}}
@media(max-width:460px){.job-progress-head{align-items:flex-start;gap:8px}.job-progress-head .check-progress{white-space:normal;text-align:right;max-width:50%}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
@media(forced-colors:active){.workspace-status,.active-job,.folder-workspace,.result-card{border:1px solid CanvasText}.masthead nav a[aria-current=page],.stage-list .current-step,.result-summary button[aria-pressed=true]{border-bottom:3px solid Highlight}.primary{border:1px solid ButtonText}}
</style>'''


CONSOLE_STYLE = '''<style id="console-style">
/* Instrument-panel geometry, not game terminology: actions retain plain labels. */
body{background-image:linear-gradient(var(--hairline) 1px,transparent 1px),linear-gradient(90deg,var(--hairline) 1px,transparent 1px);background-size:64px 64px;background-attachment:fixed}
main{background:var(--bg);border-left:1px solid var(--hairline);border-right:1px solid var(--hairline)}
.masthead{background:var(--panel);border-top:3px solid var(--accent);border-bottom:1px solid var(--border);padding-bottom:12px}
.brand{font-family:Consolas,monospace;letter-spacing:.035em;text-transform:uppercase}
.brand::before{width:18px;height:18px;border-radius:0;transform:rotate(45deg);background:var(--accent);box-shadow:inset 0 0 0 4px var(--panel)}
.masthead nav a{font-family:Consolas,monospace;letter-spacing:.035em}
.page-heading h1{font-family:Segoe UI,Arial,sans-serif;font-weight:700;letter-spacing:-.025em;font-size:clamp(1.8rem,4vw,2.5rem)}
.connection-bar{font-family:Consolas,monospace}
.workspace-status{position:relative;border:1px solid var(--border);border-top:3px solid var(--accent);box-shadow:inset 5px 0 0 var(--soft)}
.savings-number{font-family:Consolas,monospace;font-weight:600;letter-spacing:-.06em}
.savings-hero .eyebrow{font-family:Consolas,monospace;letter-spacing:.16em}
.queue-glance{gap:10px;border:0}
.queue-glance>div,.queue-glance>div:first-child,.queue-glance>div:last-child{padding:12px 16px;border:1px solid var(--border);background:var(--panel);border-top:2px solid var(--accent)}
.panel-head{border-bottom:1px solid var(--border);padding-bottom:12px}
.panel-head h2{font-family:Consolas,monospace;letter-spacing:.035em}
.active-job{position:relative;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,360px);column-gap:24px;row-gap:4px;border:1px solid var(--border);border-left:3px solid var(--accent);padding:12px 18px;margin-bottom:10px;background:var(--panel);box-shadow:inset 0 3px 0 var(--soft)}
.active-job>h3{grid-column:1;grid-row:1;align-self:center}
.active-job>.result-meta{grid-column:1;grid-row:2;margin:0}
.active-job>.job-progress-head{grid-column:2;grid-row:1;margin:0;align-self:center;min-width:0}
.active-job>.job-progress-track{grid-column:2;grid-row:2;align-self:center}
.active-job>.job-phase{grid-column:1 / -1;margin:2px 0 0}
.active-job>.job-timing{grid-column:1;align-self:center;margin:0}
.active-job>details{grid-column:2;border:0;padding:0;margin:0}
.active-job>details>summary{min-height:44px;display:flex;align-items:center;justify-content:flex-end;gap:6px}
.active-job>details>summary::before{content:'▸';font-size:.8rem}
.active-job>details[open]{grid-column:1 / -1;border-top:1px solid var(--hairline);margin-top:4px;padding-top:4px}
.active-job>details[open]>summary{justify-content:flex-start}
.active-job>details[open]>summary::before{content:'▾'}
.active-job>.attention{grid-column:1 / -1;margin:4px 0}
.active-job::after{content:'';position:absolute;right:8px;top:8px;width:12px;height:12px;border-right:2px solid var(--accent);border-top:2px solid var(--accent);pointer-events:none}
.job-progress-head{max-width:360px;margin-top:18px}
.job-progress-track{width:100%;max-width:360px;height:12px;border:1px solid var(--border);border-radius:0;padding:2px;box-sizing:border-box}
.job-progress-fill{border-radius:0;background:var(--progress);position:relative}
.job-progress-fill::after{content:'';position:absolute;inset:0;background:repeating-linear-gradient(90deg,transparent 0 12px,var(--panel) 12px 14px);opacity:.45;pointer-events:none}
.job-progress-head .check-progress{font-family:Consolas,monospace;font-weight:700}
.job-phase,.job-timing{max-width:65ch}
button,.button,.primary,input:not([type=checkbox]),select{border-radius:0}
button,.button{border-bottom-width:2px}
.primary{box-shadow:inset 0 0 0 1px var(--panel)}
.folder-workspace,.control-preview{border-top:3px solid var(--accent)}
.result-card{border-left:2px solid var(--hairline);padding-left:18px}
dialog{border-radius:0!important;border-top:3px solid var(--accent)}
.queue-dialog-heading h2{font-family:Segoe UI,Arial,sans-serif;font-weight:650}
@media(max-width:760px){body{background-image:none}.masthead{gap:14px}.queue-glance{flex-wrap:wrap}.queue-glance>div{flex:1 1 40%;min-width:0}.active-job{display:block;padding:10px 14px}.active-job>.result-meta{margin:2px 0 6px}.active-job>.job-progress-head{margin:6px 0 4px}.active-job>.job-timing{margin-top:2px}.active-job>details>summary{justify-content:flex-start}.job-progress-head,.job-progress-track{max-width:280px}.workspace-status{box-shadow:none}}
@media(forced-colors:active){body{background-image:none}.job-progress-fill{background:Highlight}.job-progress-fill::after{display:none}.active-job::after{border-color:CanvasText}}
</style>'''


TERMINAL_STYLE = '''<style id="terminal-style">
:root{--bg:#edf0e5;--panel:#f8faef;--text:#22311b;--muted:#4c5e40;--soft:#dde5d1;--accent:#395f25;--accent-text:#ffffff;--border:#6b7e59;--hairline:#becab0;--focus:#395f25;--danger:#8a3c20;--success:#395f25;--lime:#c3ed72;--progress:#395f25;--signal:#765600}
:root[data-theme=dark]{--bg:#0b100b;--panel:#141e13;--text:#dcebc9;--muted:#aabe94;--soft:#202d1c;--accent:#b8dc77;--accent-text:#18220e;--border:#748d5d;--hairline:#35472b;--focus:#e5bc64;--danger:#ffb59a;--success:#b8dc77;--lime:#b8dc77;--progress:#b8dc77;--signal:#e5bc64}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0b100b;--panel:#141e13;--text:#dcebc9;--muted:#aabe94;--soft:#202d1c;--accent:#b8dc77;--accent-text:#18220e;--border:#748d5d;--hairline:#35472b;--focus:#e5bc64;--danger:#ffb59a;--success:#b8dc77;--lime:#b8dc77;--progress:#b8dc77;--signal:#e5bc64}}
body{font-family:Consolas,'Courier New',monospace;background-image:linear-gradient(90deg,transparent 0 31px,var(--hairline) 31px 32px);background-size:32px 32px;font-size:14px}
main{border:8px solid var(--soft);border-top:0;box-shadow:0 0 0 1px var(--border);padding:0 24px 32px;max-width:1180px}
.masthead{max-width:1180px;padding:14px 24px;background:var(--soft);border:1px solid var(--border);border-top:6px solid var(--border);gap:26px}
.brand{font-size:1.35rem;letter-spacing:.08em;color:var(--accent)}
.brand::before{transform:none;width:16px;height:20px;border:1px solid var(--accent);background:repeating-linear-gradient(0deg,var(--accent) 0 2px,transparent 2px 5px);box-shadow:none}
.masthead nav{gap:8px}.masthead nav a{border:1px solid var(--border);padding:10px 16px;color:var(--text);min-height:44px}
.masthead nav a[aria-current=page]{background:var(--accent)!important;color:var(--accent-text);border-color:var(--accent)}
.theme-control select{background:var(--panel);font-family:inherit}
.connection-bar{color:var(--muted);border-bottom:1px solid var(--hairline);padding:10px 0}
.page-heading{padding:18px 0 16px}.page-heading h1{font-family:inherit;font-size:clamp(1.5rem,3vw,2rem);letter-spacing:.04em;text-transform:uppercase}
.page-heading p{font-size:.83rem}.workspace-status{grid-template-columns:minmax(0,1fr) 300px;border:1px solid var(--border);box-shadow:inset 0 0 0 4px var(--bg);margin-bottom:16px}
.savings-hero{padding:16px 22px}.savings-number{font-size:clamp(2.6rem,5vw,3.4rem);color:var(--accent);margin:6px 0;letter-spacing:-.035em}
.savings-hero .eyebrow{color:var(--signal);font-size:.75rem;letter-spacing:.08em}#live-resources{padding:10px 20px}.resource-strip>div{padding:8px 0}
.queue-glance{gap:8px;margin-bottom:20px}.queue-glance>div,.queue-glance>div:first-child,.queue-glance>div:last-child{padding:8px 12px;border-top:1px solid var(--border)}
.queue-glance strong{font-size:1.4rem;color:var(--signal)}
.panel-head h2{color:var(--signal);text-transform:uppercase;font-size:.95rem;letter-spacing:.08em}
.active-job{background:var(--panel);border-left:3px solid var(--signal);padding:8px 14px;row-gap:2px;column-gap:20px;margin-bottom:8px;box-shadow:inset 0 0 0 2px var(--bg)}
.active-job h3{font-family:Segoe UI,Arial,sans-serif;font-size:.9rem}.active-job::after{display:none}
.active-job>.job-phase{font-size:.77rem}.active-job>.job-timing,.active-job>.result-meta{font-size:.72rem}
.job-progress-head .stage-title{font-size:.75rem}.job-progress-head .check-progress{font-size:.73rem;color:var(--accent)}
.job-progress-track{height:14px;border-color:var(--border);background:var(--bg)}
.job-progress-fill{animation:none;transition:width .4s ease}.job-progress-fill::after{opacity:.65;background:repeating-linear-gradient(90deg,transparent 0 7px,var(--bg) 7px 9px)}
.job-progress-track.is-measuring .job-progress-fill{animation:progress-breathe 2.4s ease-in-out infinite}
button,.button,input:not([type=checkbox]),select{font-family:inherit;font-size:.8rem}
button,.button{background:var(--soft);border:1px solid var(--border);box-shadow:inset 0 0 0 2px var(--bg)}
.primary,.control-actions .primary{background:var(--accent);color:var(--accent-text);box-shadow:none}
.result-card h3{font-family:Segoe UI,Arial,sans-serif}.result-card .badge{color:var(--signal);border-color:var(--border)}
.queue-dialog-heading h2{font-family:inherit}dialog{background:var(--panel);border:2px solid var(--border)}
.queue-support{margin-top:8px;padding-top:0}.queue-support>summary{min-height:44px;display:flex;align-items:center;gap:6px}.queue-support>summary::before{content:'▸'}.queue-support[open]>summary::before{content:'▾'}
#activity{margin-bottom:8px}#current-work>.result-meta{margin:6px 0;font-size:.72rem}
#activity>.panel-head{padding-bottom:6px}#activity>.panel-body{padding-top:8px}
#activity #control-state{margin:0 0 6px;font-size:.82rem}
#activity .queue-actions{margin:0 0 8px;gap:8px}#activity .queue-actions button{padding:6px 12px}
#queue-clear-feedback:empty{margin:0;padding:0}
@media(min-width:1000px){
 .active-job{grid-template-columns:minmax(160px,1fr) minmax(150px,1fr) minmax(0,300px) 80px;column-gap:16px;padding:6px 12px;row-gap:2px}
 .active-job>h3{grid-column:1;grid-row:1}.active-job>.result-meta{grid-column:1;grid-row:2}
 .active-job>.job-phase{grid-column:2;grid-row:1;margin:0;align-self:center}
 .active-job>.job-timing{grid-column:2;grid-row:2;margin:0;align-self:center}
 .active-job>.job-progress-head{grid-column:3;grid-row:1;gap:8px}
 .active-job>.job-progress-head .check-progress{white-space:normal;text-align:right}
 .active-job>.job-progress-track{grid-column:3;grid-row:2}
 .active-job>details{grid-column:4;grid-row:1 / span 2;align-self:center}
 .active-job>details[open]{grid-column:1 / -1;grid-row:auto;align-self:stretch}
 .active-job>.attention{grid-row:auto}
}
.workspace-footer{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:12px;border-top:1px solid var(--hairline);margin-top:8px}
.workspace-footer>.help{margin:0;padding:0;border:0}.workspace-footer>.help>summary{min-height:44px;display:flex;align-items:center;gap:6px;font-size:.74rem}.workspace-footer>.help>summary::before{content:'▸'}.workspace-footer>.help[open]>summary::before{content:'▾'}
.workspace-footer>footer{border:0;margin:0;padding:12px 0;font-size:.7rem;max-width:65ch;text-align:right}
main{padding-bottom:8px}
@media(max-width:760px){.workspace-footer{grid-template-columns:1fr;gap:0}.workspace-footer>footer{text-align:left;padding:4px 0 8px}main{padding-bottom:8px}}
@media(max-width:760px){main{padding:0 12px 24px;border-width:4px}.masthead{padding:12px 16px;gap:12px}.masthead nav{gap:6px}.masthead nav a{padding:10px 12px}.workspace-status{grid-template-columns:1fr}.active-job{padding:8px 12px}.page-heading h1{font-size:1.5rem}.savings-hero{padding:14px 18px}}
@media(prefers-reduced-motion:reduce){.job-progress-fill{animation:none!important;transition:none!important}}
@media(forced-colors:active){main,.workspace-status{box-shadow:none}.masthead nav a[aria-current=page]{border:3px solid Highlight}.job-progress-fill{background:Highlight}}
</style>'''


def restyle(html):
    """Existing inputs/actions/IDs stay intact, including disclosure behavior."""
    start = html.index('<section class="panel savings-hero"')
    end = html.index('<section id="queue-overview"', start)
    html = html[:start] + '<div class="workspace-status">' + html[start:end] + '</div>' + html[end:]
    html = html.replace('What happened, why it happened, and how much smaller each video became. Your latest attempt is shown first.',
                        'The latest result for each video. Open Details for checks and earlier attempts.')
    html = html.replace('>Your server · your media</span>', '>MEDIA WORKSPACE</span>')
    html = html.replace('The highlighted step shows what is happening. Each percentage belongs to the current check.',
                        'Progress shows the current check, not the whole video.')
    progress_note = '<p class="control-note">Progress shows the current check, not the whole video.</p>'
    html = html.replace(progress_note, '', 1)
    support_start = html.index('<details class="queue-support">')
    support_end = html.index('</details>', support_start)
    html = html[:support_end] + progress_note + html[support_end:]
    # Results come first; explanations and history housekeeping follow the list.
    secondary = []
    for marker in ('<details><summary>Understanding results</summary>', '<details class="history-options">'):
        start = html.index(marker)
        end = html.index('</details>', start) + len('</details>')
        secondary.append(html[start:end])
        html = html[:start] + html[end:]
    anchor = '<button id="show-results" type="button" hidden>Show more results</button>'
    html = html.replace(anchor, anchor + ''.join(secondary), 1)
    # File age is an optional filter, not another mandatory setup step.
    start = html.index('<div class="control-grid"><div><label for="file-age-unit">')
    end = html.index('<label for="output-preset">', start)
    selection = html[start:end]
    html = html[:start] + '<details class="control-advanced selection-options"><summary>Filter by file age (optional)</summary>' + selection + '</details>' + html[end:]
    # Keep secondary guidance available without a tall stack below the queue.
    pause_note = '<p class="control-note">Pause new starts lets active jobs finish. Freeze display only stops screen updates; jobs continue.</p>'
    if pause_note in html:
        html = html.replace(pause_note, '', 1)
        start = html.index('<details class="queue-support">')
        end = html.index('</details>', start)
        html = html[:end] + pause_note + html[end:]
    start = html.index('<details class="panel help">')
    end = html.index('</footer>', start) + len('</footer>')
    html = html[:start] + '<div class="workspace-footer">' + html[start:end] + '</div>' + html[end:]
    return html.replace('</head>', STYLE + CONSOLE_STYLE + TERMINAL_STYLE + '</head>')
