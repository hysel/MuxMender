import json
import shutil
import subprocess
import unittest
from ui.controls import SCRIPT
from ui.app import HTML


class QueueActionStatusTests(unittest.TestCase):
    def test_status_is_visible_and_accessible(self):
        self.assertIn('id="queue-action-status" class="control-note" role="status" aria-live="polite"', HTML)
        self.assertIn('actionVersion!==queueActionVersion', SCRIPT)

    @unittest.skipUnless(shutil.which('node'), 'Node required for UI state checks')
    def test_queue_states_and_connection_loss(self):
        source=SCRIPT[SCRIPT.index('let lastQueueControl='):SCRIPT.index('async function refreshControls(')]
        harness=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();function controlElement(id){if(!nodes.has(id))nodes.set(id,{textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v}});return nodes.get(id)}
const ctx=vm.createContext({controlElement});vm.runInContext(JSON.parse(require('fs').readFileSync(0,'utf8')),ctx);
const pause=controlElement('pause-selected'),resume=controlElement('resume-selected'),status=controlElement('queue-action-status');
const running={ready:true,paused:false,counts:{pending:16,running:2}};
ctx.renderQueueActions(null,true);assert.ok(pause.disabled&&resume.disabled);assert.match(status.textContent,/Connecting/);
ctx.renderQueueActions(running);assert.equal(pause.disabled,false);assert.equal(resume.disabled,true);assert.match(status.textContent,/Queue running/);
ctx.renderQueueActions(running,true);assert.equal(pause.disabled,false,'Safe pause request remains available using confirmed state');assert.equal(resume.disabled,true);assert.match(status.textContent,/status delayed/);
ctx.renderQueueActions({...running,paused:true});assert.equal(pause.disabled,true);assert.equal(resume.disabled,false);assert.match(status.textContent,/2 active job/);
ctx.renderQueueActions({...running,paused:true},true);assert.ok(pause.disabled&&resume.disabled);assert.match(resume.title,/Waiting for current/);
ctx.renderQueueActions({ready:true,paused:true,counts:{pending:0,running:0}});assert.ok(pause.disabled&&resume.disabled);assert.match(status.textContent,/No waiting jobs/);
ctx.renderQueueActions({ready:false,error:'Worker offline'});assert.ok(pause.disabled&&resume.disabled);assert.match(status.textContent,/Worker offline/);
vm.runInContext('queueActionBusy=true',ctx);ctx.renderQueueActions(running);assert.ok(pause.disabled&&resume.disabled);assert.match(status.textContent,/Updating/);
vm.runInContext("queueActionBusy=false;queueActionError='Queue action failed: offline'",ctx);ctx.renderQueueActions(running,true);assert.match(status.textContent,/Queue action failed/);
assert.equal(pause.attrs['aria-describedby'],'queue-action-status');assert.equal(resume.attrs['aria-describedby'],'queue-action-status');
'''
        result=subprocess.run(['node','-e',harness],input=json.dumps(source),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
