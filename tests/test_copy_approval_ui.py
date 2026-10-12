import json
import shutil
import subprocess
import unittest
from ui.app import HTML
from ui.workspace_history import SCRIPT
from ui.controls import SCRIPT as CONTROLS


@unittest.skipUnless(shutil.which('node'),'Node required for UI behavior checks')
class CopyApprovalUITests(unittest.TestCase):
    def run_js(self, source, harness):
        result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps(source),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_approval_dialog_requires_confirmation_and_can_close(self):
        source=SCRIPT[SCRIPT.index('const copyApprovalBusy='):SCRIPT.index('function makeResultCard(')]
        self.run_js(source,r'''
const assert=require('node:assert/strict'),vm=require('vm');
class Element{
 constructor(tag,text){this.tag=tag;this.textContent=text;this.children=[];this.events={};this.attrs={};this.isConnected=true}
 append(...nodes){this.children.push(...nodes)}
 setAttribute(k,v){this.attrs[k]=v}
 addEventListener(k,v){this.events[k]=v}
 showModal(){this.open=true}
 close(){this.open=false;this.events.close?.()}
 remove(){this.isConnected=false}
 focus(){this.focused=true}
}
let calls=[],refreshes=0,failPreview=false;
const body=new Element('body'),feedback=new Element('p');
const context=vm.createContext({userNode:(...args)=>new Element(...args),resultName:j=>j.source,
 fileSizeText:v=>String(v),document:{body},userEl:()=>feedback,refreshControls:()=>refreshes++,
 historyCall:async(action,data)=>{calls.push({action,data});if(failPreview)throw Error('missing copy');return {confirmation_id:'token',source_bytes:200,copy_bytes:100,message:'Permanent replacement after verification',target:'/media/example.mkv'}}});
vm.runInContext(JSON.parse(require('fs').readFileSync(0,'utf8')),context);
const job={id:'fixture',source:'example.mkv',state:'awaiting-playback',settings:{mode:'encode'}};
assert.equal(context.eligibleCopy(job),true);
for(const change of [{state:'failed'},{publication_authorized:false},{settings:{mode:'test'}}])assert.equal(context.eligibleCopy({...job,...change}),false);
function all(n){return [n,...n.children.flatMap(all)]}
(async()=>{
 let trigger=new Element('button');await context.approveExistingCopy(job,trigger);
 let dialog=body.children.at(-1);assert.equal(dialog.open,true);assert.equal(calls.length,1);
 assert.equal(dialog.attrs['aria-labelledby'],'copy-approval-title');
 all(dialog).find(n=>n.textContent==='Keep original').events.click();
 assert.equal(dialog.open,false);assert.equal(trigger.disabled,false);assert.equal(calls.length,1);
 await context.approveExistingCopy(job,trigger);dialog=body.children.at(-1);
 await all(dialog).find(n=>n.textContent==='Replace original with this copy').events.click();
 assert.equal(calls.at(-1).action,'approve-copy-confirm');assert.equal(calls.at(-1).data.confirm,true);
 assert.equal(calls.at(-1).data.confirmation_id,'token');assert.equal(refreshes,1);assert.equal(dialog.open,false);
 failPreview=true;await context.approveExistingCopy(job,trigger);assert.equal(trigger.disabled,false);assert.match(feedback.textContent,/missing copy/);
})().catch(e=>{console.error(e);process.exitCode=1});
''')

    def test_resource_apply_feedback_busy_and_failure_recovery(self):
        source=CONTROLS[CONTROLS.index('let resourceProfileBusy='):CONTROLS.index('let gpuSharingBusy=')]
        self.run_js(source,r'''
const assert=require('node:assert/strict'),vm=require('vm');
class Element{constructor(){this.attrs={};this.events={}}setAttribute(k,v){this.attrs[k]=v}removeAttribute(k){delete this.attrs[k]}addEventListener(k,v){this.events[k]=v}}
const button=new Element(),select=new Element(),feedback=new Element();select.value='faster';select.selectedIndex=0;select.options=[{text:'Faster — up to four files'}];
const nodes={'save-resource-profile':button,'resource-profile':select,'resource-profile-feedback':feedback};let reject=false,calls=0,release;
const context=vm.createContext({controlElement:id=>nodes[id],lastQueueControl:{resource_profile:'shared'},controlMessage:()=>{},refreshControls:()=>{},
 controlCall:async()=>{calls++;await new Promise(r=>release=r);if(reject)throw Error('timeout');return {profile:'faster',message:'saved'}}});
vm.runInContext(JSON.parse(require('fs').readFileSync(0,'utf8')),context);
(async()=>{
 let pending=context.applyResourceProfile();assert.equal(button.textContent,'Applying…');assert.equal(button.disabled,true);assert.equal(select.disabled,true);
 await context.applyResourceProfile();assert.equal(calls,1);release();await pending;
 assert.equal(button.disabled,false);assert.equal(select.disabled,false);assert.equal(button.attrs['aria-busy'],undefined);assert.match(feedback.textContent,/Saved: Faster/);
 assert.equal(context.lastQueueControl.resource_profile,'faster');
 reject=true;pending=context.applyResourceProfile();release();await pending;
 assert.equal(button.disabled,false);assert.equal(button.textContent,'Apply resource profile');assert.match(feedback.textContent,/Could not confirm.*timeout/);
})().catch(e=>{console.error(e);process.exitCode=1});
''')

    def test_shipped_scripts_parse_and_feedback_is_near_button(self):
        import re
        scripts=re.findall(r'<script[^>]*>(.*?)</script>',HTML,re.S)
        self.run_js(scripts,r'''
const vm=require('vm');for(const source of JSON.parse(require('fs').readFileSync(0,'utf8')))new vm.Script(source);
''')
        button=HTML.index('id="save-resource-profile"');feedback=HTML.index('id="resource-profile-feedback"')
        self.assertLess(feedback-button,400)
        self.assertIn('signal:AbortSignal.timeout(15000)',CONTROLS)


if __name__=='__main__':unittest.main()
