import re
import shutil
import subprocess
import unittest
from ui.workspace_history import SCRIPT


class RetryLabelTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required for UI logic test')
    def test_current_retry_is_separate_from_previous_outcome(self):
        function=re.search(r'function retryLabel\(group\)\{[^\n]+',SCRIPT).group()
        harness=function+'''
const assert=require('node:assert/strict');
const group=(state,n=2)=>({latest:{state},attempts:Array.from({length:n},()=>({state:'failed'}))});
assert.equal(retryLabel(group('running')),'Retry in progress');
assert.equal(retryLabel(group('pending')),'Retry queued');
assert.equal(retryLabel(group('running',1)),'');
for(const state of ['failed','replaced','skipped','interrupted'])assert.equal(retryLabel(group(state)),'');
'''
        subprocess.run(['node','-e',harness],check=True,capture_output=True,text=True)
        self.assertNotIn('previous outcome:',SCRIPT)
        self.assertIn("retryNote=userNode('p',null,'result-meta')",SCRIPT)
        self.assertIn('ref.retryNote.hidden=!ref.retryNote.textContent',SCRIPT)
        self.assertIn("'Previous attempts ('",SCRIPT)
        self.assertIn('outcomeLabel(a)',SCRIPT)
