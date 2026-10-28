/* Presentation and consent tests. All records and assumptions here are synthetic. */
'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const Context=require('../static/js/business_context.js');
const root=require('node:path').join(__dirname,'..');
function pageHarness(){
  const nodes=new Map();
  const element=id=>{if(!nodes.has(id))nodes.set(id,{id,innerHTML:'',textContent:'',hidden:false,classList:{toggle(){}},setAttribute(){}});return nodes.get(id);};
  const storage={getItem:()=>null,setItem(){},removeItem(){},length:0};
  const sandbox={URLSearchParams,Intl,console,document:{body:{dataset:{page:'scenarios',demoMode:'synthetic'}},getElementById:element},location:{search:'?mode=synthetic'},window:{MarginGuardContext:Context,MarginGuardUpload:{attach(){}},sessionStorage:storage}};
  vm.createContext(sandbox);
  const source=fs.readFileSync(root+'/static/js/main.js','utf8');
  // Load presentation functions only. The network bootstrap is exercised by browser UAT.
  vm.runInContext(source.slice(0,source.indexOf('(async()=>{')),sandbox);
  vm.runInContext("state={item_id:'SYNTHETIC_TEST_PRODUCT',store_id:'SYNTHETIC_TEST_STORE',context:{currency:'AUD'},analysis:{future:[{date:'2024-03-25'},{date:'2024-04-07'}],total_forecast_demand:'84'}}",sandbox);
  return {sandbox,element};
}
function strategy(name,patch={}){return{strategy:name,feasible:true,feasibility_status:'Feasible',revenue:'1218.00',gross_profit:'556.20',gross_margin:'45.67',unmet_demand:'0',ending_inventory:'6',procurement_cash_outlay:'462.00',budget_satisfied:true,moq_satisfied:true,reasons:[],daily:[],...patch};}
function result(rows){return{currency:'AUD',cash_budget:'500.00',recommendation:'Reorder',recommendation_reason:'Synthetic test-only engine reason',strategies:rows,limitations:'Hypothetical assumptions; lost sales are not backlogged.'};}

