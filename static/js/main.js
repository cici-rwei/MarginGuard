/* One UI with separate contexts for M5, synthetic Demo and uploaded records. */
'use strict';
const $=id=>document.getElementById(id),page=document.body.dataset.page;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>v===null||v===undefined?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:2});
const method=v=>v==='moving_average_7'?'7-day Moving Average':'Same-Weekday Average';
const tag=(text,color='neutral')=>`<span class="tag ${color}">${esc(text)}</span>`;
const kpi=(label,value,note='',small=false)=>`<div class="kpi"><div class="kpi-label">${esc(label)}</div><div class="kpi-value ${small?'small':''}">${esc(value)}</div><div class="kpi-note">${esc(note)}</div></div>`;
const table=(headers,rows)=>`<table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
const queryAtStart=new URLSearchParams(location.search),business=queryAtStart.get('mode')==='business';
let catalog=[],state=null,generation=0,calculation=0,controller=null,datasetId=queryAtStart.get('dataset'),revision=null,features=null,synthetic=queryAtStart.get('mode')==='synthetic'||document.body.dataset.demoMode==='synthetic';
const Upload=window.MarginGuardUpload,Context=window.MarginGuardContext;
let storage;try{storage=window.sessionStorage;}catch(error){storage=null;}
function unavailableStorage(){ $('draft-status').textContent='Browser storage is unavailable. You can still analyse manually; inputs will not survive navigation. No results or CSV records are stored in browser storage.'; }
const drafts=Context.create(storage,unavailableStorage);if(!storage)unavailableStorage();
const currency=()=>state?.context?.currency||(synthetic?'AUD':'USD');
const demoApi=kind=>'/api/'+(synthetic?'demo/':'')+kind;
const money=v=>v===null||v===undefined?'—':new Intl.NumberFormat('en-AU',{style:'currency',currency:currency(),currencyDisplay:'code'}).format(Number(v));
async function api(path,body,signal){
  let response;try{response=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal,cache:'no-store'});}
  catch(error){if(error.name==='AbortError')throw error;throw Error(document.body.dataset.public==='true'?'Cannot reach MarginGuard. Please retry shortly.':'Cannot reach the local MarginGuard server. Run ./start.command, then retry.');}
  const data=await response.json().catch(()=>({error:'Server returned an unreadable response.'}));
  if(!response.ok)throw Object.assign(Error(typeof data.error==='string'?data.error:'Request failed.'),{status:response.status,code:data.code});return data;
}
function showError(error){$('error').textContent=error.message||String(error);$('error').hidden=false;$('retry-connection').hidden=false;}
function expired(error){drafts.clearUploads();state=null;generation++;controller?.abort();$('content').hidden=true;showError(Error('Your temporary data is unavailable or expired. Return to Analyse My Business and upload again.'));}
Upload.attach({onExpired:expired,onError:showError,onRemoved:id=>drafts.clearDataset(id),onConfirmed:async data=>{generation++;calculation++;controller?.abort();state=null;$('content').hidden=true;$('loading').hidden=false;datasetId=data.dataset_id;revision=data.revision;if($('upload-panel'))$('upload-panel').hidden=true;notice('');try{await loadBusinessCatalog(data.series?.[0]?.series_id);}catch(error){showError(error);}finally{$('loading').hidden=true;}}});
function riskTone(r){return r.stockout_risk?'red':r.status==='Sufficient Inventory'?'green':'amber';}
function notice(message){$('mode-notice').textContent=message;$('mode-notice').hidden=!message;}
function chart(id,labels,series,bars=false){if(!$(id))return;const W=700,H=245,L=48,R=16,T=20,B=35,colors=['#3568e8','#1baf8e','#e7a041'];const vals=series.flatMap(s=>s.values.filter(v=>v!==null).map(Number));if(!vals.length){$(id).textContent='No feasible financial values to plot.';return;}let low=Math.min(0,...vals),high=Math.max(1,...vals);const y=v=>T+(high-Number(v))/(high-low)*(H-T-B),x=i=>L+(i/(Math.max(1,labels.length-1)))*(W-L-R);let svg='';for(let i=0;i<=4;i++){const value=low+(high-low)*i/4,yy=y(value);svg+=`<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" stroke="#e9eef5"/><text x="${L-8}" y="${yy+4}" text-anchor="end">${num(value)}</text>`;}
if(bars){series[0].values.forEach((v,i)=>{const xx=L+(i+.5)*(W-L-R)/labels.length;if(v!==null){svg+=`<rect x="${xx-43}" y="${Math.min(y(v),y(0))}" width="86" height="${Math.max(1,Math.abs(y(v)-y(0)))}" rx="4" fill="${Number(v)<0?'#d85e69':colors[i%3]}"><title>${esc(labels[i])}: ${money(v)}</title></rect><text x="${xx}" y="${Number(v)>=0?y(v)-7:y(v)+14}" text-anchor="middle">${money(v)}</text>`;}else svg+=`<text x="${xx}" y="${y(0)-10}" text-anchor="middle">Unavailable</text>`;svg+=`<text x="${xx}" y="${H-8}" text-anchor="middle">${esc(labels[i])}</text>`;});}
else{series.forEach((s,j)=>{const color=colors[j%3];svg+=`<polyline points="${s.values.map((v,i)=>`${x(i)},${y(v)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>`;if(labels.length<=28)s.values.forEach((v,i)=>svg+=`<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="${color}"><title>${esc(labels[i])} · ${esc(s.name)}: ${num(v)}</title></circle>`);});[0,Math.floor((labels.length-1)/2),labels.length-1].forEach(i=>svg+=`<text x="${x(i)}" y="${H-8}" text-anchor="${i===0?'start':i===labels.length-1?'end':'middle'}">${esc(labels[i])}</text>`);}
$(id).innerHTML=`<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(series.map(s=>s.name).join(', '))}">${svg}</svg><div class="chart-legend">${series.map((s,i)=>`<span><i class="swatch" style="background:${colors[i%3]}"></i>${esc(s.name)}</span>`).join('')}</div>`;}

function setModeLabels(){
  $('mode-demo').classList.toggle('active',!business);$('mode-business').classList.toggle('active',business);
  $('mode-demo').textContent=synthetic?'Explore Demo · Synthetic':'Explore Demo';
  $('mode-demo').href=synthetic?'/?mode=synthetic':'/';
  (business?$('mode-business'):$('mode-demo')).setAttribute('aria-current','true');
  if(business){
    $('business-data-context').innerHTML='<div class="context-title"><strong>User-uploaded data · Source not independently verified</strong><span class="tag neutral">Temporary browser session</span></div><p>Daily sales come from your CSV. Inventory, costs and purchasing inputs require your review. No business account is connected.</p><p>Forecast dates follow the selected history, not automatically today. Missing days are unknown; no automatic zero filling.</p>';
    $('sidebar-data-source').textContent='User-uploaded business data · anonymous temporary session';
    $('source-tag').textContent='User-uploaded data';
    $('business-footer').innerHTML='<strong>Data transparency</strong> User-uploaded history · Python forecasts · User-reviewed assumptions<p>The source is not independently verified. Historical price/cost references are not future quotations or verified inventory book values. No currency conversion, real purchase order or guaranteed outcome.</p>';
    if($('portfolio-title')){$('portfolio-title').textContent='Selected business series';$('portfolio-note').textContent='Only the selected product-store analysis is shown; use the selectors to review another series.';}
  }else if(synthetic){
    $('business-data-context').innerHTML='<div class="context-title"><strong>Business data: Synthetic Demo · AUD</strong><span class="tag neutral">Fictional business</span></div><p>Sales, historical price and cost references are deliberately synthetic. Inventory, purchasing and supplier settings are editable demonstration assumptions. No real business account is connected.</p><p>The history and forecast use a simulated 2024 period, not today\'s outlook. Python calculates forecasts and financial results from the synthetic history and your assumptions. No currency conversion.</p>';
    $('sidebar-data-source').textContent='Synthetic Demo · AUD · No connected business account';
    $('source-tag').textContent='Synthetic Demo · AUD';
    $('business-footer').innerHTML='<strong>Data transparency</strong> Synthetic sales and price/cost references · Python forecasts · Editable inventory and purchasing assumptions<p>Fictional 2024 demonstration, not real enterprise or Walmart transactions. Forecast dates follow the synthetic history, not today. Educational decision support; no real purchase order or guaranteed outcome.</p>';
    if($('portfolio-title')){$('portfolio-title').textContent='Synthetic Demo product';$('portfolio-note').textContent='Fictional product-store series · a demonstration of the analysis workflow, not real business performance.';}
  }
}
function linkContext(series){
  const query=business?new URLSearchParams({mode:'business',dataset:datasetId,series:series.series_id}):new URLSearchParams({item_id:series.item_id,store_id:series.store_id});
  if(synthetic&&!business)query.set('mode','synthetic');
  history.replaceState(null,'','?'+query);document.querySelectorAll('[data-business-link]').forEach(a=>a.search='?'+query);
}
function selected(){return catalog.find(s=>s.item_id===$('product').value&&s.store_id===$('store').value);}
function stores(preferred){const choices=catalog.filter(s=>s.item_id===$('product').value).map(s=>s.store_id);$('store').innerHTML=choices.map(s=>`<option>${esc(s)}</option>`).join('');if(choices.includes(preferred))$('store').value=preferred;}
function selectSeries(item,store){$('product').value=item;stores(store);load();}
function populateCatalog(preferred){
  if(!catalog.length)throw Error('No confirmed series is available. Confirm at least 42 consecutive known days.');
  $('product').innerHTML=[...new Set(catalog.map(s=>s.item_id))].map(s=>`<option>${esc(s)}</option>`).join('');
  if(preferred)$('product').value=preferred.item_id;stores(preferred?.store_id);
  $('product').disabled=$('store').disabled=false;$('series-selection').hidden=false;
  $('product').onchange=()=>{stores($('store').value);load();};$('store').onchange=load;
}
async function loadBusinessCatalog(preferredId){
  const data=await Upload.request(`/api/business/datasets/${encodeURIComponent(datasetId)}/catalog`);
  revision=data.revision;catalog=data.series;datasetId=data.dataset_id||datasetId;Upload.setActive(datasetId);
  $('business-dataset-actions').hidden=false;$('dataset-status').textContent='Confirmed temporary dataset · '+(data.meta?.currency||'')+' · tax '+(data.meta?.tax_basis||'unspecified')+' · '+(data.meta?.time_zone||'');
  populateCatalog(catalog.find(s=>s.series_id===preferredId));await load();
}
function requestBody(inputs){
  if(business)return {...inputs,series_id:state.context.series_id,revision:state.context.revision,currency:currency()};
  if(synthetic)return {...inputs,item_id:state.item_id,store_id:state.store_id,revision:state.context.revision,currency:currency()};
  return {...inputs,item_id:state.item_id,store_id:state.store_id,currency:currency()};
}
async function calculate(kind,inputs,signal){
  const body=requestBody(inputs);
  return business?Upload.request(`/api/business/datasets/${encodeURIComponent(datasetId)}/${kind}`,{method:'POST',json:body,signal}):api(demoApi(kind),body,signal);
}
async function load(){
  const series=selected();if(!series)return;
  const gen=++generation;calculation++;controller?.abort();controller=new AbortController();state=null;
  $('content').hidden=true;$('loading').hidden=false;$('error').hidden=true;$('retry-connection').hidden=true;linkContext(series);
  try{
    const query=new URLSearchParams(business?{series_id:series.series_id,revision}:{item_id:series.item_id,store_id:series.store_id});
    const data=business?await Upload.request(`/api/business/datasets/${encodeURIComponent(datasetId)}/analysis?${query}`,{signal:controller.signal}):await api(demoApi('analysis')+'?'+query,null,controller.signal);
    if(gen!==generation)return;
    if(!data.context)throw Error('Analysis context is missing. Restart the updated server.');
    if(data.context.source_kind!==(business?'user_csv':synthetic?'synthetic_demo':'m5_demo'))throw Error('Analysis data source does not match the selected mode. Reload this page.');
    if(synthetic&&data.context.currency!=='AUD')throw Error('Synthetic Demo requires an AUD analysis context. Reload this page.');
    if(business&&(data.context.dataset_id!==datasetId||data.context.revision!==revision||data.context.series_id!==series.series_id))throw Error('Analysis context changed. Reload the selected dataset.');
    Context.key(data.context);state=data;
    $('source-tag').textContent=(business?'User-uploaded data':synthetic?'Synthetic Demo':'Walmart M5 Demo')+' · '+currency();
    await populate(gen);if(gen!==generation)return;$('content').hidden=false;
  }catch(error){if(error.name!=='AbortError'&&gen===generation)showError(error);}
  finally{if(gen===generation)$('loading').hidden=true;}
}
async function populate(gen){
  const data=state,analysis=data.analysis,future=analysis.future;
  $('range').textContent=`${analysis.history_start} — ${analysis.history_end} · ${analysis.observations} ${synthetic?'synthetic history':'observed'} days · Forecast ${future[0].date} — ${future[future.length-1].date}`;
  chart('history-chart',data.history.map(r=>r.date),[{name:synthetic?'Synthetic historical units':'Historical actuals',values:data.history.map(r=>r.units)}]);
  chart('future-chart',future.map(r=>r.date),[{name:method(analysis.selected_method),values:future.map(r=>r.prediction)}]);
  if(page==='dashboard'){
    $('overview-kpis').innerHTML=kpi('Historical Sales',num(data.historical_units),'Units · selected history')+kpi('Forecast Demand',num(analysis.total_forecast_demand),'Units · next 14 dataset days')+kpi('Validation MAE',num(analysis.backtest[analysis.selected_method].mae),'Units/day · '+method(analysis.selected_method))+'<div id="overview-risk-kpi"></div>';
    $('portfolio').innerHTML=table(['Product / Store','Category','Historical units','Forecast units','MAE'],(data.overview||[]).map(r=>[`<button class="table-button" data-item="${esc(r.item_id)}" data-store="${esc(r.store_id)}">${esc(r.item_id)} <small> / ${esc(r.store_id)}</small></button>`,esc(r.category||'Not supplied'),num(r.historical_units),num(r.forecast_total),num(r.mae)]));
    $('portfolio').querySelectorAll('button').forEach(b=>b.onclick=()=>selectSeries(b.dataset.item,b.dataset.store));
    const saved=drafts.read(data.context).inventory||{};let risk=Object.keys(saved).length?null:data.inventory;
    let note=Object.keys(saved).length?'Saved inventory assumptions need review.':business?'No inventory assumptions supplied.':'Default hypothetical stock & lead time';
    if(completeInventory(saved)){
      try{const result=await calculate('inventory',saved,controller.signal);if(gen!==generation)return;risk=result;note='Recalculated from this tab’s inventory assumptions.';}
      catch(error){if(error.name==='AbortError')throw error;note='Saved assumptions could not be assessed: '+error.message;}
    }
    if(gen!==generation)return;
    $('overview-risk-kpi').innerHTML=kpi('Inventory Risk · assumption',risk?risk.status:'Not assessed',note,true);
    $('overview-assumptions').textContent=risk?note+' Review inventory and supplier assumptions on Inventory & Risk.':'Inventory has not been assessed. Enter current stock, lead time and inventory policy assumptions; no business inventory is inferred from sales.';
  }
  if(page==='forecasting'){
    $('method-cards').innerHTML=Object.entries(analysis.backtest).map(([m,v])=>kpi(method(m),num(v.mae)+' MAE',m===analysis.selected_method?'Selected · lowest validation error':'Compared on identical holdout',true)).join('')+kpi('Future forecast total',num(analysis.total_forecast_demand),'Units · refitted using selected history');
    const back=analysis.backtest.moving_average_7.daily;
    $('holdout-range').textContent=`${back[0].date} — ${back[back.length-1].date}`;$('future-range').textContent=`${future[0].date} — ${future[future.length-1].date}`;
    chart('backtest-chart',back.map(r=>r.date),[{name:synthetic?'Synthetic held-out units':'Actual',values:back.map(r=>r.actual)},{name:'Moving average',values:back.map(r=>r.prediction)},{name:'Same weekday',values:analysis.backtest.same_weekday_4.daily.map(r=>r.prediction)}]);
    $('forecast-tables').innerHTML='<h3>Historical holdout</h3>'+table(['Date',synthetic?'Synthetic units':'Actual','Moving average','Same weekday'],back.map((r,i)=>[esc(r.date),num(r.actual),num(r.prediction),num(analysis.backtest.same_weekday_4.daily[i].prediction)]))+'<h3>Future predictions</h3>'+table(['Date','Forecast units'],future.map(r=>[esc(r.date),num(r.prediction)]));
  }
  if(page==='inventory'||page==='scenarios')setupForm();
}
const inventoryFields=[['current_stock','Current Stock',1,1000000,'Whole units'],['lead_time_days','Supplier Lead Time',1,365,'Days · receipt at day lead + 1'],['safety_stock','Safety Stock',1,1000000,'Whole units'],['on_order_units','On-order Units',1,1000000,'Arrival date unknown'],['excess_cover_days','Excess Cover Threshold',0.01,3650,'Days · user-defined threshold above zero']];
const scenarioFields=[['current_stock','Current Stock',1,1000000,'Whole units'],['selling_price','Selling Price','any',1000000000,'{currency} / unit · future assumption'],['existing_unit_cost','Existing Inventory Cost','any',1000000000,'{currency} / unit · old stock only'],['unit_purchase_cost','New Purchase Cost','any',1000000000,'{currency} / unit · new stock only'],['order_quantity','Order Quantity',1,1000000,'Whole units · proposed, not globally optimal'],['freight','Freight Cost','any',1000000000,'{currency} / order'],['other_costs','Other Procurement Costs','any',1000000000,'{currency} / order'],['moq','MOQ',1,1000000,'Minimum units for a positive order'],['lead_time_days','Supplier Lead Time',1,365,'Days · 7 means arrival on day 8'],['discount_percent','Discount Percentage','any',100,'Percent · 0–100'],['demand_uplift_percent','Assumed Demand Uplift','any',500,'Percent · hypothetical response'],['cash_budget','Procurement Budget','any',1000000000000000,'{currency} · incremental purchase cash'],['max_unmet_units','Maximum Unmet Demand','any',84000000,'Optional service constraint · units'],['on_order_units','Existing On-order Units',1,1000000,'Not supported by this scenario engine; 0 means none']];
function completeInventory(values){
  return inventoryFields.every(([name])=>values[name]!==undefined&&values[name]!==null&&values[name]!=='')&&(!business||values.hypothetical_stock_at_origin===true||values.stock_as_of===state.context.forecast_origin);
}
function formInputs(form){
  const values=Object.fromEntries(new FormData(form));
  form.querySelectorAll('input[type=checkbox]').forEach(input=>values[input.name]=input.checked);
  if(values.max_unmet_units==='')values.max_unmet_units=null;
  if(!business){values.hypothetical_stock_at_origin=true;delete values.stock_as_of;}
  return values;
}
function fill(form,values){Object.entries(values).forEach(([key,value])=>{const input=form.elements.namedItem(key);if(input){if(input.type==='checkbox')input.checked=value===true;else input.value=value??'';}});}
function timingRules(form){
  const hypothetical=form.elements.namedItem('hypothetical_stock_at_origin'),asOf=form.elements.namedItem('stock_as_of');
  if(hypothetical&&asOf){asOf.required=!hypothetical.checked;asOf.disabled=hypothetical.checked;}
  const outstanding=form.elements.namedItem('on_order_units'),ack=form.elements.namedItem('acknowledge_excluded_on_order');
  if(ack){const hasOrder=Number(outstanding.value)>0;ack.required=hasOrder;$('on-order-warning').hidden=!hasOrder;if(!hasOrder)ack.checked=false;}
}
function setupForm(){
  const inventory=page==='inventory',kind=inventory?'inventory':'scenarios',form=$(inventory?'inventory-form':'scenario-form'),fields=inventory?inventoryFields:scenarioFields;
  const gen=generation,context=state.context;
  $(inventory?'inventory-fields':'scenario-fields').innerHTML=fields.map(([name,label,step,max,hint])=>`<div class="field"><label for="${name}">${label}</label><input type="number" id="${name}" name="${name}" step="${step}" min="${name==='excess_cover_days'?'.01':'0'}" max="${max}" ${name==='max_unmet_units'?'':'required'}><small>${esc(hint.replaceAll('{currency}',currency()))}</small></div>`).join('')+(business?`<div class="field"><label for="stock_as_of">Stock as of (close of day)</label><input id="stock_as_of" name="stock_as_of" type="date" required><small>Must match forecast origin ${esc(context.forecast_origin)}.</small></div><label class="check-row"><input type="checkbox" name="hypothetical_stock_at_origin" id="hypothetical_stock_at_origin">Use explicitly hypothetical stock at ${esc(context.forecast_origin)} instead of a reported snapshot.</label>`:'')+(!inventory?'<label id="on-order-warning" class="check-row warning" hidden><input type="checkbox" name="acknowledge_excluded_on_order" id="acknowledge_excluded_on_order">I am creating a separate scenario that excludes existing on-order stock and its costs. It does not represent the complete inventory situation.</label>':'');
  form.querySelectorAll('button').forEach(b=>b.disabled=false);
  const restoreDefaults=()=>{fields.forEach(([name])=>form.elements[name].value=business?'':(state.defaults[name]??''));if(business){form.elements.stock_as_of.value='';form.elements.hypothetical_stock_at_origin.checked=false;}if(!inventory)form.elements.acknowledge_excluded_on_order.checked=false;timingRules(form);};
  restoreDefaults();const saved=drafts.read(context)[kind]||{};fill(form,saved);timingRules(form);
  const results=$(inventory?'inventory-results':'scenario-results');results.hidden=true;
  form.querySelector('.form-status').textContent=Object.keys(saved).length?'Draft restored · Python recalculation required':business?'Enter your assumptions · no Demo defaults':'Ready · disclosed Demo assumptions';
  function changed(){calculation++;results.hidden=true;timingRules(form);drafts.save(context,kind,formInputs(form));form.querySelector('.form-status').textContent='Inputs changed · run again to update results';}
  form.oninput=changed;form.onchange=changed;
  form.querySelector('.reset').onclick=()=>{calculation++;drafts.clear(context);restoreDefaults();results.hidden=true;$('error').hidden=true;$('retry-connection').hidden=true;form.querySelector('.form-status').textContent=business?'Current context cleared · enter assumptions':'Current context cleared · disclosed Demo assumptions restored';if(!inventory)setupHandoff(form,changed);};
  form.onsubmit=async event=>{
    event.preventDefault();timingRules(form);if(!form.reportValidity())return;
    const values=formInputs(form),token=++calculation;drafts.save(context,kind,values);
    $('error').hidden=true;$('retry-connection').hidden=true;results.hidden=true;
    const buttons=form.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);form.querySelectorAll('input').forEach(i=>i.readOnly=true);form.querySelector('.form-status').textContent='Calculating in Python…';
    try{const result=await calculate(kind,values,controller.signal);if(gen!==generation||token!==calculation)return;inventory?renderInventory(result):renderScenarios(result);form.querySelector('.form-status').textContent='Updated · user assumptions · Python calculation complete';}
    catch(error){if(error.name!=='AbortError'&&gen===generation&&token===calculation){showError(error);form.querySelector('.form-status').textContent='Calculation failed · review inputs';}}
    finally{if(gen===generation){buttons.forEach(b=>b.disabled=false);form.querySelectorAll('input').forEach(i=>i.readOnly=false);}}
  };
  if(!inventory){$('scenario-currency').textContent='14 days · '+currency();setupReferences(form,changed);setupHandoff(form,changed);}
  if(Object.keys(saved).length&&form.checkValidity())setTimeout(()=>{if(gen===generation)form.requestSubmit();},0);
}
function setupReferences(form,changed){
  const price=state.price_reference||(state.price!==null&&state.price!==undefined?{date:state.price_date,value:state.price}:null),cost=state.cost_reference;
  $('price-note').textContent=price?`${synthetic?'Synthetic historical':'Historical'} price: ${money(price.value)} on ${price.date}. Its use as a future price is an assumption.`:'No observed price available. Enter an explicit assumed selling price.';
  const box=$('historical-references');box.hidden=!(price||cost);
  box.innerHTML=`<strong>Optional ${synthetic?'synthetic ':''}historical references</strong><p>${synthetic?'These price and cost values are fictional. ':''}Use references only after checking their meaning. Historical unit cost is not automatically current inventory book cost or a new supplier quotation.</p>`+(price?`<button type="button" class="secondary" id="use-price-reference">Use ${esc(money(price.value))} (${esc(price.date)}) as future price</button>`:'')+(cost?`<p>${synthetic?'Synthetic historical':'Historical'} cost ${esc(money(cost.value))} on ${esc(cost.date)}. Review each assumption separately.</p><button type="button" class="secondary" id="use-old-cost-reference">Use reference as existing inventory cost</button><button type="button" class="secondary" id="use-new-cost-reference">Use reference as new purchase cost</button>`:'');
  if(price)$('use-price-reference').onclick=()=>{form.elements.selling_price.value=price.value;changed();};
  if(cost){$('use-old-cost-reference').onclick=()=>{form.elements.existing_unit_cost.value=cost.value;changed();};$('use-new-cost-reference').onclick=()=>{form.elements.unit_purchase_cost.value=cost.value;changed();};}
}
function setupHandoff(form,changed){
  const inputs=drafts.read(state.context).inventory||{},box=$('inventory-handoff');box.hidden=!Object.keys(inputs).length;if(box.hidden)return;
  const blocked=Number(inputs.on_order_units)>0,complete=completeInventory(inputs),gen=generation;
  $('handoff-note').textContent=blocked?'Existing on-order units are not supported in the financial model. Automatic transfer is disabled; create and acknowledge a separate manual scenario if appropriate.':complete?'Review saved inventory inputs before replacing any current financial inputs. Suggested quantity is recalculated in Python.':'The inventory draft is incomplete. Complete and calculate Inventory & Risk first.';
  $('use-inventory-assumptions').disabled=$('use-suggested-quantity').disabled=blocked||!complete;$('handoff-confirm').hidden=true;
  const preview=values=>{if(gen!==generation)return;$('handoff-preview').textContent='Replace these current inputs with reviewed inventory values: '+Object.entries(values).map(([k,v])=>k+' = '+v).join(', ')+'. Zero procurement may require manually resetting freight and other charges.';$('handoff-confirm').hidden=false;$('confirm-handoff').onclick=()=>{fill(form,values);changed();$('handoff-confirm').hidden=true;};};
  $('use-inventory-assumptions').onclick=()=>preview(Object.fromEntries(['current_stock','lead_time_days','stock_as_of','hypothetical_stock_at_origin'].filter(k=>inputs[k]!==undefined).map(k=>[k,inputs[k]])));
  $('use-suggested-quantity').onclick=async()=>{try{const result=await calculate('inventory',inputs,controller.signal);preview({order_quantity:result.suggested_reorder_quantity});}catch(error){if(error.name!=='AbortError')showError(error);}};
  $('cancel-handoff').onclick=()=>$('handoff-confirm').hidden=true;
}
function renderInventory(result){
  $('inventory-results').hidden=false;$('risk-banner').innerHTML=`<div class="alert ${result.stockout_risk?'danger':result.status==='Sufficient Inventory'?'success':'warning'}"><h2>${esc(result.status)}</h2><p>${esc(result.explanation)}</p></div>`;
  $('inventory-kpis').innerHTML=kpi('Days of Cover',result.days_of_cover===null?'No demand':num(result.days_of_cover),'Current stock / average demand')+kpi('Lead-Time Demand',num(result.lead_time_demand),result.extrapolated?'Includes extrapolation beyond day 14':'Sum of daily forecast values')+kpi('Proposed Order Quantity',num(result.suggested_reorder_quantity),'Inventory-rule estimate; review costs and constraints')+kpi('Inventory Position',num(result.inventory_position),'Current + on-order units');
  $('inventory-notes').innerHTML=`<p>Stockout risk: <strong>${result.stockout_risk?'Yes':'No'}</strong> · Excess inventory warning: <strong>${result.excess_inventory_warning?'Yes':'No'}</strong></p><p>Target position: ${num(result.target_inventory_position)} units. Average daily demand: ${num(result.average_daily_demand)} units. User excess threshold: ${num(result.excess_cover_days)} days.</p><p>${esc(result.on_order_policy)}</p>${result.extrapolated?`<p>${esc(result.extension_rule)} This is an extrapolation.</p>`:''}`;
}
function renderScenarios(result){
  if(result.currency!==currency())throw Error('Result currency conflicts with the current dataset.');
  $('scenario-results').hidden=false;$('recommendation').innerHTML=`<div class="alert ${result.recommendation?'success':'warning'}"><h2>${result.recommendation?'Recommended: '+esc(result.recommendation):'No feasible strategy'}</h2><p>${esc(result.recommendation_reason)}</p></div>`;
  $('scenario-table').innerHTML=table(['Strategy','Revenue','Gross Profit','Gross Margin','Unmet Demand','Ending Inventory','Procurement Cash','Feasibility'],result.strategies.map(s=>[esc(s.strategy)+(s.strategy===result.recommendation?' '+tag('Recommended','blue'):''),money(s.revenue),`<strong class="${s.gross_profit===null?'':Number(s.gross_profit)>=0?'positive':'negative'}">${money(s.gross_profit)}</strong>`,s.gross_margin===null?'—':num(s.gross_margin)+'%',num(s.unmet_demand),num(s.ending_inventory),money(s.procurement_cash_outlay),tag(s.feasibility_status,s.feasible?'green':'red')]));
  chart('profit-chart',result.strategies.map(s=>s.strategy),[{name:`Gross profit (${currency()}); infeasible outcomes are not recommendations`,values:result.strategies.map(s=>s.gross_profit)}],true);
  $('tradeoffs').innerHTML=result.strategies.map(s=>`<div class="tradeoff"><strong>${esc(s.strategy)}</strong> ${tag(s.feasibility_status,s.feasible?'green':'red')}<p>${s.reasons.length?esc(s.reasons.join(' ')):`${num(s.unmet_demand)} unmet units · ${money(s.procurement_cash_outlay)} incremental cash · ${num(s.ending_inventory)} ending units.`}</p>${s.receipt_day?`<p>Receipt: day ${s.receipt_day}. Sold before / after receipt: ${num(s.sales_before_receipt)} / ${num(s.sales_after_receipt)}. In transit at end: ${num(s.in_transit_units)} units.</p>`:''}</div>`).join('');
  $('scenario-audit').innerHTML=result.strategies.map(s=>`<h3>${esc(s.strategy)}</h3>${s.daily.length?`<p>Existing COGS: ${money(s.existing_cogs)} · New COGS: ${money(s.new_cogs)} · New unit landed cost: ${money(s.unit_landed_cost)}. Potential lost revenue: ${money(s.potential_lost_revenue)}; potential lost gross profit: ${money(s.potential_lost_gross_profit)}.</p>`+table(['Day','Demand','Received','Sold','Unmet','Ending stock'],s.daily.map(d=>[d.day,num(d.demand),num(d.received_units),num(d.units_sold),num(d.unmet_demand),num(d.ending_inventory)])):`<p>${esc(s.reasons.join(' '))}</p>`}`).join('');
  const winner=result.strategies.find(s=>s.strategy===result.recommendation);
  $('decision-summary').innerHTML='<h2>Purchasing Decision Summary</h2>'+`<p>${esc(state.item_id)} / ${esc(state.store_id)} · ${esc(state.analysis.future[0].date)} — ${esc(state.analysis.future[state.analysis.future.length-1].date)} · ${currency()} · user-reviewed assumptions</p>`+
    (winner?`<div class="kpis">${kpi('Recommended strategy',winner.strategy,'Best feasible of the three tested strategies',true)}${kpi('Base 14-day forecast',num(state.analysis.total_forecast_demand),'Units · before any hypothetical discount uplift')}${kpi('Expected revenue',money(winner.revenue),currency(),true)}${kpi('Expected gross profit',money(winner.gross_profit),'COGS differs from purchase cash',true)}${kpi('Procurement cash',money(winner.procurement_cash_outlay),'Incremental new purchase cash',true)}${kpi('Unmet demand',num(winner.unmet_demand),'Units · selected strategy')}${kpi('Ending inventory',num(winner.ending_inventory),'Units · selected strategy')}${kpi('Budget / MOQ',`${winner.budget_satisfied===false?'Budget failed':winner.budget_satisfied===true?'Budget met':'See feasibility'} / ${winner.moq_satisfied?'MOQ met':'MOQ failed'}`,'Based on Python constraint checks',true)}</div>`:'<p>No feasible recommendation. Review the constraints and comparison table.</p>')+
    `<p>${esc(result.recommendation_reason)}</p><p>Trade-offs are shown for all three strategies below. This compares your tested quantities and assumptions; it is not a globally optimal purchasing plan and does not create a purchase order.</p><p>${esc(result.limitations||'')}</p>`;
}
(async()=>{
  setModeLabels();
  try{
    features=await api('/api/features');
    synthetic=!business&&(synthetic||(!features.demo_enabled&&features.synthetic_demo_enabled===true));
    setModeLabels();
    if(business){
      $('upload-panel')&&($('upload-panel').hidden=!features.upload_enabled);$('series-selection').hidden=true;
      if(!features.upload_enabled){notice('Analyse My Business is disabled in this environment pending security acceptance. Explore the available Demo or Market Intelligence.');$('loading').hidden=true;return;}
      const session=await Upload.getSession();
      if(!session.active_dataset)drafts.clearUploads();
      datasetId=datasetId||session.active_dataset?.dataset_id;
      if(datasetId){await loadBusinessCatalog(queryAtStart.get('series'));if($('upload-panel')&&queryAtStart.get('upload')!=='1')$('upload-panel').hidden=true;}
      else if(page!=='dashboard')location.replace('/?mode=business');
      else{$('loading').hidden=true;notice('Upload and confirm your daily history to begin. No business KPIs are displayed before analysis.');}
    }else{
      if(synthetic&&!features.synthetic_demo_enabled){$('series-selection').hidden=true;$('loading').hidden=true;notice('Synthetic Demo is not enabled in this environment. Select an available data mode or Market Intelligence.');return;}
      if(!synthetic&&!features.demo_enabled){$('series-selection').hidden=true;$('loading').hidden=true;notice('Walmart M5 Demo is not available in this deployment until display and redistribution permissions are confirmed. Market Intelligence remains independent.');return;}
      catalog=(await api(demoApi('catalog'))).series;populateCatalog(catalog.find(s=>s.item_id===queryAtStart.get('item_id')&&s.store_id===queryAtStart.get('store_id')));await load();
    }
  }catch(error){$('loading').hidden=true;showError(error);}
})();
$('retry-connection').onclick=()=>location.reload();
