"""Native dashboard controls; no external assets or source-file write actions."""
STYLE = '''<style>
.control-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.control-grid label{display:block;font-weight:600;margin:12px 0 6px}.control-grid input:not([type=checkbox]),.control-grid select{width:100%;padding:10px;border:1px solid var(--line);border-radius:7px;background:white;color:var(--ink)}.control-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}.control-actions button,.browser-row button{border:1px solid var(--line);background:white;border-radius:7px;padding:9px 13px}.control-actions .primary{background:var(--lime);border-color:var(--lime);color:#203719;font-weight:600}.control-note{color:var(--muted);font-size:12px;line-height:1.6}.browser-list{max-height:260px;overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:12px}.browser-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.browser-row span{min-width:0}.control-preview{background:#f5f8ef;border:1px solid #dce7cb;border-radius:8px;padding:16px;margin-top:18px;overflow-wrap:anywhere}.control-preview ul{max-height:160px;overflow:auto}.control-feedback{white-space:pre-wrap;overflow-wrap:anywhere;margin-top:12px}.control-jobs{max-height:350px;overflow:auto}.control-jobs p{border-bottom:1px solid var(--line);padding-bottom:10px;overflow-wrap:anywhere}.control-log{white-space:pre-wrap;max-height:320px;overflow:auto}.control-jobs button{margin-left:10px}#workflow{margin-bottom:24px} @media(max-width:850px){.control-grid{grid-template-columns:1fr}}
.folder-workspace{border-left:4px solid var(--lime);padding:16px 20px;background:#f5f8ef;border-radius:8px;margin-bottom:20px}.folder-workspace h3{margin:0 0 6px;overflow-wrap:anywhere}.folder-picker{border:1px solid var(--line);padding:18px;border-radius:10px;margin:16px 0}.folder-picker input{width:100%;padding:10px;border:1px solid var(--line);border-radius:7px}.folder-picker .browser-row button{width:100%;text-align:left;border:0;background:transparent}.control-advanced{margin-top:18px;border-top:1px solid var(--line);padding-top:14px}.control-advanced summary{cursor:pointer;color:var(--muted)}[hidden]{display:none!important}
</style>'''

