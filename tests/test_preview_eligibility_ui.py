import json
import shutil
import subprocess
import unittest
from ui.controls import SCRIPT


class PreviewEligibilityTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required for UI behavior test')
    def test_history_exclusions_are_actionable_without_bypassing_active_jobs(self):
        source=SCRIPT[SCRIPT.index('function previewEligibility('):SCRIPT.index('function invalidatePreview(')]
        harness=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const context=vm.createContext({});vm.runInContext(JSON.parse(require('fs').readFileSync(0,'utf8')),context);
const check=(files,mode)=>context.previewEligibility({files,settings:{history_mode:mode}});
let r=check([{history_reason:'Already recorded',history_state:'awaiting-playback'}],'retry');
assert.equal(r.eligible,0);assert.match(r.message,/Nothing can be added/);assert.match(r.message,/Recheck everything/);
r=check([{history_reason:'Retry only',history_state:'not-selected'}],'retry');assert.match(r.message,/without an eligible earlier result/);
r=check([{history_reason:'Active',history_state:'running'}],'all');assert.equal(r.eligible,0);assert.match(r.message,/already queued or running/);assert.doesNotMatch(r.message,/Recheck everything/);
r=check([{}, {history_reason:'Already recorded',history_state:'replaced'}],'reuse');assert.equal(r.eligible,1);assert.match(r.message,/1 video\(s\) can be queued/);
r=check([{}],'all');assert.equal(r.eligible,1);assert.match(r.message,/Review the file list/);
'''
        result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps(source),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_empty_preview_cannot_be_confirmed(self):
        self.assertIn('if(!eligibility.eligible){previewId=null;previewReplaces=false;',SCRIPT)
        self.assertIn("disabled=!eligibility.eligible||previewReplaces",SCRIPT)
        self.assertIn("controlMessage(eligibility.message)",SCRIPT)
