/* Synthetic UI assumptions only; no real uploaded records. */
'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const Context=require('../static/js/business_context.js');
const base={source_kind:'user_csv',dataset_id:'synthetic-dataset',revision:'stock-v1',series_id:'synthetic-series',forecast_origin:'2024-03-24',currency:'AUD'};
const next={...base,revision:'stock-v2'};
function memory(){const data=new Map();return{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k),get length(){return data.size;},key:i=>[...data.keys()][i],data};}

test('snapshot provenance is stored separately without changing the public read structure',()=>{
  const storage=memory(),drafts=Context.create(storage);
  drafts.save(base,'inventory',{current_stock:'20',safety_stock:'3'},'snapshot');
  assert.equal(drafts.inventorySource(base),'snapshot');
  assert.deepEqual(drafts.read(base),{inventory:{current_stock:'20',safety_stock:'3'},scenarios:{}});
  assert.equal(JSON.parse(storage.getItem(Context.key(base))).inventory_source,'snapshot');
});
test('a subsequent user edit marks a snapshot draft as manual',()=>{
  const drafts=Context.create(memory());
  drafts.save(base,'inventory',{current_stock:'20'},'snapshot');
  drafts.save(base,'inventory',{current_stock:'19'});
  assert.equal(drafts.inventorySource(base),'manual');
  assert.equal(drafts.read(base).inventory.current_stock,'19');
});
test('saving financial inputs preserves the inventory provenance',()=>{
  const drafts=Context.create(memory());
  drafts.save(base,'inventory',{current_stock:'20'},'snapshot');
  drafts.save(base,'scenarios',{order_quantity:'8'});
  assert.equal(drafts.inventorySource(base),'snapshot');
  assert.equal(drafts.read(base).inventory.current_stock,'20');
  assert.equal(drafts.read(base).scenarios.order_quantity,'8');
});
test('legacy and missing drafts conservatively have manual provenance',()=>{
  const storage=memory(),drafts=Context.create(storage);
  assert.equal(drafts.inventorySource(base),'manual');
  storage.setItem(Context.key(base),JSON.stringify({schema:1,inventory:{current_stock:'4'}}));
  assert.equal(drafts.inventorySource(base),'manual');
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),1);
  assert.equal(drafts.read(next).inventory.current_stock,'4');
});
test('stock revision carries only manual inventory inputs and never financial data or results',()=>{
  const storage=memory(),drafts=Context.create(storage);
  drafts.save(base,'inventory',{current_stock:'20',safety_stock:'',hypothetical_stock_at_origin:false,stock_as_of:'2024-03-24',gross_profit:555,csrf_token:'secret'});
  drafts.save(base,'scenarios',{cash_budget:'900',order_quantity:'5'});
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),1);
  assert.deepEqual(drafts.read(next),{inventory:{current_stock:'20',safety_stock:'',stock_as_of:'2024-03-24',hypothetical_stock_at_origin:false},scenarios:{}});
  assert.equal(drafts.inventorySource(next),'manual');
  assert.ok(!storage.getItem(Context.key(next)).includes('secret'));
  assert.equal(drafts.read(base).scenarios.cash_budget,'900');
});
test('automatic snapshot inputs and empty inventory are not carried to the new stock revision',()=>{
  const drafts=Context.create(memory()),empty={...base,series_id:'empty'};
  drafts.save(base,'inventory',{current_stock:'20'},'snapshot');
  drafts.save(empty,'scenarios',{order_quantity:'10'});
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),0);
  assert.deepEqual(drafts.read(next),{});
  assert.deepEqual(drafts.read({...empty,revision:next.revision}),{});
});
test('carrying one dataset and revision leaves other datasets, sources and revisions alone',()=>{
  const storage=memory(),drafts=Context.create(storage);
  const unrelated=[{...base,source_kind:'m5_demo'},{...base,source_kind:'synthetic_demo'},{...base,dataset_id:'other-dataset'},{...base,revision:'unrelated-revision'}];
  drafts.save(base,'inventory',{current_stock:'1'});
  for(const ctx of unrelated)drafts.save(ctx,'inventory',{current_stock:'2'});
  const before=unrelated.map(ctx=>storage.getItem(Context.key(ctx)));
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),1);
  unrelated.forEach((ctx,index)=>assert.equal(storage.getItem(Context.key(ctx)),before[index]));
  for(const ctx of unrelated.slice(0,3))assert.deepEqual(drafts.read({...ctx,revision:next.revision}),{});
});
test('series, forecast date and AUD or USD remain separate when manual drafts carry',()=>{
  const drafts=Context.create(memory());
  const contexts=[base,{...base,series_id:'other-series'},{...base,forecast_origin:'2024-04-01'},{...base,currency:'USD'}];
  contexts.forEach((ctx,index)=>drafts.save(ctx,'inventory',{current_stock:String(index+1)}));
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),4);
  contexts.forEach((ctx,index)=>assert.equal(drafts.read({...ctx,revision:next.revision}).inventory.current_stock,String(index+1)));
});
test('new-version edits are not overwritten when carrying is retried',()=>{
  const drafts=Context.create(memory());
  drafts.save(base,'inventory',{current_stock:'20'});
  drafts.save(next,'inventory',{current_stock:'7'});
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),0);
  assert.equal(drafts.read(next).inventory.current_stock,'7');
});
test('corrupt entries, unsupported schemas and unknown input fields are not carried',()=>{
  const storage=memory(),drafts=Context.create(storage);
  storage.setItem('marginguard.assumptions.v1:bad-json','broken');
  storage.setItem(Context.key(base),JSON.stringify({schema:9,inventory:{current_stock:'10'}}));
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),0);
  storage.setItem(Context.key(base),JSON.stringify({schema:1,inventory:{token:'secret',current_stock:{nested:1}}}));
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),0);
  assert.deepEqual(drafts.read(next),{});
});
test('blocked storage safely disables carrying and provenance lookup without throwing',()=>{
  let warnings=0;const drafts=Context.create({get length(){throw Error('blocked');}},()=>warnings++);
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),0);
  assert.equal(drafts.inventorySource(base),'manual');
  assert.equal(drafts.available(),false);
  assert.equal(warnings,1);
  assert.deepEqual(drafts.read(next),{});
  assert.equal(drafts.save(next,'inventory',{current_stock:'20'},'snapshot'),false);
});
test('failed storage writes do not claim that a manual draft was carried',()=>{
  const storage=memory();let warnings=0;const drafts=Context.create(storage,()=>warnings++);
  drafts.save(base,'inventory',{current_stock:'20'});
  storage.setItem=()=>{throw Error('quota');};
  assert.equal(drafts.carryInventoryDrafts(base.dataset_id,base.revision,next.revision),0);
  assert.equal(drafts.available(),false);
  assert.equal(warnings,1);
});
