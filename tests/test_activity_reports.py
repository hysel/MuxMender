import re
import shutil
import subprocess
from pathlib import Path
import unittest
from ui.app import HTML


class ActivityReportTests(unittest.TestCase):
    def test_accessible_report_controls(self):
        for value in ['href="#reports"','id="reports-title"','for="report-outcome"',
                      'for="report-scope"','for="report-search"','Download matching report (CSV)',
                      'aria-label="Video activity, newest first"','History and export','aria-pressed="false"','Connection unavailable']:
            self.assertIn(value,HTML)

    @unittest.skipUnless(shutil.which('node'),'Node required for report DOM checks')
    def test_report_outcomes_history_and_csv(self):
        harness=(Path(__file__).parent/'dashboard_ui_test.js').read_text(encoding='utf-8')
        scripts='\n'.join(re.findall(r'<script>(.*?)</script>',HTML,re.S))
        mock="globalThis.setTimeout=()=>0;globalThis.fetch=()=>new Promise(()=>{});globalThis.matchMedia=()=>({matches:false,addEventListener(){}});"
        checks=r'''
const records=[
 {id:'old',source:'/media/a.mkv',state:'failed',created:1,finished:2,reason:'Old failure'},
 {id:'new',source:'/media/a.mkv',state:'replaced',created:3,finished:4,saved_bytes:123},
 {id:'kept',source:'/media/b.mkv',state:'skipped',created:2,decision_code:'already_efficient_for_settings',reason:'Quality threshold not met'},
 {id:'err',source:'/media/c.mkv',state:'skipped',created:2,outcome_category:'error',reason:'Decoder failed'},
 {id:'copy',source:'/media/d.mkv',state:'verified',created:2,original_bytes:1000,output_bytes:500,saved_bytes:500},
 {id:'active',source:'/media/e.mkv',state:'running',created:2},
 {id:'manual',source:'/media/f.mkv',state:'kept-original',created:2},
 {id:'unsupported',source:'/media/g.mkv',state:'skipped',created:2,reason:'Unsupported input'}];
assert(sizeSummary({signature:[2e9,123]})==='Source: 2.00 GB','Queued source size from signature');
assert(sourceBytes({original_bytes:3e9,signature:[2e9]})===3e9,'Recorded original takes precedence');
assert(sourceBytes({original_bytes:-1,signature:[2e9]})===2e9,'Invalid size falls back');
assert(sizeSummary({signature:[2e9],output_bytes:1e9}).includes('Output: 1.00 GB · 50.0% smaller'),'Output size and reduction');
assert(sizeSummary({signature:[1e9],output_bytes:2e9}).includes('100.0% larger'),'Growth correctly labelled');
assert(sizeSummary({signature:[0],output_bytes:0})==='Source: 0 bytes → Output: 0 bytes','Zero avoids division');
assert(sizeSummary({})==='Source size unavailable','Unknown size explicit');
assert(sizeSummary({source_bytes:5e6})==='Source: 5.00 MB','Small file readable');
assert(collect(renderActiveCard({source:'/media/test.mkv',state:'running',signature:[2e9]})).some(n=>n.textContent==='Source: 2.00 GB'),'Active card includes source size');
assert(activityCsv([{source:'/media/test.mkv',state:'pending',signature:[2e9]}]).includes('"2000000000"'),'CSV includes queued source bytes');
assert(reportRows(records,'latest','all','').length===7,'Latest deduplicates retries');
assert(reportRows(records,'latest','converted','').length===2,'Converted groups replacements and copies');
assert(reportRows(records,'latest','problems','').length===2,'Attention groups errors and unsupported');
assert(reportRows(records,'latest','kept','').length===2,'Kept groups non-error outcomes');
assert(reportRows(records,'attempts','all','').length===8,'All attempts retain past failures');
assert(reportRows(records,'latest','errors','').length===1,'Error skip is an error, not no benefit');
assert(reportRows(records,'attempts','errors','').length===2,'Historical errors available');
for(const category of ['replaced','copies','benefit','attention','other','active'])assert(reportRows(records,'latest',category,'').length===1,'Category '+category);
assert(reportRows(records,'latest','all','/MEDIA/B').length===1,'Case insensitive path search');
assert(csvCell('=HYPERLINK("evil")').startsWith('"\''),'Formula injection escaped');
assert(csvCell('a,"b"\nc').includes('""b""'),'CSV quotes escaped');
assert(activityCsv([records[4]]).includes('"500","","copy"'),'Copy cannot claim reclaimed bytes');
assert(activityCsv([records[1]]).includes('"123","new"'),'Replacement receipt bytes included');
assert(reportDate({})==='Not recorded','No fabricated date');
assert(reportDate(records[1]).endsWith('Z'),'UTC zone explicit');
viewState={archived_ids:['new']};userEl('report-outcome').value='all';userEl('report-scope').value='latest';
renderActivityReports(records);
assert(reportMatched.length===7,'Archived results remain in report');
assert(userEl('report-rows').children.length===7,'Rendered rows');
assert(!collect(userEl('report-rows')).some(n=>n.tag==='table'),'No wide report table');
const card=userEl('report-rows').children[0],details=card.children.find(n=>n.tag==='details');details.open=true;
renderActivityReports([...records,{id:'next',source:'/media/next.mkv',state:'pending',created:10}]);
assert(userEl('report-rows').contains(card)&&details.open,'Polling keeps expanded details open');
assert(reportReason({state:'failed',reason:'Source audio preflight failed: quant_step_size larger than huff_lsbs'}).includes('source audio could not be decoded'),'Readable audio explanation');
assert(!userReason({state:'failed',reason:'Video decoder reported incomplete frame'}).includes('source audio'),'Do not mislabel video errors as source audio');
assert(userEl('report-freshness').textContent.includes('may be stale'),'Disconnected state visible');
console.log('Report checks passed');
'''
        result=subprocess.run(['node'],input=mock+harness+scripts+checks,text=True,encoding='utf-8',capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
