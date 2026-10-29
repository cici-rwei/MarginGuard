/* Dataset-wide inventory review. Python supplies risk, totals, filtering and ordering. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.MarginGuardRisk=api;
})(typeof window==='object'?window:null,function(){
  'use strict';
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=value=>value===null||value===undefined?'Not available':Number(value).toLocaleString('en-US',{maximumFractionDigits:2});
  const units=value=>value===null||value===undefined?'Unknown':number(value)+' units';
  const contextFields=['source_kind','dataset_id','revision','series_id','forecast_origin','currency'];
  const risks=new Set(['all','stockout','reorder_attention','excess','sufficient','not_assessed']);
  const sorts=new Set(['priority','product','stock_asc','demand_desc']);
  function contextMatches(left,right){return !!left&&!!right&&left.source_kind==='user_csv'&&contextFields.every(key=>typeof left[key]==='string'&&left[key]!==''&&left[key]===right[key]);}
  function detailUrl(path,context,row){
    if(!['/inventory','/scenarios','/forecasting'].includes(path))throw Error('Unsupported detail page.');
    const params=new URLSearchParams({mode:'business',dataset:context.dataset_id,revision:context.revision,series:row.series_id});
    return path+'?'+params;
  }
  function filterQuery(revision,values){
    if(!risks.has(values.risk)||!sorts.has(values.sort))throw Error('Choose a supported risk filter and sort order.');
    const result=new URLSearchParams({revision,risk:values.risk,sort:values.sort});
    if(values.store)result.set('store',values.store);
    if(values.search)result.set('search',values.search.trim());
    return result.toString();
  }
  function summaryMarkup(summary){
    const metrics=[['Products Analysed','products_analysed','Successful 14-day forecasts'],['High Stockout Risk','high_stockout_risk','Stock below delivery-time demand'],['Excess Inventory Risk','excess_inventory_risk','Above your stock-cover policy'],['Sufficient Inventory','sufficient_inventory','Delivery-time demand + backup target'],['Data Incomplete','data_incomplete','Not assessed; review missing information']];
    return metrics.map(([label,key,note])=>'<div class="kpi"><div class="kpi-label">'+escape(label)+'</div><div class="kpi-value">'+escape(number(summary[key]))+'</div><div class="kpi-note">'+escape(note)+'</div></div>').join('');
  }
  function issueText(issue){return typeof issue==='string'?issue:(issue?.message||issue?.reason||issue?.code||'Review this record.');}
  function rowsMarkup(rows,context,preview=false){
    if(!rows.length)return '<p class="note">No products match these filters. Try another status, store or search.</p>';
    return '<div class="risk-row-list">'+rows.map(row=>{
      const tone=row.risk_code==='stockout'?'red':row.risk_code==='sufficient'?'green':row.risk_code==='not_assessed'?'neutral':'amber';
      const issues=Array.isArray(row.issues)?row.issues:[];
      const forecastReady=row.forecast_demand!==null&&row.forecast_demand!==undefined;
      const facts=row.risk,inputs=row.inventory_inputs;
      const calculation=facts&&inputs?'<details class="source-details risk-calculation"><summary>Stock calculation details</summary><dl class="risk-row-metrics">'+[['Supplier Delivery Time',number(inputs.lead_time_days)+' days'],['Demand Before Delivery',units(facts.lead_time_demand)],['Backup Stock',units(inputs.safety_stock)],['Stock Coverage Days',facts.days_of_cover===null?'No forecast demand':number(facts.days_of_cover)+' days'],['Stock Already Ordered',units(inputs.on_order_units)+' · not current stock'],['Excess Stock Warning After',number(facts.excess_cover_days)+' days'],['Stockout Warning',facts.stockout_risk===true?'Yes':facts.stockout_risk===false?'No':'Not assessed'],['Excess Stock Warning',facts.excess_inventory_warning===true?'Yes':facts.excess_inventory_warning===false?'No':'Not assessed']].map(([label,value])=>'<dt>'+escape(label)+'</dt><dd>'+escape(value)+'</dd>').join('')+'</dl><p>Suggested quantities are additional units under the inventory rule, not an optimal purchase. Review delivery timing, minimum orders and cash before buying. Open orders cannot cover demand before arrival.'+(facts.extrapolated?' Demand beyond day 14 uses the forecast’s average daily demand.':'')+'</p></details>':'';
      const links=!preview&&forecastReady?'<div class="risk-detail-links"><a class="text-link" data-risk-detail-link href="'+escape(detailUrl('/inventory',context,row))+'">Review inventory →</a><a class="text-link" data-risk-detail-link href="'+escape(detailUrl('/scenarios',context,row))+'">Review financial decision →</a></div>':'';
      return '<article class="risk-row"><header><div><h4>'+escape(row.item_id)+'</h4><span>Store: '+escape(row.store_id)+'</span></div><span class="tag '+tone+'">'+escape(row.risk_code==='sufficient'?'Sufficient for delivery-time demand + backup target':row.status||'Not assessed')+'</span></header><dl class="risk-row-metrics"><dt>Current stock</dt><dd>'+escape(units(row.current_stock))+'</dd><dt>14-day forecast demand</dt><dd>'+escape(units(row.forecast_demand))+'</dd><dt>Stock count date</dt><dd>'+escape(row.stock_as_of_date||'Not supplied')+'</dd><dt>Required closing stock date</dt><dd>'+escape(row.expected_stock_date||'No forecast history selected')+'</dd></dl><p class="risk-period">Forecast: '+escape(forecastReady?row.forecast_start+' — '+row.forecast_end:'Not available')+'</p><p><strong>'+escape(row.action||'Review data')+'</strong> '+escape(row.action_reason||'')+'</p>'+(facts?'<p class="risk-order"><strong>Suggested Reorder Quantity:</strong> '+escape(units(facts.suggested_reorder_quantity))+'</p>':'')+calculation+(issues.length?'<details class="source-details"><summary>Data checks ('+issues.length+')</summary><ul>'+issues.map(issue=>'<li>'+escape(issueText(issue))+'</li>').join('')+'</ul></details>':'')+links+'</article>';
    }).join('')+'</div>';
  }
  function snapshotValues(snapshot,context,kind,suggestion=false){
    if(!snapshot||!contextMatches(snapshot.context,context)||!snapshot.inputs)throw Error('These stock inputs no longer match this product and data version. Reload the page.');
    if(kind==='scenarios'&&Number(snapshot.inputs.on_order_units)>0)throw Error('Stock is already on order. Automatic financial import is unavailable because this model cannot schedule those arrivals. Review Inventory & Risk and explicitly acknowledge exclusions in a separate manual scenario.');
    if(suggestion){
      if(kind!=='scenarios'||!Number.isFinite(snapshot.suggested_reorder_quantity)||snapshot.suggested_reorder_quantity<0)throw Error('No current suggested order quantity is available.');
      return {order_quantity:snapshot.suggested_reorder_quantity};
    }
    const keys=kind==='inventory'?['current_stock','lead_time_days','safety_stock','on_order_units','excess_cover_days','stock_as_of','hypothetical_stock_at_origin']:['current_stock','lead_time_days','on_order_units','stock_as_of','hypothetical_stock_at_origin'];
    return Object.fromEntries(keys.filter(key=>snapshot.inputs[key]!==undefined).map(key=>[key,snapshot.inputs[key]]));
  }
  function createOverview(options){
    const doc=options.document||document,el=id=>doc.getElementById(id),panel=el('business-risk-overview');
    if(!panel)return null;
    let current=null,pending=null,generation=0,controller=null,uploadGeneration=0,lastRenderedRevision=null;
    const request=options.request,Context=window.MarginGuardContext;
    function error(id,value){const box=el(id),issues=Array.isArray(value.issues)?value.issues:[];box.innerHTML='<p>'+escape(Context.friendlyError(value))+'</p>'+(issues.length?'<ul>'+issues.map(issue=>'<li>'+escape(issue.line?'Line '+issue.line+' · ':'')+escape(Context.businessText(issueText(issue)))+'</li>').join('')+'</ul>':'');box.hidden=false;}
    function validate(data,context){if(data.dataset_id&&data.dataset_id!==context.dataset_id||data.revision&&data.revision!==context.revision)throw Error('The stock overview belongs to another data version. Reload your sales data.');}
    function render(data,context){
      validate(data,context);lastRenderedRevision=context.revision;
      el('risk-kpis').innerHTML=summaryMarkup(data.summary||{});
      const summary=data.summary||{};
      el('risk-coverage').textContent='Complete dataset: '+number(summary.total_products)+' product–store combinations · '+number(summary.products_analysed)+' forecasted · '+number(summary.reorder_attention)+' need backup-stock / reorder attention. Counts do not change with list filters. Inventory checks use confirmed snapshots, not this tab’s manual scenario drafts.';
      el('priority-risk-list').innerHTML=rowsMarkup(data.rows||[],context);
      el('risk-status').textContent=number(data.filtered_count)+' product–store combinations shown. Review each product’s dates and data checks.';
    }
    function filters(){return {risk:el('risk-filter').value,store:el('risk-store').value,search:el('risk-search').value,sort:el('risk-sort').value};}
    async function refresh(){
      if(!current)return;
      const context={...current},token=++generation;controller?.abort();controller=new AbortController();
      el('risk-errors').hidden=true;el('risk-status').textContent='Refreshing risk review…';el('priority-risk-list').setAttribute('aria-busy','true');
      try{
        const data=await request('/api/business/datasets/'+encodeURIComponent(context.dataset_id)+'/inventory-risk?'+filterQuery(context.revision,filters()),{signal:controller.signal});
        if(token!==generation)return;render(data,context);
      }catch(value){if(value.name!=='AbortError'&&token===generation){lastRenderedRevision=null;el('priority-risk-list').innerHTML='';el('risk-kpis').innerHTML='';el('risk-coverage').textContent='';el('risk-status').textContent='No current risk result. Your filters are kept; retry when ready.';error('risk-errors',value);}}
      finally{if(token===generation)el('priority-risk-list').setAttribute('aria-busy','false');}
    }
    function qualityMarkup(data){
      const overview=data.overview||{},quality=overview.inventory_quality||{},issues=Array.isArray(data.report?.issues)?data.report.issues:[],unmatched=Array.isArray(quality.unmatched)?quality.unmatched:[];
      const summaries=[['Inventory rows',quality.row_count],['Matched product–store combinations',quality.matched_rows],['Rows with no matching sales combination',quality.unmatched_rows],['Stock dates that do not match selected history',quality.date_mismatch_count],['Sales combinations without a stock snapshot',quality.missing_snapshot_count],['Blank open orders set to zero by your declaration',quality.assumed_no_on_order_count]].map(([label,value])=>'<li>'+escape(label)+': '+escape(number(value))+'</li>').join('');
      const unmatchedDetails=unmatched.length?'<details class="source-details"><summary>Review unmatched stock rows ('+unmatched.length+')</summary><ul>'+unmatched.map(row=>'<li>'+escape(row.product||'Product missing')+' / '+escape(row.store||'Store missing')+' · '+escape(row.stock_as_of_date||'Date missing')+'</li>').join('')+'</ul><p>These rows cannot be used for inventory or financial analysis. Correct the identifiers or add matching sales records.</p></details>':'';
      return '<h3>Review inventory data quality</h3><p>This is a pending snapshot. The active risk overview stays unchanged until you confirm.</p><ul>'+summaries+'</ul>'+unmatchedDetails+(issues.length?'<details class="source-details"><summary>Missing-cell checks ('+issues.length+')</summary><ul>'+issues.map(value=>'<li>'+escape(value.line?'Line '+value.line+' · ':'')+escape(Context.businessText(issueText(value)))+'</li>').join('')+'</ul></details>':'')+'<p>Review each match and required date below. Missing or invalid inputs remain unassessed; they are not zero stock.</p>'+rowsMarkup(overview.rows||[],current,true)+'<div class="form-actions"><button type="button" id="confirm-inventory-upload" class="primary">Confirm inventory snapshot</button><button type="button" id="discard-inventory-upload" class="secondary">Discard pending snapshot</button></div>';
    }
    function showPending(data){
      pending=data;el('inventory-upload-report').innerHTML=qualityMarkup(data);el('inventory-upload-report').hidden=false;
      el('confirm-inventory-upload').onclick=async()=>{
        if(!pending||!current)return;
        const context={...current},draft=pending,token=uploadGeneration;const button=el('confirm-inventory-upload');button.disabled=true;let saved=false;
        try{
          const data=await request('/api/business/datasets/'+encodeURIComponent(context.dataset_id)+'/inventory-uploads/'+encodeURIComponent(draft.upload_id)+'/confirm',{method:'POST',json:{revision:context.revision,upload_revision:draft.revision}});
          if(token!==uploadGeneration)return;
          saved=true;pending=null;generation++;controller?.abort();lastRenderedRevision=null;
          current={dataset_id:context.dataset_id,revision:data.revision};
          el('risk-kpis').innerHTML='';el('priority-risk-list').innerHTML='';el('risk-coverage').textContent='';
          el('risk-status').textContent='Snapshot saved. Refreshing results for the new version…';
          el('inventory-upload-report').hidden=true;el('inventory-upload-errors').hidden=true;el('inventory-upload-status').textContent='Snapshot saved. Previous risk results have been cleared while updated results load.';
          await options.onConfirmed(data);
          el('inventory-upload-status').textContent=lastRenderedRevision===data.revision?'Stock snapshot confirmed. The overview now uses this version; review imports before changing a scenario.':'Snapshot saved, but updated risk results are unavailable. Refresh risks or reload this page; do not submit the same snapshot again.';
        }catch(value){if(saved){el('inventory-upload-status').textContent='Snapshot saved, but updated results are unavailable. Refresh risks or reload this page; previous results are no longer current.';error('inventory-upload-errors',value);}else if(token===uploadGeneration)error('inventory-upload-errors',value);}
        finally{button.disabled=false;}
      };
      el('discard-inventory-upload').onclick=async()=>{
        if(!pending||!current)return;
        try{await request('/api/business/datasets/'+encodeURIComponent(current.dataset_id)+'/inventory-uploads/'+encodeURIComponent(pending.upload_id),{method:'DELETE'});pending=null;el('inventory-upload-report').hidden=true;el('inventory-upload-status').textContent='Pending snapshot discarded. Confirmed inventory is unchanged.';}
        catch(value){error('inventory-upload-errors',value);}
      };
    }
    el('risk-filter-form').onsubmit=event=>{event.preventDefault();refresh();};
    ['risk-filter','risk-store','risk-sort'].forEach(id=>el(id).onchange=refresh);
    el('risk-refresh').onclick=refresh;
    el('inventory-upload-form').onsubmit=async event=>{
      event.preventDefault();const form=event.currentTarget;if(!current||!form.reportValidity())return;
      const file=el('inventory-csv-file').files[0];if(!file)return;
      const token=++uploadGeneration,context={...current},button=form.querySelector('button[type=submit]');pending=null;el('inventory-upload-report').hidden=true;button.disabled=true;el('inventory-upload-errors').hidden=true;el('inventory-upload-status').textContent='Checking stock records…';
      try{
        const session=await options.getSession();if(file.size>session.limits.file_bytes)throw Object.assign(Error('Inventory CSV exceeds the file-size limit.'),{code:'file_too_large'});
        const data=new FormData(form);data.set('revision',context.revision);data.set('assume_no_on_order',el('inventory-no-on-order').checked?'true':'false');
        const response=await request('/api/business/datasets/'+encodeURIComponent(context.dataset_id)+'/inventory-uploads',{method:'POST',form:data});
        if(token!==uploadGeneration)return;
        if(response.dataset_revision!==context.revision)throw Error('Your sales data changed. Reload before reviewing this stock snapshot.');
        showPending(response);el('inventory-csv-file').value='';el('inventory-upload-status').textContent='Review required. Nothing has been applied to your active inventory.';
      }catch(value){if(token===uploadGeneration){error('inventory-upload-errors',value);el('inventory-upload-status').textContent='Validation failed. Confirmed sales and stock are unchanged.';}}
      finally{button.disabled=false;}
    };
    async function setDataset(data){
      const changed=!current||current.dataset_id!==data.dataset_id||current.revision!==data.revision;
      current={dataset_id:data.dataset_id,revision:data.revision};panel.hidden=false;
      if(changed){uploadGeneration++;pending=null;el('inventory-upload-report').hidden=true;el('inventory-upload-errors').hidden=true;}
      const selected=el('risk-store').value,stores=[...new Set((data.catalog_series||data.series||[]).map(row=>row.store_id))];
      el('risk-store').innerHTML='<option value="">All stores</option>'+stores.map(value=>'<option value="'+escape(value)+'">'+escape(value)+'</option>').join('');
      if(stores.includes(selected))el('risk-store').value=selected;
      await refresh();
    }
    function clear(){generation++;uploadGeneration++;controller?.abort();current=pending=lastRenderedRevision=null;panel.hidden=true;el('risk-kpis').innerHTML='';el('priority-risk-list').innerHTML='';el('inventory-upload-report').hidden=true;}
    return {setDataset,refresh,clear};
  }
  function attachSnapshot(options){
    const {form,snapshot,context,kind,currentValues,onApply,isCurrent,request}=options,doc=form.ownerDocument,Context=window.MarginGuardContext;
    doc.getElementById('snapshot-import')?.remove();
    if(!snapshot||!contextMatches(snapshot.context,context))return null;
    const box=doc.createElement('section');box.id='snapshot-import';box.className='note snapshot-import';
    const blocked=kind==='scenarios'&&Number(snapshot.inputs?.on_order_units)>0;
    box.innerHTML='<h3>Confirmed inventory snapshot</h3><p>Closing stock dated '+escape(snapshot.inputs?.stock_as_of)+'. Review before applying: this will not replace your existing inputs automatically.</p>'+(blocked?'<p class="warning">Stock is already on order. This financial model cannot schedule those arrivals, so automatic import is unavailable. Review Inventory & Risk, then explicitly acknowledge excluded orders if you create a separate manual scenario.</p>':'<div class="handoff-buttons"><button type="button" id="review-snapshot-inputs" class="secondary">Review snapshot inputs</button>'+(kind==='scenarios'?'<button type="button" id="review-snapshot-order" class="secondary">Review suggested order quantity</button>':'')+'</div>')+'<p>Prices, costs and budgets stay as entered. An inventory-rule order suggestion is not an optimised purchase or a budget approval.</p><div id="snapshot-confirmation" hidden><div id="snapshot-differences"></div><button type="button" id="apply-snapshot" class="primary">Apply reviewed inputs</button><button type="button" id="cancel-snapshot" class="secondary">Keep current inputs</button></div><p id="snapshot-import-error" role="alert" hidden></p>';
    form.before(box);let token=0,values=null;
    const get=id=>box.querySelector('#'+id);
    function invalidate(){token++;values=null;get('snapshot-confirmation').hidden=true;}
    function preview(suggestion){
      try{values=snapshotValues(snapshot,context,kind,suggestion);token++;get('snapshot-import-error').hidden=true;const changes=Context.assumptionChanges(currentValues(),values);get('snapshot-differences').innerHTML=changes.length?'<p>Current input → confirmed snapshot:</p><ul>'+changes.map(change=>'<li>'+escape(change.label)+': <strong>'+escape(change.before)+' → '+escape(change.after)+'</strong></li>').join('')+'</ul>':'<p>These inputs already match the confirmed snapshot.</p>';get('snapshot-confirmation').hidden=false;}
      catch(value){get('snapshot-import-error').textContent=Context.friendlyError(value);get('snapshot-import-error').hidden=false;}
    }
    if(!blocked){get('review-snapshot-inputs').onclick=()=>preview(false);if(kind==='scenarios')get('review-snapshot-order').onclick=()=>preview(true);}
    get('cancel-snapshot').onclick=invalidate;
    get('apply-snapshot').onclick=async()=>{
      if(!values||!isCurrent())return;
      const proposed={...values},attempt=token,button=get('apply-snapshot');button.disabled=true;
      try{
        const params=new URLSearchParams({series_id:context.series_id,revision:context.revision});
        const fresh=await request('/api/business/datasets/'+encodeURIComponent(context.dataset_id)+'/analysis?'+params);
        if(attempt!==token||!isCurrent())return;
        if(!contextMatches(fresh.context,context)||!contextMatches(fresh.inventory_import?.context,context))throw Error('The confirmed stock snapshot changed. Reload before applying it.');
        onApply(proposed);invalidate();
      }catch(value){if(attempt===token){get('snapshot-import-error').textContent=Context.friendlyError(value);get('snapshot-import-error').hidden=false;}}
      finally{button.disabled=false;}
    };
    return {invalidate};
  }
  return {contextMatches,detailUrl,filterQuery,summaryMarkup,rowsMarkup,snapshotValues,createOverview,attachSnapshot};
});
