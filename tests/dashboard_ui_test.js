// Pure DOM-model tests; no browser, external packages, or network needed.
// Execute in a Node vm context with the dashboard script passed as `source`.
class Element {
  constructor(tag='div') { this.tag=tag; this.children=[]; this.style={}; this.attrs={}; this.value=''; this.hidden=false; this.textContent=''; this.classList={toggle(){}}; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=items; }
  setAttribute(k,v) { this.attrs[k]=v; }
  addEventListener(k,v) { this[k]=v; }
  scrollIntoView() {}
}
const elements=new Map();
const document={createElement:tag=>new Element(tag),querySelector:s=>{if(!elements.has(s))elements.set(s,new Element());return elements.get(s)},querySelectorAll:()=>[]};
document.querySelector('#filter').value='all';
function collect(node){return [node,...node.children.filter(x=>x instanceof Element).flatMap(collect)]}
function assert(value,message){if(!value)throw Error(message)}
const base={id:'test',title:'Validate NVIDIA',state:'running',progress_kind:'structured',
  completed:6,total:8,unit:'tests',percent:75,stage_percent:95,phase:'Encoding',updated:1000,started:900,
  elapsed:100,results:[],has_log:true,directory:'reports/job-test'};

function checkDashboardUi(){
  data=[base];renderFocus();
  let bars=collect(document.querySelector('#focus')).filter(n=>n.attrs.role==='progressbar');
  assert(bars.length===1&&bars[0].attrs['aria-valuenow']===75,'One overall bar at 75%');
  base.stage_percent=0;base.phase='Checking output';renderFocus();
  bars=collect(document.querySelector('#focus')).filter(n=>n.attrs.role==='progressbar');
  assert(bars.length===1&&bars[0].attrs['aria-valuenow']===75,'Stage reset must not move overall backwards');
  base.total=null;base.percent=null;renderFocus();
  assert(!collect(document.querySelector('#focus')).some(n=>n.attrs.role==='progressbar'),'Unknown progress must have no bar');
  renderHistory();
  assert(document.querySelector('#history-body').children.length===1,'History renders');
  document.querySelector('#search').value='does not match';renderHistory();
  assert(document.querySelector('#history-count').textContent==='Showing 0 of 0 jobs','History filtering works');
  return 'Dashboard DOM-model checks passed.';
}
