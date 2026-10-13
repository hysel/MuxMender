import json
import shutil
import subprocess
import unittest
from ui.app import HTML
from ui.controls import SCRIPT


class GpuSharingAutosaveTests(unittest.TestCase):
    def test_accessible_toggle_replaces_apply_button(self):
        self.assertNotIn('id="save-gpu-yield"', HTML)
        self.assertIn('id="gpu-yield-feedback" role="status" aria-live="polite"', HTML)
        self.assertIn('aria-describedby="gpu-yield-help gpu-yield-feedback" disabled', HTML)
        self.assertIn("['resource-profile','gpu-yield','cpu-allocation'].includes(action)", SCRIPT)

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_save_failure_poll_races_and_external_changes(self):
        source=SCRIPT[SCRIPT.index('let gpuSharingBusy='):SCRIPT.index('let queueClearToken=')]
        harness=r'''
const assert=require('node:assert/strict'),vm=require('vm');
const input={checked:false,disabled:true,attrs:{},events:{},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},addEventListener(k,v){this.events[k]=v}};
const feedback={},status={},nodes={'gpu-yield-enabled':input,'gpu-yield-feedback':feedback,'gpu-yield-status':status};
let calls=[],release,reject=false,refreshes=0;
const context=vm.createContext({controlElement:id=>nodes[id],queueActionVersion:0,lastQueueControl:{ready:true},refreshControls:()=>refreshes++,
 controlCall:async(action,body)=>{calls.push({action,body});await new Promise(r=>release=r);if(reject)throw Error('timeout');return {message:'saved'}}});
vm.runInContext(JSON.parse(require('fs').readFileSync(0,'utf8')),context);
const state=enabled=>({ready:true,gpu_yield:{enabled,reason:'No competing GPU activity'}});
(async()=>{
 context.renderGpuSharing(state(false));assert.equal(input.disabled,false);assert.equal(input.checked,false);
 input.checked=true;let pending=input.events.change();assert.equal(input.disabled,true);assert.equal(feedback.textContent,'Saving…');assert.equal(input.attrs['aria-busy'],'true');
 context.renderGpuSharing(state(false));assert.equal(input.checked,true);assert.equal(feedback.textContent,'Saving…');
 await context.saveGpuSharing();assert.equal(calls.length,1);release();await pending;
 assert.equal(input.checked,true);assert.equal(input.disabled,false);assert.match(feedback.textContent,/Saved: On/);assert.equal(context.queueActionVersion,2);assert.equal(input.attrs['aria-busy'],undefined);
 reject=true;input.checked=false;pending=input.events.change();release();await pending;
 assert.equal(input.checked,true);assert.equal(input.disabled,false);assert.match(feedback.textContent,/timeout/);assert.equal(refreshes,2);
 // A timed-out request may have committed: reconcile with a fresh server snapshot.
 context.renderGpuSharing(state(false));assert.equal(input.checked,false);assert.match(feedback.textContent,/Saved: Off/);
 context.renderGpuSharing({...state(true),snapshot_stale:true});assert.equal(input.checked,false);
 context.renderGpuSharing({...state(false),ready:false});assert.equal(input.disabled,true);
 assert.equal(calls[0].action,'gpu-yield');assert.equal(calls[0].body.enabled,true);assert.equal(calls[1].body.enabled,false);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps(source),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
