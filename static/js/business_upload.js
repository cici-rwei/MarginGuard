/* Upload transport and review UI. CSRF stays in memory, never Web Storage. */
window.MarginGuardUpload = (function () {
  'use strict';
  let session=null, sessionPromise=null, pending=null, activeId=null, callbacks={};
  const el=id=>document.getElementById(id);
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function response(url, options) {
    let result;
    try { result=await fetch(url,{credentials:'same-origin',cache:'no-store',...options}); }
    catch(error) { if(error.name==='AbortError') throw error; throw Error('Cannot reach MarginGuard. Check your internet connection and retry. Your file has not been confirmed for analysis.'); }
    const data=await result.json().catch(()=>({error:'The server returned an unreadable response.'}));
    if(!result.ok) {
      const error=Object.assign(Error(typeof data.error==='string'?data.error:'Request failed.'),{status:result.status,code:data.code,issues:data.issues});
      if([401,410].includes(result.status)) { session=null; if(callbacks.onExpired)callbacks.onExpired(error); }
      throw error;
    }
    return data;
  }
  async function getSession() {
    if(session) return session;
    if(!sessionPromise) sessionPromise=response('/api/business/session',{}).then(value=>(session=value)).finally(()=>sessionPromise=null);
    return sessionPromise;
  }
  async function request(path, {method='GET',json,form,signal}={}) {
    const headers={}; let body;
    if(method!=='GET') { const value=await getSession(); headers['X-CSRF-Token']=value.csrf_token; }
    if(json!==undefined){ headers['Content-Type']='application/json'; body=JSON.stringify(json); }
    if(form)body=form;
    return response(path,{method,headers,body,signal});
  }
  function showError(error) {
    const box=el('upload-errors'); if(!box) return;
    const issues=Array.isArray(error.issues)?error.issues:[];
    box.className='alert danger'; box.hidden=false;
    box.innerHTML=`<h3>Validation or confirmation failed</h3><p>${escape(window.MarginGuardContext.friendlyError(error))}</p>${issues.length?`<ul>${issues.map(i=>`<li>Line ${escape(i.line??'—')} · ${escape(window.MarginGuardContext.fieldLabel(i.field||'CSV'))}: ${escape(window.MarginGuardContext.businessText(i.message))}</li>`).join('')}</ul>`:''}`;
  }
  function showReport(data) {
    pending=data;
    const box=el('upload-report'),summary=data.report.summary;
    box.hidden=false;
    box.innerHTML=`<h3>Review data quality</h3><p>Your selected currency: ${escape(data.report.currency)} · Source not independently verified.</p><p>${escape(summary.row_count)} records · ${escape(summary.product_count)} products · ${escape(summary.store_count)} stores · ${escape(summary.series_count)} combinations. No duplicate records accepted. Select and confirm complete history for each included series.</p>
      <div class="table-scroll"><table><thead><tr><th>Include / product / store</th><th>Quality</th><th>Continuous history</th><th>Start</th><th>End</th></tr></thead><tbody>${data.series.map((s,index)=>{
        const ranges=(s.continuous_ranges||[]).filter(r=>r.days>=42), chosen=ranges[ranges.length-1];
        return `<tr data-review-index="${index}"><td><label class="check-row"><input class="include-series" type="checkbox" ${chosen?'checked':'disabled'}>${escape(s.item_id)} / ${escape(s.store_id)}</label></td><td>${escape(s.recorded_days??'—')} recorded days<br>${escape((s.missing_dates||[]).length)} missing; ${escape((s.unknown_sales_dates||[]).length)} unknown<br>${escape(s.zero_sales_days??0)} explicit zero days<br>Missing price / cost: ${escape(s.price_missing_days??'—')} / ${escape(s.cost_missing_days??'—')}${(s.warnings||[]).includes('no_positive_sales_evidence')?'<br><strong>No positive sales evidence</strong>':''}</td><td><select class="review-range" ${chosen?'':'disabled'} aria-label="Continuous history for ${escape(s.item_id)} ${escape(s.store_id)}">${ranges.length?ranges.map((r,i)=>`<option value="${i}" ${i===ranges.length-1?'selected':''}>${escape(r.start_date)} — ${escape(r.end_date)} · ${r.days} days</option>`).join(''):'<option>No complete 42-day history</option>'}</select></td><td><input type="date" class="review-start" value="${chosen?.start_date||''}" ${chosen?'':'disabled'} aria-label="History start for ${escape(s.item_id)} ${escape(s.store_id)}"></td><td><input type="date" class="review-end" value="${chosen?.end_date||''}" ${chosen?'':'disabled'} aria-label="History end for ${escape(s.item_id)} ${escape(s.store_id)}"></td></tr>`;
      }).join('')}</tbody></table></div><p>Your selected dates are checked again before analysis. A shorter explicit window excludes other records; its forecast starts after that window. Prices/costs are historical references, not current stock costs or future quotations.</p>
      <details><summary>Preview first ${data.preview.length} records</summary><div class="table-scroll"><table><thead><tr>${['Date','Product','Store','Units sold','Unit price','Unit cost'].map(v=>`<th>${v}</th>`).join('')}</tr></thead><tbody>${data.preview.map(row=>`<tr>${['date','product','store','units_sold','unit_price','unit_cost'].map(k=>`<td>${escape(row[k]===null?'Unknown':row[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>
      <div class="form-actions"><button type="button" class="primary" id="confirm-upload">Confirm selected history</button><button type="button" class="secondary" id="cancel-upload">Discard pending upload</button></div><p>Confirming this upload replaces the sales data currently in this temporary session. Previous analyses will no longer be available.</p>`;
    box.querySelectorAll('[data-review-index]').forEach(tr=>{
      const series=data.series[Number(tr.dataset.reviewIndex)],ranges=series.continuous_ranges.filter(r=>r.days>=42);
      tr.querySelector('.review-range').onchange=event=>{const range=ranges[Number(event.target.value)];tr.querySelector('.review-start').value=range.start_date;tr.querySelector('.review-end').value=range.end_date;};
    });
    el('confirm-upload').onclick=confirmUpload;
    el('cancel-upload').onclick=async()=>{try{await request(`/api/business/uploads/${encodeURIComponent(pending.upload_id)}`,{method:'DELETE'});pending=null;box.hidden=true;el('upload-status').textContent='Pending upload discarded.';}catch(error){showError(error);}};
  }
  async function confirmUpload() {
    const selections=[];
    el('upload-report').querySelectorAll('[data-review-index]').forEach(tr=>{
      if(tr.querySelector('.include-series').checked)selections.push({series_id:pending.series[Number(tr.dataset.reviewIndex)].series_id,start_date:tr.querySelector('.review-start').value,end_date:tr.querySelector('.review-end').value});
    });
    if(!selections.length){showError(Error('Select at least one product and store with 42 consecutive known sales days.'));return;}
    const button=el('confirm-upload');button.disabled=true;
    try {
      const data=await request(`/api/business/uploads/${encodeURIComponent(pending.upload_id)}/confirm`,{method:'POST',json:{revision:pending.revision,selections}});
      pending=null;el('upload-report').hidden=true;el('upload-errors').hidden=true;el('upload-status').textContent='Sales history confirmed. You can now review forecasts and enter your business assumptions.';
      if(activeId&&activeId!==data.dataset_id&&callbacks.onRemoved)callbacks.onRemoved(activeId);
      activeId=data.dataset_id;session.active_dataset={dataset_id:data.dataset_id,revision:data.revision};
      if(callbacks.onConfirmed)await callbacks.onConfirmed(data);
    }catch(error){showError(error);}finally{button.disabled=false;}
  }
  function attach(options) {
    callbacks=options;
    const form=el('upload-form');
    if(form)form.onsubmit=async event=>{
      event.preventDefault();if(!form.reportValidity())return;
      const file=el('csv-file').files[0];if(!file)return;
      if(file.size>5*1024*1024){showError(Object.assign(Error('CSV exceeds 5 MiB.'),{code:'file_too_large'}));return;}
      const button=form.querySelector('button[type=submit]');button.disabled=true;el('upload-errors').hidden=true;el('upload-report').hidden=true;pending=null;el('upload-status').textContent='Checking your sales records…';
      const data=new FormData(form);data.set('sales_basis','gross_units');data.set('authorized','true');
      try {showReport(await request('/api/business/uploads',{method:'POST',form:data}));el('upload-status').textContent='Review required. No new dataset is active yet.';el('csv-file').value='';}
      catch(error){showError(error);el('upload-status').textContent='Validation failed; no dataset confirmed.';}
      finally{button.disabled=false;}
    };
    if(el('delete-business-data'))el('delete-business-data').onclick=()=>el('delete-confirmation').hidden=false;
    if(el('cancel-delete'))el('cancel-delete').onclick=()=>el('delete-confirmation').hidden=true;
    if(el('confirm-delete'))el('confirm-delete').onclick=async()=>{
      if(!activeId)return;
      try {await request(`/api/business/datasets/${encodeURIComponent(activeId)}`,{method:'DELETE'});const removed=activeId;activeId=null;if(session)session.active_dataset=null;if(callbacks.onRemoved)callbacks.onRemoved(removed);location.assign('/?mode=business');}
      catch(error){if(callbacks.onError)callbacks.onError(error);}
    };
  }
  return {attach,request,getSession,setActive:id=>{activeId=id;}};
})();
