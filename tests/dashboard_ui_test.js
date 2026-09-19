// Pure DOM-model tests; no browser, external packages, or network needed.
// Execute in a Node vm context with the dashboard script passed as `source`.
class Element {
  constructor(tag='div') { this.tag=tag; this.children=[]; this.style={}; this.attrs={}; this.value=''; this.hidden=false; this.textContent=''; this.classList={toggle(){}}; }
  append(...items) { for(const item of items){item.remove?.();item.parentNode=this;this.children.push(item)} }
  replaceChildren(...items) { for(const item of this.children)item.parentNode=null;this.children=[];this.append(...items); }
  remove() { if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(n=>n!==this);this.parentNode=null} }
  insertBefore(item,before) { item.remove();const i=before?this.children.indexOf(before):this.children.length;this.children.splice(i,0,item);item.parentNode=this; }
  contains(item) { return item===this||this.children.some(n=>n.contains?.(item)); }
  focus() { document.activeElement=this; }
  setAttribute(k,v) { this.attrs[k]=v; }
  addEventListener(k,v) { const old=this[k];this[k]=(...args)=>{old?.(...args);return v(...args)}; }
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
  assert(!done('skipped'),'Skipped is not a successful completion');
  data=[{...base,state:'skipped',detail:'Quality threshold not met'}];summary();renderFocus();
  assert(collect(document.querySelector('#summary')).some(n=>n.textContent==='Skipped'),'Separate skipped count');
  assert(!collect(document.querySelector('#focus')).some(n=>n.textContent==='No worthwhile size reduction. Original retained.'),'No misleading savings rejection');
  data=[{...base,id:'new',results:[]},{...base,id:'old',results:[{label:'old',status:'passed'}]}];
  selected=null;renderFocus();
  assert(savingsText({file_savings_percent:70.213})==='70.2% smaller','Savings rounded');
  assert(savingsText({file_savings_percent:-12})==='12.0% larger','Larger files are not clamped');
  assert(savingsText({file_savings_percent:null})==='Pending / unavailable','No invented savings');
  data=[base];renderFocus();
  base.file_savings_percent=70.213;base.savings_scope='1 validated batch file(s)';renderFocus();
  assert(collect(document.querySelector('#focus')).some(n=>n.textContent==='File-size savings: 70.2% smaller'),'Focus shows savings');
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
