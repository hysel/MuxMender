import json
import shutil
import subprocess
import unittest
from ui.app import HTML
from ui.workspace import SCRIPT


class RemoveQueuedUITests(unittest.TestCase):
    def test_accessible_compact_waiting_list(self):
        self.assertEqual(HTML.count('id="waiting-queue"'),1)
        self.assertIn('id="waiting-queue-feedback" role="status" aria-live="polite"',HTML)
        self.assertIn('min-height:44px;flex-shrink:0',HTML)

    @unittest.skipUnless(shutil.which('node'),'Node needed for UI behavior')
    def test_render_click_stale_and_focus(self):
        source=(SCRIPT[SCRIPT.index('function sourceBytes('):SCRIPT.index('function queueSizeTotals(')]+
                SCRIPT[SCRIPT.index('const queuedRemovals='):SCRIPT.index('function receiveControls(')])
        harness=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const document={activeElement:null};
class Node {
 constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.dataset={};this.attrs={};this.listeners={}}
 append(...items){this.children.push(...items)}
 replaceChildren(){this.children=[]}
 contains(item){return this===item||this.children.some(n=>n.contains(item))}
 querySelectorAll(tag){return this.children.flatMap(n=>[...(n.tag===tag?[n]:[]),...n.querySelectorAll(tag)])}
 setAttribute(k,v){this.attrs[k]=v}
 addEventListener(k,v){this.listeners[k]=v}
 focus(){document.activeElement=this}
}
const nodes=new Map();function userEl(id){if(!nodes.has(id))nodes.set(id,new Node('div'));return nodes.get(id)}
let calls=[],refreshes=0;
const ctx=vm.createContext({document,userEl,userNode:(t,x)=>new Node(t,x),resultName:j=>j.source,
 controlReady:true,queueStatusUnavailable:false,
 controlCall:async(action,data)=>{calls.push([action,data]);return {message:'Removed'}},refreshControls:()=>refreshes++});
vm.runInContext(JSON.parse(require('fs').readFileSync(0,'utf8')),ctx);
(async()=>{
const pending={id:'one',state:'pending',source:'<unsafe>.mkv'};
const body={jobs:[pending,{id:'two',state:'running',source:'Running.mkv'}]};
ctx.renderWaitingQueue(body);const list=userEl('waiting-queue-items');
assert.equal(list.children.length,1);assert.equal(list.children[0].children[0].textContent,'<unsafe>.mkv');
assert.equal(list.children[0].children[0].children[0].textContent,'Source size unavailable');
let button=list.querySelectorAll('button')[0];assert.equal(button.disabled,false);
assert.equal(button.attrs['aria-label'],'Remove <unsafe>.mkv from queue');
button.focus();ctx.renderWaitingQueue(body,false);button=list.querySelectorAll('button')[0];
assert.equal(button.disabled,true);assert.equal(document.activeElement,button);
await button.listeners.click();assert.equal(calls.length,0);
ctx.renderWaitingQueue(body);button=list.querySelectorAll('button')[0];button.focus();
await button.listeners.click();assert.equal(calls.length,1);assert.equal(calls[0][0],'remove-queued');assert.equal(calls[0][1].id,'one');
assert.equal(refreshes,1);assert.equal(userEl('waiting-queue-feedback').textContent,'Removed');
ctx.renderWaitingQueue({jobs:[]});assert.equal(userEl('waiting-queue').hidden,true);
assert.equal(document.activeElement,list);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',harness],input=json.dumps(source),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
