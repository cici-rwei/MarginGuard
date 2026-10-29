/* All identifiers, amounts and histories below are fictional test fixtures. */
'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const risk=require('../static/js/business_risk.js');
const Context=require('../static/js/business_context.js');
const context={source_kind:'user_csv',dataset_id:'synthetic-dataset',revision:'r1',series_id:'synthetic-series',forecast_origin:'2024-03-24',currency:'AUD'};
const snapshot={context,inputs:{current_stock:5,lead_time_days:3,safety_stock:10,on_order_units:0,excess_cover_days:'30',stock_as_of:'2024-03-24',hypothetical_stock_at_origin:false},suggested_reorder_quantity:23};
const row={series_id:'synthetic-series',item_id:'Fictional product',store_id:'Fictional store',forecast_start:'2024-03-25',forecast_end:'2024-04-07',forecast_demand:'84',current_stock:5,stock_as_of_date:'2024-03-24',expected_stock_date:'2024-03-24',risk_code:'stockout',status:'Stockout Risk',action:'Review stock',action_reason:'Synthetic engine explanation',issues:[]};
test('all analysis identity dimensions must match before a stock import is offered',()=>{
  assert.ok(risk.contextMatches(context,{...context}));
  for(const key of Object.keys(context))assert.equal(risk.contextMatches(context,{...context,[key]:'other'}),false,key);
  assert.equal(risk.contextMatches({...context,source_kind:'synthetic_demo'},{...context,source_kind:'synthetic_demo'}),false);
  assert.equal(risk.contextMatches(null,context),false);
});
test('risk detail links retain dataset revision and row identity, with URL encoding',()=>{
  const url=new URL(risk.detailUrl('/scenarios',{...context,dataset_id:'a&b'}, {...row,series_id:'x/y?z'}),'https://example.invalid');
  assert.equal(url.pathname,'/scenarios');assert.equal(url.searchParams.get('dataset'),'a&b');assert.equal(url.searchParams.get('series'),'x/y?z');assert.equal(url.searchParams.get('revision'),'r1');assert.equal(url.searchParams.get('mode'),'business');
  assert.throws(()=>risk.detailUrl('https://example.invalid',context,row));
});
test('filter request preserves server-owned filtering and rejects unsupported choices',()=>{
  const params=new URLSearchParams(risk.filterQuery('r1',{risk:'not_assessed',store:'Store & 2',search:'  product  ',sort:'stock_asc'}));
  assert.equal(params.get('store'),'Store & 2');assert.equal(params.get('search'),'product');assert.equal(params.get('sort'),'stock_asc');
  assert.throws(()=>risk.filterQuery('r1',{risk:'invented',sort:'priority'}));assert.throws(()=>risk.filterQuery('r1',{risk:'all',sort:'profit'}));
});
test('five KPIs display Python counts without treating unknown counts as zero',()=>{
  const html=risk.summaryMarkup({products_analysed:11,high_stockout_risk:3,excess_inventory_risk:2,sufficient_inventory:4,data_incomplete:null});
  assert.equal((html.match(/class="kpi"/g)||[]).length,5);assert.match(html,/Products Analysed/);assert.match(html,/Not available/);assert.match(html,/>11</);assert.match(html,/>3</);
});
test('row display preserves server order and escapes uploaded identifiers and explanations',()=>{
  const html=risk.rowsMarkup([{...row,item_id:'<script>bad</script>'},{...row,item_id:'second',action_reason:'<img onerror="bad">'}],context);
  assert.doesNotMatch(html,/<script>|<img /);assert.match(html,/&lt;script&gt;/);assert.ok(html.indexOf('&lt;script&gt;')<html.indexOf('second'));
  assert.match(html,/data-risk-detail-link/);assert.doesNotMatch(html,/data-business-link/);
});
test('unknown inventory is not zero and missing forecasts have no decision deep link',()=>{
  const html=risk.rowsMarkup([{...row,current_stock:null,forecast_demand:null,forecast_start:null,forecast_end:null,risk_code:'not_assessed',status:'Not assessed'}],context);
  assert.match(html,/Not available/);assert.doesNotMatch(html,/data-risk-detail-link/);assert.doesNotMatch(html,/0 units/);
});
test('draft inventory preview does not expose actions that imply it is already confirmed',()=>{
  assert.doesNotMatch(risk.rowsMarkup([row],context,true),/data-risk-detail-link/);
  assert.match(risk.rowsMarkup([row],context),/Review financial decision/);
});
test('inventory import keeps recorded closing date and explicit non-hypothetical flag',()=>{
  assert.deepEqual(risk.snapshotValues(snapshot,context,'inventory'),snapshot.inputs);
  assert.equal(risk.snapshotValues(snapshot,context,'inventory').hypothetical_stock_at_origin,false);
});
test('financial import cannot silently replace price, cost, budget or purchase quantity',()=>{
  const original=JSON.stringify(snapshot),values=risk.snapshotValues(snapshot,context,'scenarios');
  assert.deepEqual(Object.keys(values),['current_stock','lead_time_days','on_order_units','stock_as_of','hypothetical_stock_at_origin']);
  assert.equal(values.on_order_units,0);assert.equal(JSON.stringify(snapshot),original);assert.deepEqual(risk.snapshotValues(snapshot,context,'scenarios',true),{order_quantity:23});
});
test('stale snapshot and existing on-order stock cannot be automatically imported',()=>{
  assert.throws(()=>risk.snapshotValues(snapshot,{...context,revision:'r2'},'inventory'));
  assert.throws(()=>risk.snapshotValues({...snapshot,inputs:{...snapshot.inputs,on_order_units:4}},context,'scenarios'),/already on order/);
  assert.throws(()=>risk.snapshotValues({...snapshot,inputs:{...snapshot.inputs,on_order_units:4}},context,'scenarios',true));
});
test('zero order suggestion remains valid but unavailable suggestions are not invented',()=>{
  assert.deepEqual(risk.snapshotValues({...snapshot,suggested_reorder_quantity:0},context,'scenarios',true),{order_quantity:0});
  for(const value of [null,undefined,-1,Infinity])assert.throws(()=>risk.snapshotValues({...snapshot,suggested_reorder_quantity:value},context,'scenarios',true));
});
function overviewHarness(request,options={}){
  const nodes=new Map();
  const el=id=>{if(!nodes.has(id))nodes.set(id,{value:'',innerHTML:'',textContent:'',hidden:false,setAttribute(){}});return nodes.get(id);};
  el('risk-filter').value='all';el('risk-sort').value='priority';
  global.window={MarginGuardContext:Context};
  const view=risk.createOverview({document:{getElementById:el},request,getSession:async()=>({limits:{file_bytes:1000}}),onConfirmed:async()=>{},...options});
  return {view,el};
}
test('stale overview responses cannot overwrite a newly confirmed dataset revision',async()=>{
  const pending=[];const {view,el}=overviewHarness(()=>new Promise(resolve=>pending.push(resolve)));
  const first=view.setDataset({dataset_id:context.dataset_id,revision:'r1',series:[row]});
  const second=view.setDataset({dataset_id:context.dataset_id,revision:'r2',series:[row]});
  pending[1]({dataset_id:context.dataset_id,revision:'r2',summary:{products_analysed:2},rows:[{...row,item_id:'CURRENT'}]});await second;
  pending[0]({dataset_id:context.dataset_id,revision:'r1',summary:{products_analysed:99},rows:[{...row,item_id:'OLD'}]});await first;
  assert.match(el('priority-risk-list').innerHTML,/CURRENT/);assert.doesNotMatch(el('priority-risk-list').innerHTML,/OLD/);delete global.window;
});
test('expiry clears the risk list and ignores any response still in flight',async()=>{
  let finish;const {view,el}=overviewHarness(()=>new Promise(resolve=>finish=resolve));
  const loading=view.setDataset({dataset_id:context.dataset_id,revision:'r1',series:[row]});view.clear();finish({summary:{products_analysed:1},rows:[row]});await loading;
  assert.equal(el('business-risk-overview').hidden,true);assert.equal(el('priority-risk-list').innerHTML,'');delete global.window;
});
test('a response with another dataset revision fails closed and leaves filters intact',async()=>{
  const {view,el}=overviewHarness(async()=>({dataset_id:context.dataset_id,revision:'r2',rows:[row]}));
  el('risk-search').value='keep my search';await view.setDataset({dataset_id:context.dataset_id,revision:'r1',series:[row]});
  assert.equal(el('risk-errors').hidden,false);assert.equal(el('priority-risk-list').innerHTML,'');assert.equal(el('risk-search').value,'keep my search');delete global.window;
});
function snapshotHarness(request,kind='scenarios'){
  const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,{hidden:false,disabled:false,innerHTML:'',textContent:''});return nodes.get(id);};
  const box={id:'',className:'',innerHTML:'',querySelector:selector=>get(selector.slice(1))};
  const doc={getElementById:()=>null,createElement:()=>box};
  let current={current_stock:'50',lead_time_days:'7',cash_budget:'500'},applied=null;
  const form={ownerDocument:doc,before(){}};global.window={MarginGuardContext:Context};
  const control=risk.attachSnapshot({form,snapshot,context,kind,currentValues:()=>current,onApply:values=>{applied=values;},isCurrent:()=>true,request});
  return {control,get,box,applied:()=>applied,edit:values=>{current={...current,...values};control.invalidate();}};
}
test('snapshot confirmation requires an explicit preview and preserves unrelated financial inputs',async()=>{
  const {get,applied,box}=snapshotHarness(async()=>({context,inventory_import:snapshot}));
  assert.equal(applied(),null);get('review-snapshot-inputs').onclick();assert.match(get('snapshot-differences').innerHTML,/50 units → 5 units/);assert.equal(applied(),null);
  await get('apply-snapshot').onclick();assert.equal(applied().current_stock,5);assert.equal(applied().cash_budget,undefined);assert.match(box.innerHTML,/Prices, costs and budgets stay as entered/);delete global.window;
});
test('editing while snapshot verification is in flight cancels the proposed overwrite',async()=>{
  let finish;const harness=snapshotHarness(()=>new Promise(resolve=>finish=resolve));
  harness.get('review-snapshot-inputs').onclick();const pending=harness.get('apply-snapshot').onclick();harness.edit({current_stock:'99'});finish({context,inventory_import:snapshot});await pending;
  assert.equal(harness.applied(),null);assert.equal(harness.get('snapshot-confirmation').hidden,true);delete global.window;
});
test('server version mismatch during confirmation keeps the current financial assumptions',async()=>{
  const harness=snapshotHarness(async()=>({context:{...context,revision:'r2'},inventory_import:{...snapshot,context:{...context,revision:'r2'}}}));
  harness.get('review-snapshot-order').onclick();await harness.get('apply-snapshot').onclick();
  assert.equal(harness.applied(),null);assert.equal(harness.get('snapshot-import-error').hidden,false);delete global.window;
});
function mainHarness(query='?mode=business&dataset=synthetic-dataset'){
  const fs=require('node:fs'),vm=require('node:vm');
  const nodes=new Map(),el=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',hidden:false,value:'',classList:{toggle(){}},setAttribute(){}});return nodes.get(id);};
  const ready={dataset_id:'synthetic-dataset',revision:'r1',meta:{currency:'AUD'},series:[],catalog_series:[{series_id:'missing-history',item_id:'Fictional short history',store_id:'Test store'}]};
  const requests=[],overview=[];
  const sandbox={URLSearchParams,Intl,console,AbortController,document:{body:{dataset:{page:'dashboard',demoMode:'m5'}},getElementById:el,querySelector:el,querySelectorAll:()=>[]},location:{search:query},history:{replaceState(){}},window:{sessionStorage:{getItem:()=>null,setItem(){},removeItem(){},length:0},MarginGuardContext:Context,MarginGuardRisk:{createOverview:()=>({setDataset:async data=>overview.push(data),clear(){}})},MarginGuardUpload:{attach(){},setActive(){},request:async path=>{requests.push(path);return ready;}}}};
  vm.createContext(sandbox);const source=fs.readFileSync(require('node:path').join(__dirname,'../static/js/main.js'),'utf8');vm.runInContext(source.slice(0,source.indexOf('(async()=>{')),sandbox);
  return {sandbox,el,overview,requests,run:code=>vm.runInContext(code,sandbox)};
}
test('confirmed datasets with no forecastable series still show the risk overview without fabricated analysis',async()=>{
  const harness=mainHarness();await harness.run('loadBusinessCatalog()');
  assert.equal(harness.overview.length,1);assert.equal(harness.overview[0].catalog_series.length,1);assert.equal(harness.el('content').hidden,true);assert.equal(harness.el('series-selection').hidden,true);assert.equal(harness.requests.length,1);assert.match(harness.el('mode-notice').textContent,/No forecast or financial result has been invented/);
});
test('a stale decision URL is rejected before silently switching the data version',async()=>{
  const harness=mainHarness('?mode=business&dataset=synthetic-dataset&revision=old');
  await assert.rejects(harness.run('loadBusinessCatalog()'),/older data version/);assert.equal(harness.overview.length,0);
});
test('uploaded business homepage gets a risk-oriented title without renaming Demo templates',()=>{
  const harness=mainHarness();harness.run('setModeLabels()');
  assert.equal(harness.el('.page-heading h1').textContent,'Business Risk Overview');assert.match(harness.sandbox.document.title,/^Business Risk Overview/);
});
test('successful stock confirmation followed by catalog failure clears stale results and preserves the new revision',async t=>{
  const NativeFormData=global.FormData;t.after(()=>{global.FormData=NativeFormData;delete global.window;});
  global.FormData=class {constructor(){this.values=new Map();}set(key,value){this.values.set(key,value);}};
  const requests=[];
  const request=async(path,options={})=>{
    requests.push({path,options});
    if(path.endsWith('/inventory-uploads'))return {upload_id:'pending-inventory',revision:'upload-r1',dataset_revision:'r1',report:{issues:[]},overview:{rows:[row]}};
    if(path.endsWith('/confirm'))return {dataset_id:context.dataset_id,revision:'r2'};
    const revision=new URL(path,'https://example.invalid').searchParams.get('revision');
    return {dataset_id:context.dataset_id,revision,summary:{products_analysed:1},rows:[{...row,item_id:revision==='r1'?'OLD SNAPSHOT':'NEW SNAPSHOT'}],filtered_count:1};
  };
  const {view,el}=overviewHarness(request,{onConfirmed:async()=>{throw Error('Cannot reach MarginGuard. Retry shortly.');}});
  await view.setDataset({dataset_id:context.dataset_id,revision:'r1',series:[row]});
  assert.match(el('priority-risk-list').innerHTML,/OLD SNAPSHOT/);
  el('inventory-csv-file').files=[{size:50}];el('inventory-no-on-order').checked=false;
  const form={reportValidity:()=>true,querySelector:()=>({disabled:false})};
  await el('inventory-upload-form').onsubmit({preventDefault(){},currentTarget:form});
  await el('confirm-inventory-upload').onclick();
  assert.equal(el('risk-kpis').innerHTML,'');assert.equal(el('priority-risk-list').innerHTML,'');assert.equal(el('inventory-upload-report').hidden,true);
  assert.match(el('inventory-upload-status').textContent,/Snapshot saved, but updated results are unavailable/);
  assert.doesNotMatch(el('inventory-upload-status').textContent,/now uses this version/);
  await view.refresh();assert.match(requests.at(-1).path,/revision=r2/);assert.match(el('priority-risk-list').innerHTML,/NEW SNAPSHOT/);
});
test('stock calculation details retain Python values and distinguish no demand from missing data',()=>{
  const html=risk.rowsMarkup([{...row,risk_code:'sufficient',inventory_inputs:snapshot.inputs,risk:{lead_time_demand:'18.25',days_of_cover:null,excess_cover_days:'30',stockout_risk:false,excess_inventory_warning:true,suggested_reorder_quantity:23}}],context);
  for(const phrase of ['Suggested Reorder Quantity','23 units','18.25 units','Backup Stock','No forecast demand','Stock Already Ordered','not current stock','Stockout Warning','Excess Stock Warning','Sufficient for delivery-time demand + backup target'])assert.ok(html.includes(phrase),phrase);
  assert.doesNotMatch(html,/NaN|undefined/);
});
