"""User-facing media workspace. Developer dashboards remain separate."""
from ui.controls import PANEL, SCRIPT
from ui.workspace import STYLE, SCRIPT as RESULTS_SCRIPT
from ui.workspace_history import SCRIPT as HISTORY_SCRIPT
from app_version import VERSION

controls = PANEL[:PANEL.index('<details class="control-advanced"><summary>Job queue & logs')]+ '</div></section>'
for old,new in [
    ('New media job','1. Select and set up'),('Safe copies only','Keep originals by default'),
    ('TV/Series/Season 1','TV/Series/Season 1'),
    ('3 · Review before submitting','2. Review and start'),('Confirm and queue','Start selected jobs'),
    ('Preview request','Review selection'),('Analyze only — no encoding','Inspect videos — no conversion'),
    ('Test short samples — keep originals','Test quality and size — samples only'),
    ('Encode full safe copies if tests pass','Create smaller copies — only if checks pass'),
    ('Keep originals — record, do not convert','Keep originals — do not convert'),
    ('Transparent</option>','Highest quality preset</option>'),
    ('Encoding options · Automatic by default','Advanced settings · automatic by default'),
    ('id="preview-description"','id="preview-description" tabindex="-1"'),
    ('<ul id="preview-files"></ul>','<ul id="preview-files"></ul><div id="replacement-confirmation" hidden><label for="confirm-replacement"><input type="checkbox" id="confirm-replacement"> I approve permanently replacing these originals after automated validation, without playback review.</label></div>'),
    ('Original files will never be replaced or deleted. A folder request is limited to 100 videos. Passing full copies still need playback review.','Safe-copy mode keeps originals. Replacement removes originals only after full validation and verified copying. Outputs use MKV; filename conflicts are skipped.'),
    ('<h3>Select a folder</h3>','<h3 id="picker-title">Select a folder</h3><p id="path-help" class="control-note">Browse your server’s media folder or enter a relative path. No upload is needed.</p>'),
    ('id="folder-picker" class="folder-picker"','id="folder-picker" class="folder-picker" role="region" aria-labelledby="picker-title"'),
    ('id="folder-path" placeholder=','id="folder-path" aria-describedby="path-help" placeholder=')]:
    controls=controls.replace(old,new)

# Native disclosure preserves keyboard/screen-reader behavior and hides only
# setup, never progress or results. Form values survive closing/reopening.
controls=controls.replace('<section class="panel" id="workflow"><div class="panel-head">',
    '<details class="panel" id="workflow" open><summary class="panel-head" id="setup-toggle">')
controls=controls.replace('</span></div><div class="guide-content">',
    '</span><span id="setup-submission" role="status" aria-live="polite"></span></summary><div class="guide-content">',1)
controls=controls.removesuffix('</section>')+'</details>'

HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>MuxMender · Media workspace</title>'''+STYLE+'''</head><body>
<a class="skip-link" href="#main">Skip to workspace</a>
<header class="masthead"><a class="brand" href="#main">MuxMender</a><nav aria-label="Main"><a href="#workflow">Set up</a><a href="#activity">Progress</a><a href="#results">Results</a></nav><div class="theme-control"><label for="theme">Appearance</label><select id="theme"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></div></header>
<main id="main" tabindex="-1"><div class="page-heading"><h1>Media workspace</h1><p class="safety-note">Keep originals by default. Replacement requires an explicit choice and confirmation.</p></div>
<section class="panel savings-hero" aria-labelledby="savings-title"><div><p class="eyebrow" id="savings-title">Lifetime library space saved</p><p class="savings-number" id="lifetime-saved">—</p><p id="lifetime-detail">Loading confirmed replacement history…</p><p class="control-note">Confirmed replacements only. Retained output copies and snapshots still occupy disk space. Older work without a receipt is not included.</p></div><div class="savings-symbol" aria-hidden="true">↓</div></section>
<section class="panel" id="live-resources" aria-labelledby="live-resources-title"><div class="panel-head"><h2 id="live-resources-title">Server resources</h2></div><div class="panel-body"><p id="resource-status" class="control-note">Collecting CPU, GPU and available RAM measurements…</p></div></section>
<section class="panel" id="activity" aria-labelledby="activity-title"><div class="panel-head"><h2 id="activity-title">Processing dashboard</h2><span id="connection-state" role="status">Connecting…</span></div><div class="panel-body">
<p id="control-state">Checking queue…</p><p class="control-note">Follow the highlighted step. Percentages describe the current check—not the whole video.</p><div class="control-actions"><button id="pause-selected" type="button" disabled>Pause after current job</button><button id="resume-selected" type="button" disabled>Resume queue</button><button id="toggle-updates" type="button" aria-pressed="false">Pause live updates</button></div>
<details><summary>Resource settings</summary><div class="control-actions"><div><label for="resource-profile">Shared-server resource use</label><select id="resource-profile"><option value="quiet">Quiet · one file</option><option value="shared" selected>Shared host · up to two files</option><option value="faster">Faster · up to four files</option></select></div><button id="save-resource-profile" type="button">Apply resource profile</button></div><p class="control-note">New workers start only with sustained headroom. Busy-server backoff stops new starts; running jobs finish at lower CPU priority. This is not a hard CPU/GPU limit. Unknown GPU telemetry restricts processing to one file.</p></details>
<p class="control-note">Pausing the queue lets its current job finish. Pausing live updates only freezes this display.</p><div id="current-work">No running job reported yet.</div><p id="activity-announcement" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></p>
</div></section>
'''+controls+'''
<section class="panel" id="results" aria-labelledby="results-title"><div class="panel-head"><h2 id="results-title">Results</h2><span id="result-count"></span></div><div class="panel-body">
<p class="control-note">Latest attempt per video, newest outcome first. Expand previous attempts to see history. Active retries stay visible. Times use your browser's local time zone.</p>
<p class="control-note">Ready for review means automated checks passed—not a guarantee of identical visual quality. Play the copy before replacing an original. Size reduction is not disk space freed while both copies are retained.</p>
<div class="control-grid"><div><label for="result-search">Find a video</label><input id="result-search" type="search" placeholder="Search by video name"></div><div><label for="result-filter">Show</label><select id="result-filter"><option value="all">Finished work</option><option value="active">Queued or running</option><option value="ready">Ready for review</option><option value="kept">Original kept</option><option value="attention">Needs attention</option><option value="replaced">Replaced</option><option value="complete">Inspections and tests</option><option value="history">All requests</option></select></div><div><label for="result-sort">Sort by</label><select id="result-sort"><option value="newest">Newest outcome first</option><option value="oldest">Oldest outcome first</option><option value="name">Video name A–Z</option><option value="saved">Most space saved (replacements)</option></select></div></div>
<div class="control-grid"><div><label for="result-batch">Folder / batch</label><select id="result-batch"><option value="">All folders and batches</option></select></div><div><label for="show-archived"><input id="show-archived" type="checkbox"> Show archived results</label></div></div>
<div class="control-actions"><button id="archive-results" type="button">Clear finished results</button><button id="undo-archive" type="button" disabled>Undo clear</button></div><p class="control-note">Clear hides finished results only. It does not erase processing history, change the queue, or delete files.</p><p id="history-feedback" role="status" aria-live="polite"></p>
<div id="user-results"></div><button id="show-results" type="button" hidden>Show more results</button>
</div></section>
<details class="panel help"><summary>How decisions are made</summary><div class="panel-body"><p><strong>Create smaller copies</strong> tests short sections using supported encoders. Only candidates meeting quality and size checks proceed to full conversion and validation.</p><p><strong>Original kept</strong> means the tested options did not qualify, or you chose not to convert. A skipped video is not an error.</p><p><strong>Needs attention</strong> means processing stopped or the input is unsupported. Open its details for the reason. No source file is deleted.</p><p>Advanced settings are optional. Automatic mode compares playback-verified formats available on your hardware. Testing covers sampled visual quality and full-file preservation/decode checks, not a perceptual guarantee for every frame.</p></div></details>
<footer>MuxMender <span id="app-version">'''+VERSION+'''</span> · Replacement is opt-in · History and preferences are stored on the /output mount.</footer></main>
'''+HISTORY_SCRIPT+RESULTS_SCRIPT+SCRIPT+'''</body></html>'''
HTML=HTML.replace('No source file is deleted.','Replacement failures may leave a recovery backup; inspect details before retrying.')
HTML=HTML.replace('<div class="control-grid"><div><label for="result-search">',
                  '<details id="result-tools" open><summary>Search, filter and sort results</summary><div class="control-grid"><div><label for="result-search">')
HTML=HTML.replace('<div class="control-actions"><button id="archive-results"',
                  '</details><div class="control-actions"><button id="archive-results"')
