import shutil
import subprocess
import unittest
from ui.app import HTML
from ui.outcome_summary import SCRIPT
from ui.workspace_history import SCRIPT as HISTORY

class OutcomeSummaryTests(unittest.TestCase):
    def test_structure_and_scope(self):
        self.assertLess(HTML.index('id="lifetime-saved"'),HTML.index('id="outcome-title"'))
        self.assertLess(HTML.index('id="outcome-title"'),HTML.index('id="workflow"'))
        self.assertIn('including archived results',HTML)
        self.assertIn('<dl class="outcome-grid">',HTML)
        for key in ('replaced','copies','benefit','errors','attention','other','active'):
            self.assertEqual(HTML.count('id="outcome-'+key+'"'),1)

    @unittest.skipUnless(shutil.which('node'),'Node required for outcome logic')
    def test_latest_outcomes_not_raw_attempt_totals(self):
        grouping=HISTORY[HISTORY.index('function historyKey'):HISTORY.index('function evidenceText')]
        js="const assert=require('assert');const outcomeTime=j=>j.finished||j.created||0;\n"+grouping+SCRIPT.removeprefix('<script>').removesuffix('</script>')+r'''
const j=(id,source,state,created,extra={})=>({id,source,state,created,...extra});
const rows=[j('1','a.mp4','failed',1),j('2','a.mp4','replaced',2,{published_path:'a.mkv'}),
 j('3','a.mkv','pending',3,{superseded_by:'2'}),
 j('4','b.mkv','skipped',1,{decision_code:'full_output_insufficient_savings'}),
 j('5','c.mkv','failed',1,{reason:'Full output did not save enough space'}),
 j('6','d.mkv','skipped',1,{reason:'Unsupported input: no encoder'}),
 j('7','e.mkv','kept-original',1),j('8','f.mkv','awaiting-playback',1),
 j('9','g.mkv','failed',1),j('10','g.mkv','running',2)];
assert.deepStrictEqual(videoOutcomeCounts(rows),{replaced:1,copies:1,benefit:1,errors:1,attention:1,other:1,active:1});
assert.equal(outcomeCategory({state:'skipped',reason:'No worthwhile savings found with current settings'}),'benefit');
assert.equal(outcomeCategory({state:'skipped',reason:'Destination conflict'}),'attention');
assert.equal(outcomeCategory({state:'interrupted'}),'errors');
assert.equal(outcomeCategory({state:'unknown'}),'attention');
assert.equal(Object.values(videoOutcomeCounts([])).reduce((a,b)=>a+b,0),0);
const nodes={};const userEl=id=>nodes[id]||(nodes[id]={});
renderOutcomeSummary(rows);assert.equal(nodes['outcome-errors'].textContent,'1');
assert.ok(nodes['outcome-total'].textContent.startsWith('7 videos'));
'''
        subprocess.run(['node','-e',js],check=True,capture_output=True,text=True)

if __name__=='__main__':unittest.main()
