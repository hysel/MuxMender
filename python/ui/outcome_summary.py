"""Latest per-video outcomes, distinct from lifetime savings and attempt counts."""
PANEL = '''<section class="panel" aria-labelledby="outcome-title"><div class="panel-head"><h2 id="outcome-title">Video outcomes</h2></div><div class="panel-body">
<p class="control-note">Latest result per video across saved history, including archived results. Retries are not counted twice. These totals are independent of the Results filters.</p>
<dl class="outcome-grid">
<div><dt>Replaced</dt><dd id="outcome-replaced">—</dd></div>
<div><dt>Converted copies</dt><dd id="outcome-copies">—</dd></div>
<div><dt>No worthwhile conversion</dt><dd id="outcome-benefit">—</dd></div>
<div><dt>Errors / interrupted</dt><dd id="outcome-errors">—</dd></div>
<div><dt>Unsupported / needs attention</dt><dd id="outcome-attention">—</dd></div>
<div><dt>Other kept / inspected / tested</dt><dd id="outcome-other">—</dd></div>
<div><dt>Queued / running</dt><dd id="outcome-active">—</dd></div>
</dl><p class="control-note">No worthwhile conversion means the tested options did not meet size or quality requirements—not a processing error. Converted copies still occupy space alongside originals.</p>
<p id="outcome-total" class="control-note">Waiting for saved history…</p></div></section>'''

SCRIPT = r'''<script>
function outcomeCategory(j){
 const state=j.state,reason=String(j.reason||''),code=j.decision_code;
 if(['pending','running'].includes(state))return 'active';
 if(state==='replaced')return 'replaced';
 if(['verified','awaiting-playback','playback-approved'].includes(state))return 'copies';
 if(['failed','interrupted'].includes(state))return 'errors';
 if(state==='skipped'){
  if(/unsupported|not supported|unavailable|needs attention|recovery|conflict/i.test(reason))return 'attention';
  if(['already_efficient_for_settings','full_output_insufficient_savings'].includes(code)||/no worthwhile savings|full output did not (?:save enough space|meet savings)|no eligible.*(?:size|smaller)|quality.*(?:not met|below|threshold)|quality_pass/i.test(reason))return 'benefit';
  return 'other';
 }
 if(['kept-original','analyzed','tested','completed'].includes(state))return 'other';
 return 'attention';
}
function videoOutcomeCounts(rows){
 const counts={replaced:0,copies:0,benefit:0,errors:0,attention:0,other:0,active:0};
 for(const group of groupedAttempts(rows.filter(j=>!j.superseded_by)))counts[outcomeCategory(group.latest)]++;
 return counts;
}
function renderOutcomeSummary(rows){
 const counts=videoOutcomeCounts(rows);
 for(const [key,value] of Object.entries(counts)){const el=userEl('outcome-'+key);if(el)el.textContent=String(value)}
 const total=userEl('outcome-total');if(total)total.textContent=Object.values(counts).reduce((a,b)=>a+b,0)+' videos in saved history. Counts show the latest attempt, not all past failures.';
}
</script>'''
