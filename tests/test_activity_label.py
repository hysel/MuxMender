import re
import shutil
import subprocess
import unittest
from ui.workspace import SCRIPT


class ActivityLabelTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required for UI logic test')
    def test_inspection_is_not_mislabeled_as_encoding(self):
        functions='\n'.join(re.search(r'function '+name+r'\(value\)\{[^\n]+',SCRIPT).group()
                            for name in ('activityLabel','friendlyStage'))
        harness=functions+'''
const assert=require('node:assert/strict');
assert.match(friendlyStage('Inspect every source frame for HDR and DV metadata'),/^CPU inspection/);
assert.match(friendlyStage('Checking original HDR metadata'),/not encoding/);
assert.match(friendlyStage('Checking HDR frame timing: full'),/^CPU validation/);
assert.match(friendlyStage('Checking HDR frame timing: full · GPU reader'),/^GPU validation/);
assert.match(friendlyStage('Checking original HDR metadata · GPU reader'),/^GPU validation/);
assert.match(friendlyStage('Checking original HDR metadata · CPU reader'),/^CPU inspection/);
assert.match(friendlyStage('Checking HDR frames: final · GPU reader'),/^GPU validation/);
assert.equal(friendlyStage('hevc_nvenc full encode'),'GPU encoding · NVIDIA');
for(const lane of ['validation','gpu','publication'])assert.match(friendlyStage('Waiting for '+lane+' resources'),/^Waiting for resources/);
assert.equal(friendlyStage('hevc_nvenc-balanced-0-quality'),'Measuring visual quality');
assert.equal(activityLabel('full-encode'),'Encoding · creating a separate video copy');
assert.equal(activityLabel('unknown phase'),'');
'''
        subprocess.run(['node','-e',harness],check=True,capture_output=True,text=True)
