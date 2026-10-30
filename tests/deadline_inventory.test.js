/* Fictional fixtures only: no uploaded business records or credentials. */
'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const risk=require('../static/js/business_risk.js');
const Context=require('../static/js/business_context.js');
const context={source_kind:'user_csv',dataset_id:'fictional-sales-dataset',revision:'r1',series_id:'fictional-product-store',forecast_origin:'2024-03-24',currency:'AUD'};
const inputs={current_stock:5,lead_time_days:7,safety_stock:10,on_order_units:0,excess_cover_days:'30',stock_as_of:'2024-03-24',hypothetical_stock_at_origin:false};
const snapshot={context,inputs,suggested_reorder_quantity:23};

test('confirmed inventory fills a new form without requiring a redundant manual import',()=>{
  const plan=risk.inventorySnapshotPlan(snapshot,context);
  assert.deepEqual(plan,{values:inputs,requiresConfirmation:false});
  assert.notEqual(plan.values,inputs);
});
test('matching browser string drafts remain eligible for automatic recalculation after refresh',()=>{
  const saved={...inputs,current_stock:'5',lead_time_days:'7',safety_stock:'10',on_order_units:'0',excess_cover_days:30};
  assert.equal(risk.inventorySnapshotPlan(snapshot,context,saved).requiresConfirmation,false);
});
test('any changed or partly completed manual draft needs confirmation before replacement',()=>{
  for(const saved of [{current_stock:'99'},{...inputs,current_stock:6},{...inputs,lead_time_days:'14'},{...inputs,safety_stock:0},{...inputs,on_order_units:2},{...inputs,excess_cover_days:'90'}]){
    assert.equal(risk.inventorySnapshotPlan(snapshot,context,saved).requiresConfirmation,true,JSON.stringify(saved));
  }
});
test('stock dates and the hypothetical-stock flag are compared without coercing a changed draft',()=>{
  for(const saved of [{...inputs,stock_as_of:'2024-03-23'},{...inputs,hypothetical_stock_at_origin:true},{...inputs,hypothetical_stock_at_origin:'false'}]){
    assert.equal(risk.inventorySnapshotPlan(snapshot,context,saved).requiresConfirmation,true);
  }
});
test('explicit zero stock is valid and is not mistaken for unknown stock',()=>{
  const zero={...snapshot,inputs:{...inputs,current_stock:0,safety_stock:0,on_order_units:0}};
  const plan=risk.inventorySnapshotPlan(zero,context);
  assert.equal(plan.values.current_stock,0);assert.equal(plan.requiresConfirmation,false);
  assert.equal(risk.inventorySnapshotPlan(zero,context,{...zero.inputs,current_stock:'0'}).requiresConfirmation,false);
});
test('missing snapshot or required inputs remain unknown instead of manufacturing zero',()=>{
  for(const value of [null,undefined,{}, {...snapshot,inputs:null}])assert.equal(risk.inventorySnapshotPlan(value,context),null);
  for(const key of Object.keys(inputs))for(const value of [null,undefined,'']){
    assert.equal(risk.inventorySnapshotPlan({...snapshot,inputs:{...inputs,[key]:value}},context),null,key);
  }
});
test('another data source, dataset, revision, product, origin or currency cannot auto-populate stock',()=>{
  for(const key of Object.keys(context))assert.equal(risk.inventorySnapshotPlan(snapshot,{...context,[key]:'different'}),null,key);
  assert.equal(risk.inventorySnapshotPlan(snapshot,null),null);
});

function inventoryHarness(t,request,afterConfirmed){
  const NativeFormData=global.FormData,previousWindow=global.window;
  global.FormData=class {constructor(form){this.form=form;this.values=new Map();}set(key,value){this.values.set(key,value);}get(key){return this.values.get(key);}};
  global.window={MarginGuardContext:Context};
  t.after(()=>{global.FormData=NativeFormData;if(previousWindow===undefined)delete global.window;else global.window=previousWindow;});
  const ids=['inventory-upload-panel','inventory-upload-form','inventory-csv-file','inventory-no-on-order','inventory-upload-errors','inventory-upload-report','inventory-upload-status','inventory-file-status','confirm-inventory-upload','discard-inventory-upload'];
  const nodes=new Map(ids.map(id=>[id,{hidden:true,textContent:'',innerHTML:'',value:'',disabled:false,checked:false}]));
  const el=id=>nodes.get(id)||null,confirmed=[];
  // Unlike the earlier overview harness, absent portfolio controls really are null.
  const document={getElementById:el};
  let view;
  view=risk.createOverview({document,request,getSession:async()=>({limits:{file_bytes:1000}}),onConfirmed:async data=>{confirmed.push(data);if(afterConfirmed)await afterConfirmed(data);await view.setDataset({...data,has_inventory:true});}});
  const button={disabled:false},form={reportValidity:()=>true,querySelector:()=>button};
  const upload=async()=>{el('inventory-csv-file').files=[{size:100}];await el('inventory-upload-form').onsubmit({preventDefault(){},currentTarget:form});};
  return {view,el,confirmed,upload,button};
}
const ready={dataset_id:context.dataset_id,revision:'r1',series:[],has_inventory:false};
const pending={upload_id:'fictional-pending-stock',revision:'upload-r1',dataset_revision:'r1',report:{issues:[]},overview:{rows:[],inventory_quality:{row_count:1,matched_rows:1}}};

