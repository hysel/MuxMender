from html.parser import HTMLParser
import re
import json
import shutil
import subprocess
import unittest

from ui.app import HTML
from ui.workbench import STYLE, CONSOLE_STYLE, TERMINAL_STYLE
from ui.workspace import SCRIPT


class WorkbenchTests(unittest.TestCase):
    def test_dense_current_work_preserves_progress_guidance(self):
        self.assertIn('@media(min-width:1000px)', TERMINAL_STYLE)
        self.assertIn('.active-job>details{grid-column:4;grid-row:1 / span 2', TERMINAL_STYLE)
        note='Progress shows the current check, not the whole video.'
        support=HTML[HTML.index('<details class="queue-support">'):]
        self.assertIn(note, support[:support.index('</details>')])
        self.assertEqual(HTML.count(note), 1)

    def test_bottom_guidance_is_compact_and_still_available(self):
        self.assertIn('<div class="workspace-footer"><details class="panel help">', HTML)
        note='Pause new starts lets active jobs finish.'
        support=HTML[HTML.index('<details class="queue-support">'):]
        self.assertIn(note, support[:support.index('</details>')])
        self.assertEqual(HTML.count(note), 1)

    def test_console_progress_is_compact_and_does_not_change_controls(self):
        self.assertIn('id="console-style"', HTML)
        self.assertIn('.job-progress-track{width:100%;max-width:360px', CONSOLE_STYLE)
        self.assertIn('max-width:280px', CONSOLE_STYLE)
        self.assertIn('forced-colors', CONSOLE_STYLE)
        self.assertNotIn('clip-path', CONSOLE_STYLE)  # Never clip control focus outlines.

    def test_compact_queue_rows_keep_expanded_details_and_mobile_readable(self):
        self.assertIn('grid-template-columns:minmax(0,1fr) minmax(0,360px)', CONSOLE_STYLE)
        self.assertIn('.active-job>details[open]{grid-column:1 / -1', CONSOLE_STYLE)
        self.assertIn('.active-job{display:block;padding:10px 14px}', CONSOLE_STYLE)
        self.assertIn('summary{min-height:44px', CONSOLE_STYLE)

    @unittest.skipUnless(shutil.which('node'), 'Node required for progress presentation tests')
    def test_progress_unknown_stale_complete_and_details(self):
        source=SCRIPT[SCRIPT.index('function stagePresentation('):SCRIPT.index('function mergedResults(')]
        harness=r'''
const assert=require('node:assert/strict'),vm=require('vm');
class Node{
 constructor(tag,text,cls){this.tag=tag;this.textContent=text;this.children=[];this.attrs={};this.style={};this.classes=new Set();this.classList={add:s=>this.classes.add(s)};this.events={}}
 append(...nodes){this.children.push(...nodes)}
 setAttribute(k,v){this.attrs[k]=v}
 addEventListener(k,v){this.events[k]=v}
}
const context=vm.createContext({userNode:(...args)=>new Node(...args),resultName:j=>j.source,
 sizeSummary:()=> 'Source: 4 GB',friendlyStage:s=>s,catalogConnected:true,globalThis:{liveUpdatesPaused:false}});
vm.runInContext(JSON.parse(require('fs').readFileSync(0,'utf8')),context);
function all(node){return [node,...node.children.flatMap(all)]}
const now=Date.now()/1000,base={id:'fixture',source:'Example video.mkv',updated:now,phase:'full-encode',workflow_stage:'encode',settings:{mode:'replace'},started:now-60};
for(const percent of [0,54,100,null,NaN,-1,101]){
 const card=context.renderActiveCard({...base,stage_percent:percent});
 const nodes=all(card),bar=nodes.find(n=>n.attrs.role==='progressbar'),detail=nodes.find(n=>n.tag==='details');
 const known=Number.isFinite(percent)&&percent>=0&&percent<=100;
 assert.equal(bar.attrs['aria-valuenow'],known?String(percent):undefined);
 assert.equal(bar.children[0].style.width,known?percent+'%':'100%');
 assert.equal(bar.classes.has('is-measuring'),!known);
 assert.equal(bar.classes.has('is-complete'),percent===100);
 assert.equal(detail.open,false);assert.ok(detail.children.some(n=>n.tag==='ol'));
 assert.ok(!card.children.some(n=>n.tag==='ol'),'Step list must be collapsed');
}
for(const change of [{updated:now-100},{telemetry_state:'stale'}]){
 const bar=all(context.renderActiveCard({...base,...change,stage_percent:54})).find(n=>n.attrs.role==='progressbar');
 assert.equal(bar.attrs['aria-valuenow'],undefined);assert.equal(bar.classes.has('is-stale'),true);
}
for(const flag of ['disconnected','paused']){
 context.catalogConnected=flag!=='disconnected';context.globalThis.liveUpdatesPaused=flag==='paused';
 const bar=all(context.renderActiveCard({...base,stage_percent:54})).find(n=>n.attrs.role==='progressbar');
 assert.equal(bar.attrs['aria-valuenow'],undefined);assert.ok(bar.classes.has('is-stale'));
}
context.catalogConnected=true;context.globalThis.liveUpdatesPaused=false;
const detail=all(context.renderActiveCard(base)).find(n=>n.tag==='details');detail.open=true;detail.events.toggle();
assert.equal(all(context.renderActiveCard(base)).find(n=>n.tag==='details').open,true,'Polling must not collapse expanded details');
'''
        result=subprocess.run([shutil.which('node'),'-e',harness],input=json.dumps(source),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_readings_remain_above_queue_and_outside_navigation_views(self):
        self.assertIn('<div class="workspace-status">', HTML)
        self.assertLess(HTML.index('id="lifetime-saved"'), HTML.index('id="resource-cpu"'))
        self.assertLess(HTML.index('id="resource-ram"'), HTML.index('id="queue-overview"'))
        self.assertIn('id="workbench-style"', HTML)
        self.assertNotIn('Design preview · sample data', HTML)

    def test_controls_keep_unique_ids(self):
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids = []
            def handle_starttag(self, tag, attrs):
                identity = dict(attrs).get('id')
                if identity: self.ids.append(identity)
        parser = Parser(); parser.feed(HTML)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        for identity in ('submit-job', 'queue-clear-close', 'confirm-replacement', 'output-preset', 'hdr-policy'):
            self.assertIn(identity, parser.ids)

    def test_workbench_theme_contrast(self):
        def luminance(color):
            values = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
            return sum((v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4)*w for v,w in zip(values,(.2126,.7152,.0722)))
        def ratio(a,b):
            low,high=sorted((luminance(a),luminance(b)))
            return (high+.05)/(low+.05)
        for block in re.findall(r':root(?:\[data-theme=dark\])?\{([^}]+)', STYLE + TERMINAL_STYLE):
            colors=dict(re.findall(r'--([\w-]+):(#[0-9a-f]{6})',block))
            for ink in ('text','muted','danger'):
                for paper in ('bg','panel','soft'):
                    self.assertGreaterEqual(ratio(colors[ink],colors[paper]),4.5,(ink,paper))
            self.assertGreaterEqual(ratio(colors['accent-text'],colors['accent']),4.5)
            for ink in ('border','focus'):
                self.assertGreaterEqual(ratio(colors[ink],colors['panel']),3)
            if 'signal' in colors:
                self.assertGreaterEqual(ratio(colors['signal'],colors['panel']),4.5)
        self.assertIn('prefers-reduced-motion', STYLE)
        self.assertIn('forced-colors', STYLE)


if __name__ == '__main__': unittest.main()
