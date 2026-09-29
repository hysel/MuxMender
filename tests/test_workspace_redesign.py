import re
import shutil
import subprocess
import unittest
from ui.app import HTML
from ui.redesign import SCRIPT, STYLE


class RedesignTests(unittest.TestCase):
    def test_live_controls_preserved_and_views_are_distinct(self):
        for identity in ('lifetime-saved','resource-status','source-depth','operation',
                         'confirm-replacement','submit-job','gpu-yield-enabled',
                         'result-batch','report-download','archive-results'):
            self.assertEqual(HTML.count('id="'+identity+'"'),1,identity)
        self.assertIn('data-workspace-link="overview"',HTML)
        self.assertIn('data-workspace-link="add-videos"',HTML)
        self.assertIn('data-workspace-link="results"',HTML)
        self.assertIn('<details class="panel" id="reports"',HTML)
        self.assertNotIn('<details id="result-tools" open>',HTML)
        self.assertLess(HTML.index('id="results"'),HTML.index('id="reports"'))
        self.assertNotIn('Sample data',HTML)

    @unittest.skipUnless(shutil.which('node'), 'Node required for DOM-model navigation test')
    def test_navigation_back_links_and_preserved_selection(self):
        harness=r'''
const assert=require('node:assert/strict');
const nodes=new Map();function node(id){if(!nodes.has(id)){const classes=new Set();nodes.set(id,{id,dataset:{},hidden:false,open:false,value:'preserve me',attrs:{},classList:{add:v=>classes.add(v),toggle:(v,on)=>on?classes.add(v):classes.delete(v)},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},addEventListener(k,fn){this[k]=fn},focus(){},scrollIntoView(){}})}return nodes.get(id)}
const links=['overview','add-videos','results'].map(id=>{const n=node('nav-'+id);n.dataset.workspaceLink=id;return n});
global.document={body:node('body'),getElementById:node,querySelectorAll:()=>links};
const events={};global.window={addEventListener:(name,fn)=>events[name]=fn};let hash='';global.location={get hash(){return hash},set hash(v){hash=v.startsWith('#')?v:'#'+v;events.hashchange?.()}};
'''+SCRIPT.removeprefix('<script>').removesuffix('</script>')+r'''
assert.equal(node('activity').hidden,false);assert.equal(node('workflow').hidden,true);assert.equal(node('results').hidden,true);
showWorkspaceView('add-videos');assert.equal(node('workflow').hidden,false);assert.equal(node('workflow').open,true);assert.equal(node('activity').hidden,true);assert.equal(node('workflow').value,'preserve me');assert.equal(links[1].attrs['aria-current'],'page');
showWorkspaceView('results');assert.equal(node('results').hidden,false);assert.equal(node('reports').hidden,false);assert.equal(node('reports').open,false);assert.equal(node('workflow').hidden,true);
location.hash='#reports';assert.equal(node('reports').open,true);
location.hash='#activity';assert.equal(node('activity').hidden,false);assert.equal(node('results').hidden,true);
assert.equal(node('lifetime-saved').hidden,false);assert.equal(node('resource-status').hidden,false);
showWorkspaceView('overview');assert.equal(node('workspace-title').textContent,'Overview');
'''
        subprocess.run(['node','-e',harness],check=True,capture_output=True,text=True,timeout=10)

    def test_redesign_text_contrast(self):
        def luminance(color):
            values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            return sum((v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)*w for v,w in zip(values,(.2126,.7152,.0722)))
        def ratio(a,b):
            low,high=sorted((luminance(a),luminance(b)))
            return (high+.05)/(low+.05)
        for block in re.findall(r':root(?:\[data-theme=dark\])?\{([^}]+)',STYLE)[:2]:
            colors=dict(re.findall(r'--([\w-]+):(#[0-9a-f]{6})',block))
            for foreground in ('text','muted'):
                for background in ('bg','panel','soft'):
                    self.assertGreaterEqual(ratio(colors[foreground],colors[background]),4.5)
            self.assertGreaterEqual(ratio(colors['accent-text'],colors['accent']),4.5)
