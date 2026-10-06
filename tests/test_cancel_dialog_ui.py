"""Execute actual cancellation-dialog handlers in a small DOM model."""
import json
import shutil
import subprocess
import unittest
from ui.controls import SCRIPT
from ui.app import HTML


class CancelDialogUITests(unittest.TestCase):
    def test_explicit_accessible_close_control(self):
        self.assertIn('id="queue-clear-close" type="button" aria-label="Close cancel jobs dialog"',HTML)
        self.assertIn('id="queue-clear-cancel" type="button" autofocus>Go back',HTML)

    @unittest.skipUnless(shutil.which('node'),'Node required for JavaScript handler checks')
    def test_empty_preview_and_all_dismissal_paths(self):
        source=SCRIPT[SCRIPT.index('let queueClearToken='):SCRIPT.index('let controlPollBusy=')]
        harness=r'''
const vm=require('vm'),source=JSON.parse(require('fs').readFileSync(0,'utf8'));
const elements=new Map(),calls=[];let response={count:2,running:1,confirmation_id:'token'},fail=false;
function element(id){if(!elements.has(id))elements.set(id,{disabled:false,open:false,handlers:{},
 addEventListener(name,fn){this.handlers[name]=fn},showModal(){this.open=true},
 close(){this.open=false;this.handlers.close?.()},focus(){this.focused=true},
 getBoundingClientRect(){return {left:10,right:200,top:10,bottom:200}}});return elements.get(id)}
function assert(ok,message){if(!ok)throw Error(message)}
const context=vm.createContext({controlElement:element,refreshControls(){element('clear-waiting-queue').disabled=false},
 async controlCall(action){calls.push(action);if(fail)throw Error('Request failed');return response}});
vm.runInContext(source,context);
(async()=>{
 const dialog=element('queue-clear-dialog'),open=()=>element('clear-waiting-queue').handlers.click();
 response={count:0,running:0,confirmation_id:'empty'};await open();
 assert(!dialog.open,'Empty queue must not open modal');
 assert(element('queue-clear-feedback').textContent.includes('No jobs to cancel'),'Empty queue feedback');
 response={count:2,running:1,confirmation_id:'token'};
 for(const id of ['queue-clear-close','queue-clear-cancel']){
  await open();assert(dialog.open,'Nonempty preview opens');element(id).handlers.click();
  assert(!dialog.open,'Close button dismisses');assert(element('clear-waiting-queue').focused,'Focus restored');
  assert(vm.runInContext('queueClearToken',context)===null,'Dismiss invalidates token');
 }
 await open();let prevented=false;dialog.handlers.cancel({preventDefault(){prevented=true}});
 assert(prevented&&!dialog.open,'Escape dismisses');
 await open();dialog.handlers.click({target:dialog,clientX:50,clientY:50});
 assert(dialog.open,'Dialog interior must not dismiss');
 dialog.handlers.click({target:dialog,clientX:0,clientY:0});assert(!dialog.open,'Backdrop dismisses');
 assert(calls.every(c=>c==='clear-queue-preview'),'Dismissal must never submit cancellation');
 await open();fail=true;await element('queue-clear-confirm').handlers.click();
 assert(dialog.open&&element('queue-clear-error').textContent==='Request failed','Failure remains actionable');
 element('queue-clear-close').handlers.click();assert(!dialog.open,'Failure dialog is dismissible');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps(source),
                              text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