test('Inventory-only entry opens for the owned dataset and shows unknown or confirmed provenance',async t=>{
  const calls=[],h=inventoryHarness(t,async path=>{calls.push(path);});
  assert.equal(h.el('business-risk-overview'),null);
  await h.view.setDataset(ready);
  assert.equal(h.el('inventory-upload-panel').hidden,false);
  assert.match(h.el('inventory-file-status').textContent,/Inventory: Unknown/);
  assert.match(h.el('inventory-file-status').textContent,/never treated as zero/);
  await h.view.setDataset({...ready,has_inventory:true});
  assert.match(h.el('inventory-file-status').textContent,/Inventory CSV: Confirmed/);
  assert.match(h.el('inventory-file-status').textContent,/Source: your uploaded stock snapshot/);
  assert.equal(calls.length,0,'Inventory form does not fetch or manufacture a duplicate portfolio');
});
test('Inventory-only validate and confirm reuse stock endpoints and advance the same sales dataset revision',async t=>{
  const calls=[];let uploadCount=0;
  const h=inventoryHarness(t,async(path,options)=>{
    calls.push({path,options});
    if(path.endsWith('/confirm'))return {...ready,revision:'r2'};
    uploadCount++;return {...pending,dataset_revision:uploadCount===1?'r1':'r2'};
  });
  await h.view.setDataset(ready);await h.upload();
  assert.equal(h.confirmed.length,0);assert.equal(h.el('inventory-upload-report').hidden,false);
  assert.match(h.el('inventory-upload-status').textContent,/Review required/);
  assert.equal(calls[0].options.form.get('revision'),'r1');
  assert.equal(calls[0].options.form.get('assume_no_on_order'),'false');
  await h.el('confirm-inventory-upload').onclick();
  assert.equal(h.confirmed.length,1);assert.equal(h.confirmed[0].dataset_id,context.dataset_id);
  assert.equal(h.confirmed[0].revision,'r2');
  assert.deepEqual(calls[1].options.json,{revision:'r1',upload_revision:'upload-r1'});
  assert.match(h.el('inventory-upload-status').textContent,/Confirmed sales history is unchanged/);
  assert.equal(h.el('inventory-upload-report').hidden,true);
  await h.upload();assert.equal(calls.at(-1).options.form.get('revision'),'r2');
  assert.ok(calls.every(call=>call.path.startsWith('/api/business/datasets/'+context.dataset_id+'/inventory-uploads')));
});
test('validation failure is visible and retry keeps the existing sales dataset and revision',async t=>{
  const calls=[];let fail=true;
  const h=inventoryHarness(t,async(path,options)=>{calls.push({path,options});if(fail)throw Error('Current Stock must be a whole number.');return pending;});
  await h.view.setDataset({...ready,has_inventory:true});await h.upload();
  assert.equal(h.el('inventory-upload-errors').hidden,false);
  assert.match(h.el('inventory-upload-errors').innerHTML,/whole number/);
  assert.match(h.el('inventory-upload-status').textContent,/Confirmed sales and stock are unchanged/);
  assert.equal(h.confirmed.length,0);assert.equal(h.button.disabled,false);
  fail=false;await h.upload();
  assert.equal(calls[1].path,calls[0].path);assert.equal(calls[1].options.form.get('revision'),'r1');
  assert.equal(h.el('inventory-upload-errors').hidden,true);
});
test('confirmation error leaves the existing version intact and does not report a successful import',async t=>{
  const h=inventoryHarness(t,async path=>{if(path.endsWith('/confirm'))throw Error('Cannot reach MarginGuard. Retry shortly.');return pending;});
  await h.view.setDataset(ready);await h.upload();await h.el('confirm-inventory-upload').onclick();
  assert.equal(h.confirmed.length,0);assert.equal(h.el('inventory-upload-errors').hidden,false);
  assert.match(h.el('inventory-upload-errors').innerHTML,/retry|Retry/);
  assert.doesNotMatch(h.el('inventory-upload-status').textContent,/Stock snapshot confirmed/);
});
test('clearing an expired Inventory-only session ignores a validation response still in flight',async t=>{
  let finish,started;const requestStarted=new Promise(resolve=>started=resolve);
  const h=inventoryHarness(t,()=>{started();return new Promise(resolve=>finish=resolve);});
  await h.view.setDataset(ready);const uploading=h.upload();await requestStarted;
  h.view.clear();finish(pending);await uploading;
  assert.equal(h.el('inventory-upload-panel').hidden,true);assert.equal(h.el('inventory-upload-report').hidden,true);
  assert.equal(h.confirmed.length,0);
  assert.equal(h.el('confirm-inventory-upload').onclick,undefined);
});