PANEL = '''<section class="panel" id="workflow"><div class="panel-head"><h2>New media job</h2><span class="badge">Safe copies only</span></div><div class="guide-content">
<p class="control-note" id="control-availability">Connecting to job controls…</p>
<div class="folder-workspace"><h3 id="active-folder">Select a folder to get started</h3><p id="folder-description" class="control-note">Choose the media folder you want to work on. Nothing starts automatically.</p><button id="browse-media" class="button" type="button">Select folder</button></div>
<input id="source-path" type="hidden">
<div id="folder-picker" class="folder-picker" hidden><h3>Select a folder</h3>
<label for="folder-path">Server folder path</label><input id="folder-path" placeholder="TV/Series/Season 1" autocomplete="off">
<div class="control-actions"><button id="open-folder-path" type="button">Open path</button><button id="browse-up" type="button">Up one level</button></div>
<p id="browse-location" class="control-note">Media root</p><div id="media-browser" class="browser-list" aria-label="Media browser"></div>
<button id="browse-more" type="button" hidden>More folders</button><div class="control-actions"><button id="choose-folder" class="primary" type="button" disabled>Use this folder</button><button id="cancel-folder" type="button">Cancel</button></div></div>
<div id="folder-actions" hidden><div class="control-grid"><div><label for="source-depth">Folder scope</label><select id="source-depth"><option value="recursive">This folder and all subfolders</option><option value="top">This folder only — one level</option></select><label for="video-choice">Work on</label><select id="video-choice"><option value="">All videos in this selection</option></select><p class="control-note">Choose all listed videos, or select one video. Nested paths identify videos with the same name.</p></div>
<div><label for="operation">Action</label>
<select id="operation"><option value="analyze">Analyze only — no encoding</option><option value="test">Test short samples — keep originals</option><option value="encode">Encode full safe copies if tests pass</option><option value="replace">Convert and replace originals — only after all checks pass</option><option value="keep">Keep originals — record, do not convert</option></select>
<p id="replacement-availability" class="control-note"></p>
</div></div>
<div class="control-grid"><div><label for="file-age-unit">File creation age</label><select id="file-age-unit" aria-describedby="file-age-help"><option value="all">All files — any creation date</option><option value="hours">Created within the last… hours</option><option value="days">Created within the last… days</option><option value="weeks">Created within the last… weeks</option></select></div><div id="file-age-value-wrap" hidden><label for="file-age-value">Number of hours, days or weeks</label><input id="file-age-value" type="number" min="1" max="100000" step="1" value="1" disabled aria-describedby="file-age-help"></div></div>
<p id="file-age-help" class="control-note">Applies to this new request, including subfolders. Uses the filesystem creation date, not the movie release date or last modified date. Files with unavailable creation dates are excluded when filtering. Preview shows matching files; existing queue entries are unchanged.</p>
<details class="control-advanced"><summary>Encoding options · Automatic by default</summary><div class="control-grid"><div>
<label for="codec-choice">Encoding format</label><select id="codec-choice"><option value="auto">Automatic — compare verified HEVC / AV1</option><option value="hevc">HEVC / H.265 only</option><option value="av1">AV1 only</option></select>
<label for="hardware-choice">Hardware preference</label><select id="hardware-choice"><option value="auto">Auto-detect supported GPU</option><option value="nvidia">NVIDIA</option><option value="amd">AMD</option><option value="intel">Intel</option></select>
</div><div>
<label for="quality-choice">Encoder quality preset</label><select id="quality-choice"><option value="auto">Automatic — compare balanced / compact</option><option value="transparent">Transparent</option><option value="balanced">Balanced</option><option value="compact">Compact</option></select>
<label for="minimum-savings">Minimum size reduction (%) — 0 accepts any smaller result</label><input id="minimum-savings" type="number" min="0" max="90" step="0.1" value="0">
<label for="legacy-color">Missing color information</label><select id="legacy-color"><option value="inspect">Inspect and preserve source color; never guess</option><option value="bt709-limited">Sample test only: assume BT.709 limited range</option></select><p class="control-note">Inspection uses declared metadata and verified codec defaults, preserving unspecified color tags where supported. Choose Retry skipped/failed files to reconsider earlier skips. The BT.709 assumption is sample-only and cannot authorize full conversion or replacement.</p>
<label for="recheck-history">Previously processed files</label><select id="recheck-history"><option value="reuse">Use saved history (default)</option><option value="retry">Retry skipped/failed files only</option><option value="all">Recheck everything, including successful conversions</option></select>
<p class="control-note">Retry only includes unchanged skipped, failed or interrupted files. It excludes successful conversions, deliberate Keep original decisions, new/changed files and active jobs. Recheck everything can re-encode successful outputs.</p>
<p class="control-note">All presets must pass the same quality checks. Resolution, frame rate, color, audio and subtitles are protected. No CPU fallback. PQ/HDR10/HDR10+ and HLG use checked preservation routes. Dolby Vision requires the separate opt-in preservation workflow and is not yet integrated here.</p>
</div></div></details>
<div class="control-actions"><button id="preview-job" class="primary" type="button" disabled>Preview request</button></div>
<div id="request-preview" class="control-preview" hidden><h3>3 · Review before submitting</h3><p id="preview-description"></p><ul id="preview-files"></ul><p class="control-note">Original files will never be replaced or deleted. A folder request is limited to 100 videos. Passing full copies still need playback review.</p><div class="control-actions"><button id="submit-job" class="primary" type="button" disabled>Confirm and queue</button></div></div>
</div><p id="control-feedback" class="control-feedback" role="status" aria-live="polite"></p>
<details class="control-advanced"><summary>Job queue & logs</summary><p id="control-state" class="control-note"></p><div class="control-actions"><button id="pause-selected" type="button" disabled>Pause after current job</button><button id="resume-selected" type="button" disabled>Resume queue</button></div><div id="selected-jobs" class="control-jobs"></div><pre id="control-log" class="control-log" hidden></pre></details>
</div></section>'''

