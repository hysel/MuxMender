import json
import shutil
import subprocess
import unittest
from ui.app import HTML
from ui.workspace import SCRIPT


class QueueSizeTests(unittest.TestCase):
    def test_summary_and_individual_sizes_are_available(self):
        for identifier in ('queue-source-size','queue-running-size','queue-waiting-size'):
            self.assertEqual(HTML.count('id="'+identifier+'"'),1)
        self.assertIn('waiting-video-size',SCRIPT)
        self.assertIn('Sizes recorded when added',SCRIPT)
        self.assertIn('Last known queue',SCRIPT)

    @unittest.skipUnless(shutil.which('node'),'Node required for queue summary tests')
    def test_sizes_filter_history_and_handle_unknown_values(self):
        source=SCRIPT[SCRIPT.index('function sourceBytes('):SCRIPT.index('function sizeSummary(')]
        harness=r'''
const assert=require('node:assert/strict'),vm=require('vm');
const nodes=Object.fromEntries(['queue-source-size','queue-running-size','queue-waiting-size'].map(k=>[k,{textContent:''}]));
const context=vm.createContext({userEl:id=>nodes[id],queueState:{},queueStatusUnavailable:false,globalThis:{liveUpdatesPaused:false}});
vm.runInContext(JSON.parse(require('fs').readFileSync(0,'utf8')),context);
const rows=[{id:'a',state:'pending',signature:[2e9,1]}, {id:'b',state:'running',original_bytes:1e9},
 {id:'c',state:'pending',signature:[null,1]}, {id:'d',state:'pending',signature:[true,1]},
 {id:'e',state:'replaced',original_bytes:99e9}, {id:'f',state:'cancelled',original_bytes:99e9}];
const result=context.queueSizeTotals([...rows,rows[0]]);
assert.equal(result.total.count,4);assert.equal(result.total.bytes,3e9);assert.equal(result.total.unknown,2);
assert.equal(result.running.bytes,1e9);assert.equal(result.waiting.bytes,2e9);
context.queueState={jobs:rows,queue_snapshot_updated:Date.now()/1000};context.renderQueueSizes();
assert.match(nodes['queue-source-size'].textContent,/Queue: 4 videos/);
assert.match(nodes['queue-source-size'].textContent,/3.00 GB known/);
assert.equal(nodes['queue-running-size'].textContent,'1.00 GB');
context.queueStatusUnavailable=true;context.renderQueueSizes();assert.match(nodes['queue-source-size'].textContent,/Last known/);
context.queueStatusUnavailable=false;context.queueState.queue_snapshot_updated=1;context.renderQueueSizes();assert.match(nodes['queue-source-size'].textContent,/Last known/);
context.queueState={jobs:[],queue_snapshot_updated:Date.now()/1000};context.renderQueueSizes();assert.match(nodes['queue-source-size'].textContent,/Queue: 0 videos/);
assert.equal(nodes['queue-waiting-size'].textContent,'0 bytes');
'''
        result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps(source),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
