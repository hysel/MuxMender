import http.client
from http.server import ThreadingHTTPServer
import json
import re
import shutil
import subprocess
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import app_service as app
from dashboard import Catalog, latest_outcome, file_savings, make_handler
from ui.app import HTML


class AppServiceTests(unittest.TestCase):
    def test_network_security_and_mount_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'media').mkdir();(root/'out').mkdir()
            env=dict(MUXMENDER_MEDIA_ROOT=str(root/'media'),MUXMENDER_OUTPUT_ROOT=str(root/'out'))
            with self.assertRaises(ValueError):app.config(env)
            env.update(MUXMENDER_ALLOWED_HOSTS='nas:8767',MUXMENDER_DASHBOARD_PASSWORD='unique-test-password')
            self.assertEqual(app.config(env)[4],('nas:8767',))
            self.assertEqual(app.config(env)[5],'')
            del env['MUXMENDER_DASHBOARD_PASSWORD']
            self.assertEqual(app.config(env)[5],'')
            env['MUXMENDER_ALLOWED_HOSTS']='*:8767'
            with self.assertRaises(ValueError):app.config(env)
            env['MUXMENDER_ALLOWED_HOSTS']='nas:8767'
            env['MUXMENDER_OUTPUT_ROOT']=str(root/'media')
            with self.assertRaises(ValueError):app.config(env)

    def test_worker_is_idle_by_default_and_requires_readonly_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'media').mkdir();(root/'out').mkdir()
            source=root/'media'/'a.mkv';source.write_bytes(b'original')
            self.assertIsNone(app.worker_command({},root/'media',root/'out'))
            env=dict(MUXMENDER_SOURCE='a.mkv',MUXMENDER_PLAYBACK_CODECS='hevc,av1')
            with patch.object(app,'is_read_only',return_value=False):
                with self.assertRaises(ValueError):app.worker_command(env,root/'media',root/'out')
            with patch.object(app,'is_read_only',return_value=True):
                cmd=app.worker_command(env,root/'media',root/'out')
                self.assertIn('auto',cmd)
                self.assertNotIn('--encode-best',cmd)
                env['MUXMENDER_SOURCE']='../outside.mkv';(root/'outside.mkv').write_bytes(b'other')
                with self.assertRaises(ValueError):app.worker_command(env,root/'media',root/'out')

    def test_host_auth_and_readonly_http(self):
        with tempfile.TemporaryDirectory() as d:
            handler=make_handler(Catalog(Path(d)),page=HTML,allowed_hosts=('nas:8767',),
                                 authorize=lambda s:s=='test-auth',app_provider=lambda:dict(worker='Idle'))
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            def request(path,host,auth='',method='GET'):
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                conn.request(method,path,headers={'Host':host,'Authorization':auth})
                response=conn.getresponse();status=response.status;body=response.read();conn.close();return status,body
            try:
                self.assertEqual(request('/','evil:8767','test-auth')[0],403)
                self.assertEqual(request('/','nas:8767')[0],401)
                self.assertEqual(request('/api/log','nas:8767')[0],401)
                self.assertEqual(request('/api/app','nas:8767','test-auth'),(200,b'{"worker": "Idle"}'))
                self.assertEqual(request('/','nas:8767','test-auth')[0],200)
                self.assertEqual(request('/api/enqueue','nas:8767','test-auth','POST')[0],501)
            finally:server.shutdown();worker.join();server.server_close()

    def test_auto_outcome_and_actual_savings(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'status.json').write_text(json.dumps(dict(state='validated-copy-awaiting-playback',saved_percent=42,output=str(root/'out.mkv'))))
            outcome,_=latest_outcome(root,root)
            self.assertEqual(file_savings(outcome),42)
            (root/'status.json').write_text(json.dumps(dict(state='trials-completed',decision=dict(action='keep_original',reason='Quality gate failed'))))
            outcome,_=latest_outcome(root,root)
            self.assertEqual(outcome['status'],'skipped')
            self.assertEqual(outcome['detail'],'Quality gate failed')
            self.assertIsNone(file_savings(outcome))

    def test_page_reuses_theme_and_has_no_write_actions(self):
        self.assertIn('<h1>Media workspace</h1>',HTML)
        self.assertLess(HTML.index('id="activity"'),HTML.index('id="workflow"'))
        self.assertNotIn('/api/app',HTML)
        self.assertIn('prefers-reduced-motion',HTML)
        self.assertIn('Skip to workspace',HTML)
        self.assertNotIn('Capability checks',HTML)
        self.assertIn('textContent',HTML)
        self.assertNotIn('Run NVIDIA validation from the terminal',HTML)
        self.assertNotIn('127.0.0.1 only',HTML)

    @unittest.skipUnless(shutil.which('node'), 'Node required for DOM-model checks')
    def test_dashboard_dom_and_queue_rendering(self):
        harness=(Path(__file__).parent/'dashboard_ui_test.js').read_text(encoding='utf-8')
        scripts='\n'.join(re.findall(r'<script>(.*?)</script>',HTML,re.S))
        mock="""
globalThis.setTimeout=()=>0; globalThis.setInterval=()=>0;
globalThis.fetch=()=>new Promise(()=>{});
"""
        check="""
assert(userReason({state:'skipped',reason:'Quality threshold not met'}).includes('quality checks'),'Clear quality reason');
assert(userReason({state:'skipped',reason:'insufficient_savings'}).includes('enough space'),'Clear savings reason');
assert(userReason({state:'skipped',reason:'HDR unsupported'}).includes('not supported'),'Clear unsupported reason');
assert(resultGroup('failed')==='attention','Failure is not success');
receiveControls({jobs:[{id:'one',source:'/media/<script>.mkv',state:'skipped',reason:'Quality failed'}]});
assert(collect(userEl('user-results')).some(x=>x.textContent==='<script>.mkv'),'Safe filename text');
userEl('result-filter').value='ready';userEl('result-filter').change();
assert(collect(userEl('user-results')).some(x=>x.textContent==='No videos match this filter.'),'Filtering works');
applyTheme('dark');assert(userEl('theme').value==='dark','Theme selected');
userEl('result-filter').value='all';userEl('result-filter').change();
const originalCard=userEl('user-results').children[0];
receiveControls({paused:true,pause_reason:'Queue paused after failures',counts:{failed:1,pending:2},jobs:[{id:'one',source:'/media/<script>.mkv',state:'failed'}]});
assert(userEl('user-results').children[0]===originalCard,'Stable result node during status update');
catalogJobs=[{id:'legacy',source:'/media/old.mkv',state:'verified'}];
assert(mergedResults().length===1,'Legacy development jobs excluded');
assert(collect(originalCard).some(x=>x.textContent==='Processing error'),'Status changes without replacing details');
assert(collect(userEl('current-work')).some(x=>x.textContent.includes('1 of 3')),'Queue summary');
assert(collect(userEl('current-work')).some(x=>x.textContent.includes('Queue paused after failures')),'Pause reason prominent');
const sorting=[{id:'queued-last',source:'/a/video10.mkv',created:90,finished:100,state:'skipped'},
 {id:'finished-last',source:'/a/video2.mkv',created:10,finished:200,state:'replaced',saved_bytes:100},
 {id:'running',source:'/a/running.mkv',created:300,state:'running'},
 {id:'no-date',source:'/a/no-date.mkv',state:'failed'}];
assert(sortedResults(sorting.filter(j=>j.state!=='running'))[0].id==='finished-last','Sort by completion, not submission');
assert(sortedResults(sorting,'name').findIndex(j=>j.id==='finished-last')<sortedResults(sorting,'name').findIndex(j=>j.id==='queued-last'),'Natural filename sorting');
assert(sortedResults(sorting,'oldest').at(-1).id==='no-date','Missing dates last');
assert(sortedResults(sorting,'saved')[0].id==='finished-last','Actual replacements sort above unconfirmed savings');
assert(sorting[0].id==='queued-last','Sorting does not mutate requests');
assert(resultMeta({...sorting[1],settings:{mode:'replace'}}).includes('Finished'),'Completion date visible');
assert(resultMeta({state:'pending',created:10}).includes('Queued'),'Queued timestamp labelled');
assert(resultMeta({state:'running',created:10,started:20}).includes('Started'),'Running timestamp labelled');
receiveControls({jobs:sorting});
assert(!collect(userEl('user-results')).some(x=>x.textContent==='running.mkv'),'Active jobs excluded from finished results');
assert(userEl('result-count').textContent==='Showing 3 of 3 matching videos','Accurate visible count');
userEl('result-filter').value='active';userEl('result-filter').change();
assert(collect(userEl('user-results')).some(x=>x.textContent==='running.mkv'),'Active filter available');
assert(!collect(userEl('user-results')).some(x=>x.textContent==='video2.mkv'),'Active filter excludes finished');
const tied=[{id:'b',source:'/a/same.mkv',finished:20},{id:'a',source:'/a/same.mkv',finished:20}];
assert(sortedResults(tied)[0].id==='a','Stable tie breaker');
assert(userReason({state:'skipped',reason:'Already efficient for current settings: original retained.'}).startsWith('Already efficient'),'Efficiency reason prominent');
userEl('result-filter').value='all';userEl('result-batch').value='';
const attempts=[{id:'old',source:'/media/retry.mkv',created:1,finished:2,state:'failed'},
 {id:'retry',source:'/media/retry.mkv',created:3,state:'pending'},
 {id:'converted',source:'/media/other.mp4',published_path:'/media/other.mkv',created:4,finished:5,state:'replaced',saved_bytes:100},
 {id:'new-path',source:'/media/other.mkv',created:6,finished:7,state:'skipped'}];
receiveControls({jobs:attempts,view:{},counts:{pending:1,failed:1,replaced:1,skipped:1}});
assert(groupedAttempts(attempts).length===2,'Published container aliases group together');
assert(userEl('user-results').children.length===2,'One result per video');
assert(collect(userEl('user-results')).some(n=>n.textContent.startsWith('Retry queued')),'Active retry visible over previous failure');
const keptCard=userEl('user-results').children[0],openDetails=keptCard.children.find(n=>n.tag==='details');openDetails.open=true;
const focused=collect(openDetails).find(n=>n.tag==='button');focused.focus();
receiveControls({jobs:[...attempts,{id:'extra',source:'/media/extra.mkv',created:8,finished:9,state:'failed'}],view:{}});
assert(openDetails.open&&document.activeElement===focused&&userEl('user-results').contains(keptCard),'Polling preserves expanded details and focused card when new results arrive');
document.activeElement=null;
receiveControls({jobs:attempts,view:{archived_ids:['old','converted','new-path']}});
assert(userEl('user-results').children.length===1&&userEl('user-results').children[0].tag==='p','Archived finished results hidden; first-attempt active is in Progress');
userEl('show-archived').checked=true;renderUserResults(true);
assert(userEl('user-results').children.length===2,'Show archived restores history');
assert(!savedText({state:'tested',file_savings_percent:40}).startsWith('Confirmed'),'Samples never count as confirmed savings');
assert(evidenceText({evidence:{quality:[{id:'trial',samples:[{mean:95,p5:90,passed:true}]}]}}).includes('not percent quality preserved'),'Metric meaning explicit');
assert(outcomeLabel({state:'skipped',decision_code:'already_efficient_for_settings'}).startsWith('Already efficient'),'Efficient outcome distinct');
assert(workflowStep('Publishing validated copy').startsWith('Replacement'),'Publication stage distinct');
assert(workflowStep('full-encode').startsWith('Encoding'),'Encoding stage distinct');
catalogJobs=[{directory:'E:\\\\output\\\\request-retry\\\\job-one',updated:1,phase:'full-encode'},
 {directory:'E:\\\\output\\\\request-retry\\\\job-two',updated:2,phase:'Publishing validated copy'}];
assert(mergedResults().find(j=>j.id==='retry').phase==='Publishing validated copy','Newest linked stage selected across Windows paths');
userEl('toggle-updates').click();assert(globalThis.liveUpdatesPaused,'Pause display independently');
console.log('Queue DOM-model checks passed.');
"""
        result=subprocess.run(['node'],input=mock+harness+scripts+check,text=True,encoding='utf-8',capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Queue DOM-model checks passed.',result.stdout)

    @unittest.skipUnless(shutil.which('node'), 'Node required for DOM-model checks')
    def test_control_ui_preview_submit_and_safe_text(self):
        from ui.controls import SCRIPT
        harness=(Path(__file__).parent/'dashboard_ui_test.js').read_text(encoding='utf-8')
        script=re.search(r'<script>(.*?)</script>',SCRIPT,re.S).group(1)
        mock="globalThis.setTimeout=()=>0;globalThis.fetch=()=>new Promise(()=>{});"
        checks="""
(async()=>{
let submitted=0;
globalThis.fetch=async(url,options)=>({ok:true,json:async()=>{
 if(url==='/api/controls')return {ready:true,csrf_token:'token',paused:false,counts:{pending:1},jobs:[]};
 if(url.startsWith('/api/media'))return {path:'.',parent:null,next_offset:null,entries:[{name:'<img onerror=evil>.mkv',path:'video.mkv',directory:false}]};
 const body=JSON.parse(options.body);assert(options.headers['X-MuxMender-CSRF']==='token','CSRF header');
 if(body.action==='preview')return {preview_id:'preview',settings:body.settings,files:[{path:'video.mkv',signature:[100,2]}],note:'Original retained'};
 if(body.action==='submit'){assert(body.preview_id==='preview','Submit exact preview');submitted++;return {queued:1}};
}});
await refreshControls();await browseMedia();
assert(controlElement('preview-job').disabled,'No operation before folder selection');
assert(!collect(controlElement('media-browser')).some(x=>x.textContent.includes('<img onerror=evil>')),'Picker shows folders only');
await selectFolder('.');
assert(!controlElement('folder-actions').hidden,'Actions appear after selecting folder');
assert(controlElement('folder-picker').hidden,'Picker closes after folder selection');
assert(collect(controlElement('video-choice')).some(x=>x.textContent.includes('<img onerror=evil>')),'Filename remains safe text in folder workspace');
assert(controlElement('source-path').value==='.' ,'Selected folder becomes scope');
controlElement('video-choice').value='video.mkv';controlElement('video-choice').change();
assert(controlElement('source-path').value==='video.mkv','Individual video belongs to selected folder');
for(const [id,value] of [['source-path','video.mkv'],['operation','test'],['codec-choice','auto'],['hardware-choice','auto'],['quality-choice','auto'],['minimum-savings','10']])controlElement(id).value=value;
controlElement('source-depth').value='recursive';
await controlElement('preview-job').click();
assert(!controlElement('submit-job').disabled,'Preview enables confirmation');
await controlElement('submit-job').click();
assert(submitted===1,'One request submitted');assert(controlElement('submit-job').disabled,'Repeat click blocked');
await controlElement('preview-job').click();invalidatePreview();
assert(controlElement('request-preview').hidden,'Changing scope invalidates preview');
console.log('Control UI checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
        result=subprocess.run(['node'],input=mock+harness+script+checks,text=True,encoding='utf-8',capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Control UI checks passed.',result.stdout)


if __name__=='__main__':unittest.main()
