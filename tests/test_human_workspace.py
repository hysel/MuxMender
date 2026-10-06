import json
from html.parser import HTMLParser
import re
import shutil
import subprocess
import unittest
from ui.app import HTML
from ui.human_workspace import STYLE,SCRIPT


class HumanWorkspaceTests(unittest.TestCase):
    def test_savings_explanation_uses_plain_language(self):
        self.assertIn('Only originals replaced with smaller files. Test copies don’t count.',HTML)
        self.assertNotIn('Room for more.',HTML)
        self.assertNotIn('Real library savings from verified replacements',HTML)

    def test_result_filters_and_display_controls_do_not_imply_queue_completion(self):
        self.assertIn('data-result-shortcut="all" aria-pressed="true">Completed results</button>',HTML)
        self.assertIn('data-result-shortcut="active" aria-pressed="false">Queued &amp; running</button>',HTML)
        self.assertIn('aria-describedby="result-view-description"',HTML)
        self.assertIn('This filter does not indicate whether the queue has finished.',HTML)
        self.assertIn('Ongoing retries of completed attempts are included.',HTML)
        self.assertIn('>Freeze display only</button>',HTML)
        self.assertIn('>Pause new starts</button>',HTML)
        self.assertIn('Pause new starts lets active jobs finish.',HTML)
        self.assertNotIn('>Finished</button>',HTML)

    @unittest.skipUnless(shutil.which('node'),'Node required for active retry presentation test')
    def test_active_retry_does_not_present_previous_failure_as_current(self):
        from ui.workspace import SCRIPT as workspace
        from ui.workspace_history import SCRIPT as history
        source=workspace[workspace.index('function userReason('):workspace.index('function resultGroup(')]
        source+=history[history.index('function outcomeLabel('):history.index('function historyKey(')]
        harness=r'''
const assert=require('node:assert/strict'),vm=require('vm'),source=JSON.parse(require('fs').readFileSync(0,'utf8'));
const context=vm.createContext({});vm.runInContext(source,context);
for(const state of ['pending','running'])for(const reason of ['Unsupported input: historical limitation','source audio preflight failed']){
 const job={state,reason,outcome_category:'error',decision_code:'full_output_insufficient_savings'};
 assert.equal(context.outcomeLabel(job),state==='pending'?'Queued':'Running');
 assert.match(context.userReason(job),/Current work/);
 assert.doesNotMatch(context.userReason(job),/could not be decoded|Unsupported input/);
}
assert.equal(context.outcomeLabel({state:'failed',outcome_category:'error'}),'Processing error');
'''
        result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps(source),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_apply_buttons_are_grouped_with_their_controls(self):
        class Parser(HTMLParser):
            def __init__(self):super().__init__();self.stack=[];self.rows={};self.void={'input','meta','link','br'}
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if tag not in self.void:self.stack.append((tag,attrs))
                identity=attrs.get('id')
                if identity in ('resource-profile','save-resource-profile','gpu-yield-enabled','save-gpu-yield'):
                    self.rows[identity]=next((id(a) for _,a in reversed(self.stack) if a.get('class')=='settings-row'),None)
            def handle_endtag(self,tag):
                for i in range(len(self.stack)-1,-1,-1):
                    if self.stack[i][0]==tag:self.stack=self.stack[:i];break
        parser=Parser();parser.feed(HTML)
        for field,button in [('resource-profile','save-resource-profile'),('gpu-yield-enabled','save-gpu-yield')]:
            self.assertIsNotNone(parser.rows[field]);self.assertEqual(parser.rows[field],parser.rows[button])
        self.assertEqual(HTML.count('id="save-gpu-yield"'),1)

    def test_resume_requires_pending_work(self):
        self.assertIn("controlElement('resume-selected').disabled=!body.ready||!body.paused||!(body.counts.pending>0)",HTML)
        self.assertIn('No waiting jobs to resume',HTML)

    @unittest.skipUnless(shutil.which('node'),'Node required for queue-control behavior test')
    def test_resume_button_state_matrix(self):
        from ui.controls import SCRIPT
        start=SCRIPT.index(' controlReady=body.ready;')
        source=SCRIPT[start:SCRIPT.index('\n',SCRIPT.index("controlElement('resume-selected').title=",start))]
        harness=r'''
const assert=require('node:assert/strict'),vm=require('vm');
const source=JSON.parse(require('fs').readFileSync(0,'utf8'));
for(const ready of [false,true])for(const paused of [false,true])for(const pending of [0,1,4]){
 const elements={};const context=vm.createContext({body:{ready,paused,counts:{pending}},workspaceReady:true,
   controlElement:id=>(elements[id]??={})});
 vm.runInContext(source,context);
 assert.equal(elements['resume-selected'].disabled,!(ready&&paused&&pending>0));
 if(!pending)assert.equal(elements['resume-selected'].title,'No waiting jobs to resume');
}
'''
        result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps(source),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_controls_remain_unique_and_resource_readings_have_labels(self):
        class Parser(HTMLParser):
            def __init__(self):super().__init__();self.ids=[];self.fields={}
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if attrs.get('id'):self.ids.append(attrs['id'])
                if tag=='option':self.fields[attrs.get('value')]=True
        parser=Parser();parser.feed(HTML)
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        for identity in ('resource-cpu','resource-gpu','resource-ram','queue-running','queue-waiting',
                         'queue-attention','queue-clear-close','confirm-replacement','report-download'):
            self.assertIn(identity,parser.ids)
        for mode in ('analyze','test','encode','replace','keep'):self.assertIn(mode,parser.fields)
        self.assertIn('Current check:',HTML)
        self.assertIn('Fine-tune settings (optional)',HTML)
        self.assertNotIn('Design preview · illustrative data',HTML)

    def test_actual_light_and_dark_palette_contrast(self):
        def luminance(color):
            rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            return sum((x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4)*w for x,w in zip(rgb,(.2126,.7152,.0722)))
        def ratio(a,b):
            low,high=sorted((luminance(a),luminance(b)));return (high+.05)/(low+.05)
        for block in re.findall(r':root(?:\[data-theme=dark\])?\{([^}]+)',STYLE)[:2]:
            colors=dict(re.findall(r'--([\w-]+):(#[0-9a-f]{6})',block))
            for ink in ('text','muted','danger'):
                for paper in ('bg','panel','soft'):
                    self.assertGreaterEqual(ratio(colors[ink],colors[paper]),4.5,(ink,paper))
            self.assertGreaterEqual(ratio(colors['accent-text'],colors['accent']),4.5)
            for ink in ('border','focus'):
                self.assertGreaterEqual(ratio(colors[ink],colors['panel']),3)

    @unittest.skipUnless(shutil.which('node'),'Node required for summary presentation test')
    def test_summary_distinguishes_missing_metrics_and_zero_and_deduplicates_attempts(self):
        function=SCRIPT[SCRIPT.index('function renderWorkspaceSummary('):SCRIPT.index('(function(){')]
        harness=r'''
const assert=require('node:assert/strict'),vm=require('vm'),source=JSON.parse(require('fs').readFileSync(0,'utf8'));
const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'all'});return nodes.get(id)};
const context=vm.createContext({document:{getElementById:node,querySelectorAll:()=>[]},
 groupedAttempts:rows=>rows.length?[{latest:rows[rows.length-1]}]:[],outcomeCategory:j=>j.state==='failed'?'errors':'replaced'});
vm.runInContext(source,context);
context.renderWorkspaceSummary({counts:{running:2,pending:3},jobs:[{state:'failed'},{state:'replaced'}],resources:{telemetry:{cpu_percent:0,gpu_encode_percent:44,available_gib:20.3}}});
assert.equal(node('queue-attention').textContent,0,'Old failure must not remain attention after success');
assert.equal(node('resource-cpu').textContent,'0%');assert.equal(node('resource-gpu').textContent,'44%');
assert.equal(node('queue-waiting').textContent,3);
assert.match(node('result-view-description').textContent,/Viewing: Completed results/);
assert.match(node('result-view-description').textContent,/Ongoing retries/);
node('result-filter').value='active';context.renderWorkspaceSummary({jobs:[]});
assert.match(node('result-view-description').textContent,/Viewing: Queued & running/);
assert.doesNotMatch(node('result-view-description').textContent,/Ongoing retries/);
context.renderWorkspaceSummary({jobs:[{state:'failed'}]});
assert.equal(node('resource-cpu').textContent,'Unavailable');assert.equal(node('resource-ram').textContent,'Unavailable');
assert.equal(node('queue-attention').textContent,1);
'''
        result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps(function),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
