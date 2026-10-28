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
function showError(error){$('error').textContent=Context.friendlyError(error);$('error').hidden=false;$('retry-connection').hidden=false;}
function expired(error){drafts.clearUploads();state=null;generation++;controller?.abort();$('content').hidden=true;showError(Error('Your temporary data is unavailable or expired. Return to Analyse My Business and upload again.'));}
Upload.attach({onExpired:expired,onError:showError,onRemoved:id=>drafts.clearDataset(id),onConfirmed:async data=>{generation++;calculation++;controller?.abort();state=null;$('content').hidden=true;$('loading').hidden=false;datasetId=data.dataset_id;revision=data.revision;if($('upload-panel'))$('upload-panel').hidden=true;notice('');try{await loadBusinessCatalog(data.series?.[0]?.series_id);}catch(error){showError(error);}finally{$('loading').hidden=true;}}});
function riskTone(r){return r.stockout_risk?'red':r.status==='Sufficient Inventory'?'green':'amber';}
function riskLabel(r){return r.status==='Sufficient Inventory'?'Sufficient for delivery-time demand and backup stock':r.status==='Reorder Attention'?'Backup stock needs attention':r.status==='Stockout Risk'?'Stock may run out before delivery':r.status==='Excess Inventory Attention'?'Possible excess stock':Context.businessText(r.status);}
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
  if(features){$('mode-business').classList.toggle('mode-unavailable',!features.upload_enabled);if($('upload-availability'))$('upload-availability').hidden=features.upload_enabled;$('mode-business').textContent=features.upload_enabled?'Analyse My Business':'Analyse My Business · Temporarily unavailable';$('mode-business').setAttribute('aria-label',features.upload_enabled?'Analyse My Business':'Analyse My Business · Temporarily unavailable. Use Synthetic Demo for now.');}
  if(business){
    $('business-data-context').innerHTML='<div class="context-title"><strong>Your uploaded sales</strong><span class="tag neutral">Temporary session</span></div><p>Review your inventory and purchasing assumptions before making decisions.</p><details class="source-details"><summary>Data source, dates and assumptions</summary><p>Daily sales come from your CSV; the source is not independently verified. No business account is connected. Forecasts start after your selected history, not automatically today. Missing days are unknown and are not filled with zero.</p><p>Prices, costs and stock require your review. Temporary uploads may disappear after expiry or a server restart; keep your original CSV. No currency conversion.</p></details>';
    $('sidebar-data-source').textContent='User-uploaded business data · anonymous temporary session';
    $('source-tag').textContent='User-uploaded data';
    $('business-footer').innerHTML='<strong>Data transparency</strong> User-uploaded history · Python forecasts · User-reviewed assumptions<p>The source is not independently verified. Historical price/cost references are not future quotations or verified inventory book values. No currency conversion, real purchase order or guaranteed outcome.</p>';
    if($('portfolio-title')){$('portfolio-title').textContent='Selected business series';$('portfolio-note').textContent='Only the selected product-store analysis is shown; use the selectors to review another series.';}
  }else if(synthetic){
    $('business-data-context').innerHTML='<div class="context-title"><strong>Business data: Synthetic Demo · AUD</strong><span class="tag neutral">Fictional business</span></div><p>Try a fictional 2024 sales history with editable inventory and purchasing assumptions.</p><details class="source-details"><summary>Data source, dates and assumptions</summary><p>Sales and historical price/cost references are deliberately synthetic. No real business account is connected. Forecast dates follow this simulated history, not today. Existing Python models calculate results from the history and your assumptions; there is no currency conversion or real purchase order.</p><p>This synthetic dataset follows a repeating weekly pattern. A zero validation MAE does not imply perfect accuracy on real business data.</p></details>';
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
  $('business-dataset-actions').hidden=false;$('dataset-status').textContent='Confirmed temporary dataset · '+(data.meta?.currency||'')+' · '+({'exclusive':'Tax excluded','inclusive':'Tax included'}[data.meta?.tax_basis]||'Tax treatment unspecified')+' · '+(data.meta?.time_zone||'');
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
    if(!data.context)throw Error('Your selected data could not be loaded. Reload this page and select the product and store again.');
    if(data.context.source_kind!==(business?'user_csv':synthetic?'synthetic_demo':'m5_demo'))throw Error('These results do not belong to your selected data source. Reload this page and choose your data again.');
    if(synthetic&&data.context.currency!=='AUD')throw Error('Synthetic Demo uses AUD. Reload this page to restore the matching data and currency.');
    if(business&&(data.context.dataset_id!==datasetId||data.context.revision!==revision||data.context.series_id!==series.series_id))throw Error('Your selected sales data changed. Reload this page and choose the current product and store.');
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
    $('overview-kpis').innerHTML=kpi('Historical Sales',num(data.historical_units),'Units · selected history')+kpi('Forecast Demand',num(analysis.total_forecast_demand),'Units · next 14 dataset days')+kpi('Average Forecast Error',num(analysis.backtest[analysis.selected_method].mae),'MAE · units/day · '+method(analysis.selected_method))+'<div id="overview-risk-kpi"></div>';
    $('portfolio').innerHTML=table(['Product / Store','Category','Historical units','Forecast units','Average error (MAE)'],(data.overview||[]).map(r=>[`<button class="table-button" data-item="${esc(r.item_id)}" data-store="${esc(r.store_id)}">${esc(r.item_id)} <small> / ${esc(r.store_id)}</small></button>`,esc(r.category||'Not supplied'),num(r.historical_units),num(r.forecast_total),num(r.mae)]));
    $('portfolio').querySelectorAll('button').forEach(b=>b.onclick=()=>selectSeries(b.dataset.item,b.dataset.store));
    const saved=drafts.read(data.context).inventory||{};let risk=Object.keys(saved).length?null:data.inventory;
    let note=Object.keys(saved).length?'Saved inventory assumptions need review.':business?'No inventory assumptions supplied.':'Demo assumptions for stock and supplier delivery time';
    if(completeInventory(saved)){
      try{const result=await calculate('inventory',saved,controller.signal);if(gen!==generation)return;risk=result;note='Recalculated from this tab’s inventory assumptions.';}
      catch(error){if(error.name==='AbortError')throw error;note='Saved assumptions could not be assessed: '+Context.friendlyError(error);}
    }
    if(gen!==generation)return;
    $('overview-risk-kpi').innerHTML=kpi('Inventory Risk · assumption',risk?riskLabel(risk):'Not assessed',note,true);
    $('overview-assumptions').textContent=risk?note+' Review inventory and supplier assumptions on Inventory & Risk.':'Inventory has not been assessed. Enter your stock count, supplier delivery time and backup stock target. Sales records do not tell us your current inventory.';
  }
  if(page==='forecasting'){
    $('method-cards').innerHTML=Object.entries(analysis.backtest).map(([m,v])=>kpi(method(m),num(v.mae)+' units/day',m===analysis.selected_method?'Average forecast error (MAE) · lowest in the historical check':'Average forecast error (MAE) · same historical check',true)).join('')+kpi('Future forecast total',num(analysis.total_forecast_demand),'Units · refitted using selected history');
    const back=analysis.backtest.moving_average_7.daily;
    $('holdout-range').textContent=`${back[0].date} — ${back[back.length-1].date}`;$('future-range').textContent=`${future[0].date} — ${future[future.length-1].date}`;
    chart('backtest-chart',back.map(r=>r.date),[{name:synthetic?'Synthetic held-out units':'Actual',values:back.map(r=>r.actual)},{name:'Moving average',values:back.map(r=>r.prediction)},{name:'Same weekday',values:analysis.backtest.same_weekday_4.daily.map(r=>r.prediction)}]);
    $('forecast-tables').innerHTML='<h3>Historical holdout</h3>'+table(['Date',synthetic?'Synthetic units':'Actual','Moving average','Same weekday'],back.map((r,i)=>[esc(r.date),num(r.actual),num(r.prediction),num(analysis.backtest.same_weekday_4.daily[i].prediction)]))+'<h3>Future predictions</h3>'+table(['Date','Forecast units'],future.map(r=>[esc(r.date),num(r.prediction)]));
  }
  if(page==='inventory'||page==='scenarios')setupForm();
}
const inventoryFields=[
  ['current_stock','Current Stock',1,1000000,'Units available at the forecast start. Do not include orders still in transit.'],
  ['lead_time_days','Supplier Delivery Time',1,365,'Whole days until stock is available. Enter 7 for delivery on forecast day 8.'],
  ['safety_stock','Backup Stock',1,1000000,'Extra units you want to keep beyond expected demand while waiting for delivery.'],
  ['on_order_units','Stock Already Ordered',1,1000000,'Whole units ordered but not received. Arrival dates are not known to this model.'],
  ['excess_cover_days','Excess Stock Warning After',0.01,3650,'Days of stock cover above which you want a warning. Choose a value above zero.']
];
const scenarioFields=[
  ['current_stock','Current Stock',1,1000000,'Units available at the forecast start; excludes stock still in transit.'],
  ['selling_price','Selling Price','any',1000000000,'{currency} per unit, before the discount in the Discount strategy.'],
  ['existing_unit_cost','Cost of Stock Already Held','any',1000000000,'{currency} per unit of current stock. Used only when those units are sold.'],
  ['unit_purchase_cost','New Supplier Unit Cost','any',1000000000,'{currency} per unit in the new order, before delivery and other purchase charges.'],
  ['order_quantity','New Order Quantity',1,1000000,'Whole units to buy in Reorder. Other strategies do not place this order.'],
  ['freight','Delivery Charge','any',1000000000,'{currency} for the entire new order. Enter 0 if no charge applies.'],
  ['other_costs','Other Purchase Charges','any',1000000000,'{currency} for the entire new order, excluding the delivery charge.'],
  ['moq','Minimum Order Quantity',1,1000000,'Minimum units your supplier accepts for a positive order; 0 means no minimum.'],
  ['lead_time_days','Supplier Delivery Time',1,365,'Whole days to delivery. Enter 7 for arrival on day 8; new stock cannot sell earlier.'],
  ['discount_percent','Customer Discount','any',100,'Percent off the selling price, from 0 to 100. Applies only to Discount.'],
  ['demand_uplift_percent','Assumed Extra Demand','any',500,'Percent extra demand during Discount, from 0 to 500. This is your assumption, not proven customer behaviour.'],
  ['cash_budget','Purchase Budget','any',1000000000000000,'{currency} available for the new order, including delivery and other charges.'],
  ['max_unmet_units','Maximum Unfilled Demand','any',84000000,'Optional units of demand you are willing to miss. Leave blank for no service limit.'],
  ['on_order_units','Stock Already Ordered',1,1000000,'Whole units still in transit. Enter 0 if none; see the required confirmation below otherwise.']
];
const fieldHelp={
  lead_time_days:['What is lead time?','Lead time is the waiting period before a supplier delivery is available for sale. The model assumes delivery at the start of the following day.'],
  safety_stock:['What is safety stock?','Safety stock is your chosen backup quantity. It is added to demand during the delivery wait to set an inventory target; it does not guarantee demand will be met.'],
  on_order_units:['How is stock in transit used?','Inventory & Risk counts it towards the stock target, but not towards demand before arrival. Financial Decision Lab cannot schedule existing orders; they must be explicitly excluded from a separate scenario.'],
  excess_cover_days:['What is stock cover?','Days of cover divides current stock by average forecast daily demand. This warning limit is your policy choice, not a universal risk threshold.'],
  existing_unit_cost:['How is cost of goods sold (COGS) calculated?','Only the cost of units sold is deducted from revenue to calculate gross profit. Existing stock and newly purchased stock use their own cost values.'],
  unit_purchase_cost:['What is the delivered unit cost?','The landed cost of new stock includes its purchase price plus allocated delivery and other purchase charges. It is used in cost of goods sold only when new units sell.'],
  moq:['What is MOQ?','Minimum order quantity (MOQ) is the smallest positive order the supplier accepts. A smaller order is not feasible. Ordering zero is allowed only when there are no purchase charges.'],
  cash_budget:['Why is purchase cash different from profit?','Purchase cash pays for the entire new order now, including units left unsold. Gross profit deducts only the cost of units that actually sell; it excludes operating expenses.'],
  max_unmet_units:['What does unfilled demand mean?','Unmet demand is forecast demand that cannot be served from available stock. Missed sales are not carried forward as backorders.']
};
function fieldExplanation(name){const help=fieldHelp[name];return help?`<details class="field-help"><summary>${esc(help[0])}</summary><p>${esc(help[1])}</p></details>`:'';}
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
function validateForm(form){
  form.querySelectorAll('input').forEach(input=>{
    input.setCustomValidity('');
    if(input.type!=='number')return;
    const label=Context.fieldLabel(input.name),validity=input.validity;
    if(validity.badInput)input.setCustomValidity(`Enter a number for ${label.toLowerCase()}.`);
    else if(validity.valueMissing)input.setCustomValidity(`Enter ${label.toLowerCase()}. Use 0 only when the value is zero.`);
    else if(validity.rangeUnderflow||validity.rangeOverflow)input.setCustomValidity(`${label} must be between ${input.min} and ${input.max}.`);
    else if(validity.stepMismatch)input.setCustomValidity(input.step==='1'?`${label} must be a whole number.`:`Use increments of ${input.step} for ${label.toLowerCase()}.`);
  });
  return form.reportValidity();
}
function setupForm(){
  const inventory=page==='inventory',kind=inventory?'inventory':'scenarios',form=$(inventory?'inventory-form':'scenario-form'),fields=inventory?inventoryFields:scenarioFields;
  const gen=generation,context=state.context;
  // Run the same browser validity checks after assigning business-language guidance.
  form.noValidate=true;
  $(inventory?'inventory-fields':'scenario-fields').innerHTML=fields.map(([name,label,step,max,hint])=>`<div class="field"><label for="${name}">${label}</label><input type="number" id="${name}" name="${name}" step="${step}" min="${name==='excess_cover_days'?'.01':'0'}" max="${max}" aria-describedby="${name}-hint" ${name==='max_unmet_units'?'':'required'}><small id="${name}-hint">${esc(hint.replaceAll('{currency}',currency()))}</small>${fieldExplanation(name)}</div>`).join('')+(business?`<div class="field"><label for="stock_as_of">Stock Count Date</label><input id="stock_as_of" name="stock_as_of" type="date" required><small>Use the closing stock count on ${esc(context.forecast_origin)}, the last day before this forecast.</small></div><label class="check-row"><input type="checkbox" name="hypothetical_stock_at_origin" id="hypothetical_stock_at_origin">Use hypothetical stock at forecast start instead of a recorded stock count on ${esc(context.forecast_origin)}.</label>`:'')+(!inventory?'<label id="on-order-warning" class="check-row warning" hidden><input type="checkbox" name="acknowledge_excluded_on_order" id="acknowledge_excluded_on_order">I am creating a separate scenario that excludes existing on-order stock and its costs. It does not represent the complete inventory situation.</label>':'');
  form.querySelectorAll('button').forEach(b=>b.disabled=false);
  const restoreDefaults=()=>{fields.forEach(([name])=>form.elements[name].value=business?'':(state.defaults[name]??''));if(business){form.elements.stock_as_of.value='';form.elements.hypothetical_stock_at_origin.checked=false;}if(!inventory)form.elements.acknowledge_excluded_on_order.checked=false;timingRules(form);};
  restoreDefaults();const saved=drafts.read(context)[kind]||{};fill(form,saved);timingRules(form);
  const results=$(inventory?'inventory-results':'scenario-results');results.hidden=true;
  form.querySelector('.form-status').textContent=Object.keys(saved).length?'Your saved inputs are restored · review any missing values before calculating':business?'Enter your business assumptions · no demo values applied':'Ready · editable Demo assumptions';
  function changed(){calculation++;results.hidden=true;form.querySelectorAll('input').forEach(input=>input.setCustomValidity(''));timingRules(form);drafts.save(context,kind,formInputs(form));form.querySelector('.form-status').textContent='Inputs changed · calculate again to update results';if(!inventory){$('handoff-confirm').hidden=true;updateHandoffDifferences(form);}}
  form.oninput=changed;form.onchange=changed;
  form.querySelector('.reset').onclick=()=>{calculation++;drafts.clear(context);restoreDefaults();results.hidden=true;$('error').hidden=true;$('retry-connection').hidden=true;form.querySelector('.form-status').textContent=business?'Current context cleared · enter assumptions':'Current context cleared · disclosed Demo assumptions restored';if(!inventory)setupHandoff(form,changed);};
  form.onsubmit=async event=>{
    event.preventDefault();timingRules(form);if(!validateForm(form)){results.hidden=true;const invalid=form.querySelector(':invalid');form.querySelector('.form-status').textContent=invalid?.validationMessage||'Review the highlighted input and try again.';return;}
    const values=formInputs(form),token=++calculation;drafts.save(context,kind,values);
    $('error').hidden=true;$('retry-connection').hidden=true;results.hidden=true;
    const buttons=form.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);form.querySelectorAll('input').forEach(i=>i.readOnly=true);form.querySelector('.form-status').textContent='Calculating from your inputs…';
    try{const result=await calculate(kind,values,controller.signal);if(gen!==generation||token!==calculation)return;inventory?renderInventory(result,values):renderScenarios(result,values);form.querySelector('.form-status').textContent='Updated · calculated from the inputs shown above';}
    catch(error){if(error.name!=='AbortError'&&gen===generation&&token===calculation){showError(error);form.querySelector('.form-status').textContent='No updated result · follow the guidance above and try again';}}
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
function handoffInputs(inputs){return Object.fromEntries(['current_stock','lead_time_days','stock_as_of','hypothetical_stock_at_origin'].filter(k=>inputs[k]!==undefined).map(k=>[k,inputs[k]]));}
function updateHandoffDifferences(form){
  const box=$('handoff-differences');if(!box)return;
  const inputs=drafts.read(state.context).inventory||{},changes=Context.assumptionChanges(formInputs(form),handoffInputs(inputs));
  box.innerHTML=changes.length?'<p><strong>Inventory inputs are not yet used here.</strong> Current Decision Lab value → saved Inventory value:</p><ul>'+changes.map(change=>`<li>${esc(change.label)}: <strong>${esc(change.before)} → ${esc(change.after)}</strong></li>`).join('')+'</ul><p>Nothing changes until you review and confirm below.</p>':'<p>Shared stock and delivery inputs match your saved Inventory assumptions.</p>';
  if(Object.keys(inputs).length)box.innerHTML+='<p>Backup stock and the excess stock warning threshold remain Inventory settings. A suggested order quantity is imported separately; your prices, costs and budget are not replaced.</p>';
}
function setupHandoff(form,changed){
  const inputs=drafts.read(state.context).inventory||{},box=$('inventory-handoff');box.hidden=!Object.keys(inputs).length;if(box.hidden)return;
  const blocked=Number(inputs.on_order_units)>0,complete=completeInventory(inputs),gen=generation;
  updateHandoffDifferences(form);
  $('handoff-note').textContent=blocked?'You have stock already ordered. This financial model cannot schedule those arrivals, so automatic import is unavailable. Review a separate manual scenario and explicitly confirm any excluded stock.':complete?'You choose which saved Inventory assumptions to bring into this financial comparison. Review the old and new values before confirming.':'Your Inventory inputs are incomplete. Complete and calculate Inventory & Risk before importing them.';
  $('use-inventory-assumptions').disabled=$('use-suggested-quantity').disabled=blocked||!complete;$('handoff-confirm').hidden=true;
  const preview=values=>{
    if(gen!==generation)return;
    const changes=Context.assumptionChanges(formInputs(form),values);
    $('handoff-preview').innerHTML=(changes.length?'<p>Confirm these changes to your Decision Lab inputs:</p><ul>'+changes.map(change=>`<li>${esc(change.label)}: <strong>${esc(change.before)} → ${esc(change.after)}</strong></li>`).join('')+'</ul>':'<p>These inputs already match; no values need replacing.</p>')+'<p>Other financial inputs stay as entered. If you choose an order quantity of zero, also set delivery and other purchase charges to zero.</p>';
    $('handoff-confirm').hidden=false;
    $('confirm-handoff').onclick=()=>{if(gen!==generation)return;fill(form,values);changed();$('handoff-confirm').hidden=true;};
  };
  $('use-inventory-assumptions').onclick=()=>preview(handoffInputs(inputs));
  $('use-suggested-quantity').onclick=async()=>{try{const result=await calculate('inventory',inputs,controller.signal);preview({order_quantity:result.suggested_reorder_quantity});}catch(error){if(error.name!=='AbortError')showError(error);}};
  $('cancel-handoff').onclick=()=>$('handoff-confirm').hidden=true;
}
function renderInventory(result,inputs){
  $('inventory-results').hidden=false;$('risk-banner').innerHTML=`<div class="alert ${result.stockout_risk?'danger':result.status==='Sufficient Inventory'?'success':'warning'}"><h2>${esc(riskLabel(result))}</h2><p>${esc(Context.businessText(result.explanation))}</p><p>This checks stock during the supplier waiting period and your backup target. It does not mean current stock covers all 14 forecast days.</p></div>`;
  $('inventory-kpis').innerHTML=kpi('Days Stock Will Last',result.days_of_cover===null?'No forecast demand':num(result.days_of_cover),'Days of cover · current stock / average daily demand')+kpi('Demand While Waiting for Delivery',num(result.lead_time_demand),result.extrapolated?'Units · extends beyond the 14-day forecast':'Units · forecast demand during supplier delivery time')+kpi('Suggested Additional Order',num(result.suggested_reorder_quantity),'Whole units · review supplier terms, costs and budget')+kpi('Stock Including Open Orders',num(result.inventory_position),'Inventory position · current + already ordered units');
  if($('inventory-coverage'))$('inventory-coverage').innerHTML='<h3>What this stock assessment covers</h3><dl class="strategy-metrics">'+[['Current stock',num(inputs.current_stock)+' units'],['Supplier delivery time',num(inputs.lead_time_days)+' days'],['Demand during delivery time',num(result.lead_time_demand)+' units'],['Backup stock target',num(inputs.safety_stock)+' units'],['Full 14-day forecast demand',num(state.analysis.total_forecast_demand)+' units']].map(([label,value])=>`<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('')+'</dl><p>Stock, delivery time and backup stock are the assumptions you submitted. Demand is calculated by Python from this product’s forecast. To see stock limits and deliveries across all 14 days, run Financial Decision Lab.</p>';
  $('inventory-notes').innerHTML=`<p>Risk of running out before delivery: <strong>${result.stockout_risk?'Yes':'No'}</strong> · Excess stock warning: <strong>${result.excess_inventory_warning?'Yes':'No'}</strong></p><p>Target including backup stock: ${num(result.target_inventory_position)} units. Average forecast demand: ${num(result.average_daily_demand)} units per day. Your excess stock warning starts above ${num(result.excess_cover_days)} days of cover.</p><p>Stock already ordered reduces the additional order suggestion but cannot meet demand before it arrives; its delivery dates are unknown.</p>${result.extrapolated?`<p>${esc(result.extension_rule)} This extends the estimate beyond the original 14-day forecast.</p>`:''}`;
}
function feasibilityLabel(strategy){return strategy.feasible?'Feasible':'Not feasible';}
function strategyReasons(strategy){return (strategy.reasons||[]).map(reason=>{
  const fixes={
    'Procurement cash exceeds budget.':'The new purchase costs more than your budget. Reduce the order or its charges, or review your budget.',
    'Order quantity is below MOQ.':'The order is smaller than the supplier’s minimum order quantity. Increase it to the minimum, or compare a strategy with no new order.',
    'A zero-quantity order cannot have procurement charges.':'An order of zero units still has purchase charges. Set the delivery charge and other purchase charges to zero, or enter a positive order quantity.',
    'Unmet demand exceeds the user service constraint.':'Unfilled demand is above the maximum you set. Review available stock, delivery timing or that service limit.'
  };return fixes[reason]||Context.businessText(reason);
});}
function strategyConstraints(strategy,result,inputs){
  const budget=strategy.budget_satisfied===true?'Within budget':strategy.budget_satisfied===false?'Over budget':'Not assessed';
  const minimum=strategy.strategy!=='Reorder'?'Not applicable — no new order':strategy.moq_satisfied?'Satisfied':'Not satisfied';
  return `<p><strong>Purchase budget:</strong> ${esc(money(result.cash_budget))} · ${esc(budget)}</p><p><strong>Minimum order quantity:</strong> ${esc(num(inputs.moq))} units · ${esc(minimum)}</p>`;
}
function renderScenarios(result,inputs){
  if(result.currency!==currency())throw Error('The result uses a different currency from your selected data. Reload the page and review the selected dataset.');
  const reason=result.recommendation?'This strategy has the highest expected gross profit among options that meet your purchase budget, supplier conditions and any unfilled-demand limit. Equal-profit ties prefer Wait, then Reorder, then Discount.':'None of these strategies meets all your limits. Review the reasons below; no strategy is recommended.';
  $('scenario-results').hidden=false;$('recommendation').innerHTML=`<div class="alert ${result.recommendation?'success':'warning'}"><h2>${result.recommendation?'Recommended: '+esc(result.recommendation):'No feasible strategy'}</h2><p>${esc(reason)}</p></div>`;
  $('scenario-table').innerHTML=table(['Strategy','Revenue','Gross Profit','Gross Margin','Unmet Demand','Ending Stock','Purchase Cash','Feasibility'],result.strategies.map(s=>[esc(s.strategy)+(s.strategy===result.recommendation?' '+tag('Recommended','blue'):''),money(s.revenue),`<strong class="${s.gross_profit===null?'':Number(s.gross_profit)>=0?'positive':'negative'}">${money(s.gross_profit)}</strong>`,s.gross_margin===null?'—':num(s.gross_margin)+'%',num(s.unmet_demand),num(s.ending_inventory),money(s.procurement_cash_outlay),tag(feasibilityLabel(s),s.feasible?'green':'red')]));
  if($('scenario-cards'))$('scenario-cards').innerHTML=result.strategies.map(s=>{
    const reasons=strategyReasons(s);
    return `<article class="strategy-card ${s.strategy===result.recommendation?'is-recommended':''}" aria-label="${esc(s.strategy)} strategy"><header><h3>${esc(s.strategy)}</h3>${s.strategy===result.recommendation?tag('Recommended','blue'):''}</header><dl class="strategy-metrics">`+
      [['Revenue',money(s.revenue)],['Gross Profit',money(s.gross_profit)],['Gross Margin',s.gross_margin===null?'—':num(s.gross_margin)+'%'],['Procurement Cash',money(s.procurement_cash_outlay)],['Unmet Demand',num(s.unmet_demand)+' units'],['Ending Stock',num(s.ending_inventory)+' units']].map(([label,value])=>`<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('')+
      `</dl><div class="strategy-feasibility"><strong>Feasibility</strong> ${tag(feasibilityLabel(s),s.feasible?'green':'red')}${strategyConstraints(s,result,inputs)}${reasons.length?'<ul>'+reasons.map(message=>'<li>'+esc(message)+'</li>').join('')+'</ul>':'<p>Meets the purchase and service limits you entered.</p>'}</div></article>`;
  }).join('');
  chart('profit-chart',result.strategies.map(s=>s.strategy),[{name:`Gross profit (${currency()}) · options marked not feasible cannot be recommended`,values:result.strategies.map(s=>s.gross_profit)}],true);
  $('tradeoffs').innerHTML=result.strategies.map(s=>`<div class="tradeoff"><strong>${esc(s.strategy)}</strong> ${tag(feasibilityLabel(s),s.feasible?'green':'red')}<p>${s.reasons.length?esc(strategyReasons(s).join(' ')):`${num(s.unmet_demand)} units of unfilled demand · ${money(s.procurement_cash_outlay)} needed for new stock · ${num(s.ending_inventory)} units left at the end.`}</p>${strategyConstraints(s,result,inputs)}${s.receipt_day?`<p>New stock arrives on day ${s.receipt_day}. Units sold before / from arrival: ${num(s.sales_before_receipt)} / ${num(s.sales_after_receipt)}. Still in transit at the end: ${num(s.in_transit_units)} units.</p>`:''}</div>`).join('');
  $('scenario-audit').innerHTML=result.strategies.map(s=>`<h3>${esc(s.strategy)}</h3>${s.daily.length?`<p>Cost of existing stock sold: ${money(s.existing_cogs)} · Cost of newly purchased stock sold: ${money(s.new_cogs)} · Delivered cost per new unit: ${money(s.unit_landed_cost)}.</p><p>These sold-stock costs form cost of goods sold (COGS), rather than the whole purchase cash payment. Potential missed revenue: ${money(s.potential_lost_revenue)}; potential missed gross profit: ${money(s.potential_lost_gross_profit)}.</p>`+table(['Day','Demand','Delivery','Units sold','Unfilled demand','Stock left'],s.daily.map(d=>[d.day,num(d.demand),num(d.received_units),num(d.units_sold),num(d.unmet_demand),num(d.ending_inventory)])):`<p>${esc(strategyReasons(s).join(' '))}</p>`}`).join('');
  const winner=result.strategies.find(s=>s.strategy===result.recommendation);
  $('decision-summary').innerHTML='<h2>Purchasing Decision Summary</h2>'+`<p>${esc(state.item_id)} / ${esc(state.store_id)} · ${esc(state.analysis.future[0].date)} — ${esc(state.analysis.future[state.analysis.future.length-1].date)} · ${currency()} · your reviewed assumptions</p>`+
    (winner?`<div class="kpis">${kpi('Recommended strategy',winner.strategy,'Highest expected gross profit among the feasible options',true)}${kpi('14-day demand before discounts',num(state.analysis.total_forecast_demand),'Units · before your assumed extra promotional demand')}${kpi('Expected revenue',money(winner.revenue),currency(),true)}${kpi('Expected gross profit',money(winner.gross_profit),'Revenue less the cost of stock sold; excludes operating expenses',true)}${kpi('Cash for the new purchase',money(winner.procurement_cash_outlay),'Includes all new units, delivery and other purchase charges',true)}${kpi('Unfilled demand',num(winner.unmet_demand),'Units · selected strategy')}${kpi('Stock left after 14 days',num(winner.ending_inventory),'Units · selected strategy')}${kpi('Purchase limits',`${winner.budget_satisfied===false?'Over budget':winner.budget_satisfied===true?'Within budget':'Budget not assessed'} / ${winner.moq_satisfied?'Minimum order satisfied':'Minimum order not met'}`,'Based on the limits and assumptions you entered',true)}</div>`:'<p>No feasible recommendation. Review your inputs and the reasons for each strategy.</p>')+
    `<p>${esc(reason)}</p><p>Review the other strategies below. This compares your chosen quantities and assumptions; it is not a search for the best possible order and does not create a purchase order.</p><p>${esc(Context.businessText(result.limitations||''))}</p>`;
}
(async()=>{
  setModeLabels();
  try{
    features=await api('/api/features');
    synthetic=!business&&(synthetic||(!features.demo_enabled&&features.synthetic_demo_enabled===true));
    setModeLabels();
    if(business){
      $('upload-panel')&&($('upload-panel').hidden=!features.upload_enabled);$('series-selection').hidden=true;
      if(!features.upload_enabled){notice('Analyse My Business · Temporarily unavailable. Private uploads are undergoing safety checks. You can explore Synthetic Demo or Market Intelligence now.');$('loading').hidden=true;return;}
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