test('backend field errors have business names and corrective guidance',()=>{
  const message=Context.friendlyError({message:'current_stock must be a whole number.'});
  assert.match(message,/Current stock/);assert.match(message,/Correct this input/);assert.doesNotMatch(message,/current_stock/);
  assert.equal(Context.fieldLabel('hypothetical_stock_at_origin'),'Hypothetical stock at forecast start');
});
test('file, security and capacity errors tell the user what to do without private internals',()=>{
  for(const code of ['file_too_large','csrf_rejected','processing_timeout','storage_capacity']){
    const message=Context.friendlyError({code,message:'/private/path confidential internal detail'});
    assert.doesNotMatch(message,/private\/path|confidential/);assert.match(message,/choose|reload|try|retry/i);
  }
  assert.doesNotMatch(Context.friendlyError({status:503,message:'/private/path'}),/private\/path/);
});
test('assumption review shows the old and new business values without mutating drafts',()=>{
  const current={current_stock:'30',lead_time_days:'7',hypothetical_stock_at_origin:false,selling_price:'20'},incoming={current_stock:'5',lead_time_days:3,hypothetical_stock_at_origin:true};
  const original=JSON.stringify(current),changes=Context.assumptionChanges(current,incoming);
  assert.deepEqual(changes.map(v=>[v.label,v.before,v.after]),[['Current stock','30 units','5 units'],['Supplier delivery time','7 days','3 days'],['Hypothetical stock at forecast start','No','Yes']]);
  assert.equal(JSON.stringify(current),original);assert.equal(current.selling_price,'20');
});
test('numeric equivalent inputs do not create a false unsynchronised warning',()=>{
  assert.deepEqual(Context.assumptionChanges({current_stock:'30.0',lead_time_days:'3'},{current_stock:30,lead_time_days:3}),[]);
});
test('missing values are not treated as zero and Boolean confirmations stay explicit',()=>{
  const changes=Context.assumptionChanges({current_stock:'',hypothetical_stock_at_origin:false},{current_stock:0,hypothetical_stock_at_origin:true});
  assert.equal(changes[0].before,'Not entered');assert.equal(changes[0].after,'0 units');assert.equal(changes[1].after,'Yes');
});
test('mobile cards retain every backend financial value and only mark the recommended strategy',()=>{
  const {sandbox,element}=pageHarness(),rows=[strategy('Wait',{revenue:'435.00',gross_profit:'189.00',procurement_cash_outlay:'0.00'}),strategy('Reorder'),strategy('Discount',{revenue:'391.50',gross_profit:'145.50',gross_margin:'37.16',procurement_cash_outlay:'0.00'})];
  sandbox.fixture=result(rows);sandbox.assumptions={moq:'20'};vm.runInContext('renderScenarios(fixture,assumptions)',sandbox);
  const cards=element('scenario-cards').innerHTML;
  assert.equal((cards.match(/<article /g)||[]).length,3);assert.equal((cards.match(/is-recommended/g)||[]).length,1);
  for(const value of ['435.00','189.00','1,218.00','556.20','462.00','391.50','145.50','37.16%'])assert.ok(cards.includes(value),value);
  for(const label of ['Revenue','Gross Profit','Procurement Cash','Unmet Demand','Feasibility','Purchase budget','Minimum order quantity'])assert.ok(cards.includes(label),label);
  assert.ok(element('scenario-table').innerHTML.includes('556.20'));
});
test('a below-minimum order card preserves unavailable results and the corrective reason',()=>{
  const {sandbox,element}=pageHarness();
  sandbox.fixture={...result([strategy('Reorder',{feasible:false,revenue:null,gross_profit:null,gross_margin:null,unmet_demand:null,ending_inventory:null,procurement_cash_outlay:null,budget_satisfied:null,moq_satisfied:false,reasons:['Order quantity is below MOQ.']})]),recommendation:null};
  sandbox.assumptions={moq:'20'};vm.runInContext('renderScenarios(fixture,assumptions)',sandbox);
  const cards=element('scenario-cards').innerHTML;assert.match(cards,/Not feasible/);assert.match(cards,/minimum order quantity/);assert.match(cards,/Increase it to the minimum/);assert.match(cards,/Not assessed/);assert.match(cards,/—/);assert.doesNotMatch(cards,/is-recommended/);
});
test('over-budget card still shows financial outcomes, failed constraint and an actionable reason',()=>{
  const {sandbox,element}=pageHarness();sandbox.fixture={...result([strategy('Reorder',{feasible:false,budget_satisfied:false,procurement_cash_outlay:'612.00',reasons:['Procurement cash exceeds budget.']})]),recommendation:null};sandbox.assumptions={moq:'20'};
  vm.runInContext('renderScenarios(fixture,assumptions)',sandbox);
  const cards=element('scenario-cards').innerHTML;assert.match(cards,/612.00/);assert.match(cards,/Over budget/);assert.match(cards,/Reduce the order/);assert.doesNotMatch(cards,/is-recommended/);
});
test('inventory output retains Python values and separates full-horizon demand from sufficient status',()=>{
  const {sandbox,element}=pageHarness();sandbox.risk={status:'Sufficient Inventory',stockout_risk:false,explanation:'Inventory position meets the lead-time demand plus safety-stock target.',days_of_cover:'5',lead_time_demand:'10',suggested_reorder_quantity:0,inventory_position:30,target_inventory_position:20,average_daily_demand:6,excess_cover_days:30,on_order_policy:'Synthetic fixture',excess_inventory_warning:false};sandbox.assumptions={current_stock:'30',lead_time_days:'3',safety_stock:'10'};
  vm.runInContext('renderInventory(risk,assumptions)',sandbox);
  assert.match(element('risk-banner').innerHTML,/does not mean current stock covers all 14/);
  const coverage=element('inventory-coverage').innerHTML;for(const text of ['30 units','10 units','84 units','Full 14-day forecast demand'])assert.ok(coverage.includes(text),text);
});
test('disabled upload entry stays explicit and recovers when the feature is enabled',()=>{
  const {sandbox,element}=pageHarness();vm.runInContext('features={upload_enabled:false};setModeLabels()',sandbox);assert.match(element('mode-business').textContent,/Temporarily unavailable/);
  vm.runInContext('features={upload_enabled:true};setModeLabels()',sandbox);assert.equal(element('mode-business').textContent,'Analyse My Business');assert.equal(element('upload-availability').hidden,true);
});
