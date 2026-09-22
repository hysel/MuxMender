"""Structural/contrast checks, not a substitute for assistive-technology review."""
from html.parser import HTMLParser
import re
import unittest
import shutil
import subprocess
from ui.app import HTML
from ui.workspace import STYLE


class WorkspaceAccessibilityTests(unittest.TestCase):
    def test_resource_labels_distinguish_host_and_container_cpu(self):
        from ui.controls import SCRIPT
        self.assertIn("'Host CPU '",SCRIPT)
        self.assertIn("' · App CPU allocation '",SCRIPT)
        self.assertIn('Number.isFinite(metrics.container_cpu_percent)',SCRIPT)

    def test_result_tools_disclosure_keeps_results_visible(self):
        start=HTML.index('<details id="result-tools" open>')
        end=HTML.index('</details>',start)
        for field in ('result-search','result-filter','result-sort','result-batch','show-archived'):
            self.assertIn('id="'+field+'"',HTML[start:end])
        self.assertLess(end,HTML.index('id="user-results"'))
        self.assertIn('<summary>Search, filter and sort results</summary>',HTML)

    def test_setup_disclosure_keeps_results_outside(self):
        self.assertLess(HTML.index('class="panel savings-hero"'),HTML.index('id="live-resources"'))
        self.assertLess(HTML.index('id="live-resources"'),HTML.index('id="activity"'))
        self.assertIn('<details class="panel" id="workflow" open>',HTML)
        self.assertIn('<summary class="panel-head" id="setup-toggle">',HTML)
        self.assertLess(HTML.index('</details>',HTML.index('id="setup-submission"')),
                        HTML.index('id="results"'))
        self.assertIn('Open to set up more',HTML)

    def test_savings_and_resource_readings_never_inside_disclosure(self):
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__();self.depth=0;self.locations={}
            def handle_starttag(self,tag,attrs):
                if tag=='details':self.depth+=1
                identity=dict(attrs).get('id')
                if identity in ('lifetime-saved','resource-status','resource-profile'):
                    self.locations[identity]=self.depth
            def handle_endtag(self,tag):
                if tag=='details':self.depth-=1
        parser=Parser();parser.feed(HTML)
        self.assertEqual(parser.locations['lifetime-saved'],0)
        self.assertEqual(parser.locations['resource-status'],0)
        self.assertGreater(parser.locations['resource-profile'],0)

    @unittest.skipUnless(shutil.which('node'),'Node required for interaction test')
    def test_success_collapses_only_nonempty_submission_and_moves_focus(self):
        from ui.controls import SCRIPT
        function=SCRIPT[SCRIPT.index('function collapseSubmittedSetup('):SCRIPT.index('document.querySelectorAll(\'a[href="#workflow"]\')')]
        javascript='''
const elements={workflow:{tagName:'DETAILS',open:true,scrollIntoView(){this.scrolled=true}},
 'setup-submission':{textContent:''},'setup-toggle':{focus(){this.focused=true}}};
const controlElement=id=>elements[id];
FUNCTION
collapseSubmittedSetup({queued:0});if(!elements.workflow.open)throw Error('Empty submission collapsed');
collapseSubmittedSetup({queued:3});if(elements.workflow.open)throw Error('Success not collapsed');
if(!elements['setup-toggle'].focused)throw Error('Focus left inside hidden form');
if(!elements['setup-submission'].textContent.includes('3'))throw Error('Missing success summary');
elements.workflow.open=true;if(!elements.workflow.open)throw Error('Cannot reopen');
'''.replace('FUNCTION',function)
        subprocess.run(['node','-e',javascript],check=True,capture_output=True,text=True)

    def test_unique_ids_and_explicit_form_labels(self):
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids=[]; self.labels=[]; self.fields=[]
            def handle_starttag(self, tag, attrs):
                attrs=dict(attrs)
                if 'id' in attrs:self.ids.append(attrs['id'])
                if tag=='label':self.labels.append(attrs.get('for'))
                if tag in ('input','select') and attrs.get('type')!='hidden':self.fields.append(attrs.get('id'))
        parser=Parser();parser.feed(HTML)
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        self.assertTrue(set(parser.fields)<=set(parser.labels))
        self.assertTrue(set(parser.labels)<=set(parser.ids))
        self.assertIn('<html lang="en">',HTML)
        self.assertIn('aria-live="polite"',HTML)
        self.assertEqual(HTML.count('<option value="replaced">'),1)
        self.assertIn('label for="result-sort"',HTML)

    def test_both_theme_text_and_control_contrast(self):
        def luminance(color):
            values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(a*b for a,b in zip(values,(.2126,.7152,.0722)))
        def ratio(a,b):
            a,b=sorted((luminance(a),luminance(b)))
            return (b+.05)/(a+.05)
        for block in re.findall(r':root(?:\[data-theme=dark\])?\{([^}]+)',STYLE)[:2]:
            colors=dict(re.findall(r'--([\w-]+):(#[0-9a-f]{6})',block))
            for foreground in ('text','muted','danger'):
                for background in ('bg','panel','soft'):
                    self.assertGreaterEqual(ratio(colors[foreground],colors[background]),4.5,(foreground,background))
            self.assertGreaterEqual(ratio(colors['accent-text'],colors['accent']),4.5)
            for foreground in ('border','focus'):
                self.assertGreaterEqual(ratio(colors[foreground],colors['panel']),3)