SCRIPT = '''<script>
let controlToken=null,previewId=null,browsePath='',browseParent=null,browseNext=null,controlTimer=null;
let activeFolder=null,folderFiles=[],browseVersion=0,selectionVersion=0,previewVersion=0,controlReady=false,workspaceReady=false;
const controlElement=id=>document.querySelector('#'+id);
function controlMessage(text){if(controlElement('control-feedback').textContent!==text)controlElement('control-feedback').textContent=text}
let previewReplaces=false;
function invalidatePreview(){previewVersion++;previewId=null;previewReplaces=false;controlElement('submit-job').disabled=true;controlElement('request-preview').hidden=true;const box=controlElement('confirm-replacement');if(box)box.checked=false}
function collapseSubmittedSetup(body){
 const section=controlElement('workflow');
 if(section?.tagName!=='DETAILS'||!(body.queued>0))return;
 const message=controlElement('setup-submission');
 if(message)message.textContent=body.queued+' job(s) queued · Open to set up more';
 section.open=false;
 controlElement('setup-toggle')?.focus({preventScroll:true});
 section.scrollIntoView?.({block:'start',behavior:'instant'});
}
document.querySelectorAll('a[href="#workflow"]').forEach(link=>link.addEventListener('click',()=>{
 const section=controlElement('workflow');if(section?.tagName==='DETAILS')section.open=true;
}));
async function controlCall(action,extra={}){
 const response=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json','X-MuxMender-CSRF':controlToken||''},body:JSON.stringify({action,...extra})});
 const body=await response.json();if(!response.ok)throw Error(body.error||'Request failed');return body;
}
async function browseMedia(path='',offset=0){try{
 const version=++browseVersion;selectionVersion++;controlElement('choose-folder').disabled=true;
 const response=await fetch('/api/media?path='+encodeURIComponent(path)+'&offset='+offset);const body=await response.json();if(!response.ok)throw Error(body.error);
 if(version!==browseVersion)return;
 browsePath=body.path;browseParent=body.parent;browseNext=body.next_offset;
 controlElement('browse-location').textContent='/media/'+(browsePath==='.'?'':browsePath);
 const list=controlElement('media-browser');list.replaceChildren();
 controlElement('folder-path').value=body.path==='.'?'':body.path;
 for(const row of body.entries.filter(row=>row.directory)){const line=document.createElement('div');line.className='browser-row';
 const button=document.createElement('button');button.type='button';button.textContent='Folder · '+row.name+' ›';button.addEventListener('click',()=>browseMedia(row.path));line.append(button);list.append(line)}
 if(!body.entries.some(row=>row.directory)){const note=document.createElement('p');note.textContent='No subfolders on this page. You can select this folder.';list.append(note)}
 controlElement('choose-folder').disabled=false;
 controlElement('browse-more').hidden=browseNext===null;controlElement('browse-up').disabled=browseParent===null;
 }catch(error){controlMessage(error.message)}
}
function closeFolderPicker(){browseVersion++;selectionVersion++;controlElement('folder-picker').hidden=true;controlElement('browse-media').focus?.()}
controlElement('browse-media').addEventListener('click',()=>{controlElement('folder-picker').hidden=false;controlElement('folder-path').focus?.();browseMedia(activeFolder||'')});
controlElement('cancel-folder').addEventListener('click',closeFolderPicker);
controlElement('folder-picker').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();closeFolderPicker()}});
controlElement('folder-path').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();browseMedia(controlElement('folder-path').value)}});
controlElement('open-folder-path').addEventListener('click',()=>browseMedia(controlElement('folder-path').value));
controlElement('browse-up').addEventListener('click',()=>{if(browseParent!==null)browseMedia(browseParent)});
controlElement('browse-more').addEventListener('click',()=>{if(browseNext!==null)browseMedia(browsePath,browseNext)});
async function selectFolder(path){const version=++selectionVersion;workspaceReady=false;invalidatePreview();controlElement('preview-job').disabled=true;controlElement('choose-folder').disabled=true;try{
 const recursive=controlElement('source-depth').value!=='top';controlMessage('Reading the selected folder…');
 let rows=[],offset=0,selectedPath=null;
 do{const r=await fetch('/api/media?path='+encodeURIComponent(path)+'&offset='+offset+'&videos=true&recursive='+recursive);const b=await r.json();if(!r.ok)throw Error(b.error);if(version!==selectionVersion)return;
 selectedPath=b.path;rows.push(...b.entries.filter(row=>!row.directory));offset=b.next_offset;
 controlMessage('Reading the selected folder… '+rows.length+' videos found');
 }while(offset!==null);
 activeFolder=selectedPath;folderFiles=rows;workspaceReady=rows.length>0;invalidatePreview();
 const choice=controlElement('video-choice');choice.replaceChildren();const all=document.createElement('option');all.value='';all.textContent='All '+rows.length+' videos in this selection';choice.append(all);
 for(const row of rows){const option=document.createElement('option');option.value=row.path;option.textContent=row.name;choice.append(option)}choice.value='';
 controlElement('source-path').value=activeFolder;
 controlElement('active-folder').textContent='/media/'+(activeFolder==='.'?'':activeFolder);controlElement('folder-description').textContent=rows.length+' videos · '+(recursive?'Including all subfolders':'This folder only');
 controlElement('browse-media').textContent='Change folder';controlElement('folder-picker').hidden=true;controlElement('folder-actions').hidden=false;controlElement('preview-job').disabled=!controlReady||!workspaceReady;controlMessage(rows.length?rows.length+' videos found. Choose an action, then review your selection.':'No videos found. Include subfolders or choose another folder.');controlElement('video-choice').focus?.();
 }catch(error){controlMessage(error.message)}finally{controlElement('choose-folder').disabled=false}}
controlElement('choose-folder').addEventListener('click',()=>selectFolder(browsePath));
controlElement('source-depth').addEventListener('change',()=>{if(activeFolder!==null)selectFolder(activeFolder)});
controlElement('video-choice').addEventListener('change',()=>{const file=controlElement('video-choice').value;
 if(file&&!folderFiles.some(row=>row.path===file))return;controlElement('source-path').value=file||activeFolder;invalidatePreview()});
for(const id of ['source-path','operation','codec-choice','hardware-choice','quality-choice','minimum-savings','recheck-history','legacy-color'])controlElement(id).addEventListener('change',invalidatePreview);
controlElement('source-path').addEventListener('input',invalidatePreview);
controlElement('file-age-unit').addEventListener('change',()=>{const all=controlElement('file-age-unit').value==='all';controlElement('file-age-value-wrap').hidden=all;controlElement('file-age-value').disabled=all;invalidatePreview()});
controlElement('file-age-value').addEventListener('input',invalidatePreview);
controlElement('preview-job').addEventListener('click',async()=>{invalidatePreview();const version=previewVersion;try{
 if(activeFolder===null||!workspaceReady)throw Error('Select a folder and wait for its video list');
 const settings={path:controlElement('source-path').value,recursive:!controlElement('video-choice').value&&controlElement('source-depth').value!=='top',mode:controlElement('operation').value,codec:controlElement('codec-choice').value,hardware:controlElement('hardware-choice').value,quality:controlElement('quality-choice').value,minimum_savings:Number(controlElement('minimum-savings').value),history_mode:controlElement('recheck-history').value||'reuse'};
 settings.legacy_color=controlElement('legacy-color').value||'inspect';
 settings.age_unit=controlElement('file-age-unit').value||'all';settings.age_value=settings.age_unit==='all'?null:Number(controlElement('file-age-value').value);
 if(settings.age_unit!=='all'&&(!Number.isInteger(settings.age_value)||settings.age_value<1||settings.age_value>100000))throw Error('Enter a whole number from 1 to 100000 for file age.');
 const body=await controlCall('preview',{settings});if(version!==previewVersion)return;previewId=body.preview_id;
 previewReplaces=body.settings.mode==='replace';
 controlElement('replacement-confirmation').hidden=!previewReplaces;
 const actionName={analyze:'Inspect only',test:'Test samples',encode:'Create smaller copies',replace:'Convert and permanently replace originals',keep:'Keep originals'}[body.settings.mode];
 controlElement('preview-description').textContent=body.files.length+' video(s) · '+actionName+' · Format: '+body.settings.codec+' · Hardware: '+body.settings.hardware+' · Preset: '+body.settings.quality+' · Minimum size reduction: '+body.settings.minimum_savings+'%. '+body.note;
 const age=body.age_filter||{};controlElement('preview-description').textContent+=' Creation age: '+(body.settings.age_unit==='all'?'All files':'Within the last '+body.settings.age_value+' '+body.settings.age_unit)+'. '+(age.outside_age_window||0)+' outside the age window; '+(age.creation_date_unavailable||0)+' excluded because creation date is unavailable. Selection is fixed at preview time.';
 const list=controlElement('preview-files');list.replaceChildren();for(const row of body.files){const li=document.createElement('li');li.textContent=row.path+' ('+(row.signature[0]/1e9).toFixed(2)+' GB)'+(row.history_reason?' — Will skip. '+row.history_reason:'');list.append(li)}
 controlElement('request-preview').hidden=false;controlElement('submit-job').disabled=previewReplaces;controlMessage('Review the file list and settings. Preview expires in 10 minutes.');controlElement('preview-description').focus?.();
 }catch(error){controlMessage(error.message)}});
controlElement('confirm-replacement').addEventListener('change',()=>{controlElement('submit-job').disabled=!previewId||(previewReplaces&&!controlElement('confirm-replacement').checked)});
controlElement('submit-job').addEventListener('click',async()=>{if(!previewId||(previewReplaces&&!controlElement('confirm-replacement').checked))return;controlElement('submit-job').disabled=true;try{const body=await controlCall('submit',{preview_id:previewId,confirm_replace:previewReplaces&&controlElement('confirm-replacement').checked});invalidatePreview();controlMessage(body.queued+' new job(s) recorded. '+(body.history_skipped||[]).length+' skipped using saved history or active jobs.');collapseSubmittedSetup(body);refreshControls()}catch(error){controlMessage(error.message);controlElement('submit-job').disabled=!previewId}});
for(const [id,action] of [['pause-selected','pause'],['resume-selected','resume']])controlElement(id).addEventListener('click',async()=>{try{const body=await controlCall(action);controlMessage(body.message);refreshControls()}catch(error){controlMessage(error.message)}});
controlElement('save-resource-profile').addEventListener('click',async()=>{try{const body=await controlCall('resource-profile',{profile:controlElement('resource-profile').value});controlMessage(body.message);refreshControls()}catch(error){controlMessage(error.message)}});
async function refreshControls(){try{
 if(globalThis.liveUpdatesPaused)return;
 const response=await fetch('/api/controls',{signal:AbortSignal.timeout(8000)});if(!response.ok)throw Error('Job controls are unavailable. Check the app connection or ask your administrator to enable them.');const body=await response.json();controlToken=body.csrf_token;
 if(!controlElement('resource-profile').initialized){controlElement('resource-profile').value=body.resource_profile||'shared';controlElement('resource-profile').initialized=true}
 const resource=body.resources||{},metrics=resource.telemetry||{};
 const metric=(key,suffix,digits=0)=>Number.isFinite(metrics[key])?metrics[key].toFixed(digits)+suffix:'Unavailable';
 controlElement('resource-status').textContent='Host CPU '+metric('cpu_percent','%')+(Number.isFinite(metrics.container_cpu_percent)?' · App CPU allocation '+metric('container_cpu_percent','%'):'')+' · Available RAM '+metric('available_gib',' GiB',1)+' · GPU compute '+metric('gpu_compute_percent','%')+' · GPU encode '+metric('gpu_encode_percent','%')+' · GPU decode '+metric('gpu_decode_percent','%')+' · Free VRAM '+metric('vram_free_gib',' GiB',1)+' · '+(resource.active||0)+' workers · '+(resource.reason||'Collecting measurements');
 controlElement('control-availability').textContent=body.ready?'Ready · choose your action below':'Worker unavailable: '+(body.error||'starting');
 controlReady=body.ready;controlElement('preview-job').disabled=!body.ready||!workspaceReady;controlElement('pause-selected').disabled=!body.ready||body.paused;controlElement('resume-selected').disabled=!body.ready||!body.paused;
 controlElement('replacement-availability').textContent=body.replacement_enabled?'Replacement available. Choose it explicitly and confirm to remove originals after verification.':'Copy-only storage: make /media writable in TrueNAS to use replacement. No replacement environment variable is needed.';
 controlElement('control-state').textContent=(body.wait_reason||(body.paused?(body.pause_reason||'Queue paused'):'Queue ready'))+' · '+(body.counts.pending||0)+' waiting · '+(body.counts.running||0)+' running';
 if(typeof receiveControls==='function')receiveControls(body);
 }catch(error){controlElement('control-availability').textContent=error.message;controlElement('preview-job').disabled=true;if(typeof connectionUpdate==='function')connectionUpdate('controls',false)}
 finally{clearTimeout(controlTimer);controlTimer=setTimeout(refreshControls,10000)}}refreshControls();
</script>'''
