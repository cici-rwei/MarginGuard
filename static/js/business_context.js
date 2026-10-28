/* Input-only, per-tab drafts. This is UX state, never server authorization. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MarginGuardContext = api;
})(typeof window === 'object' ? window : this, function () {
  'use strict';
  const PREFIX = 'marginguard.assumptions.v1:';
  const fields = {
    inventory: ['current_stock','lead_time_days','safety_stock','on_order_units','excess_cover_days','stock_as_of','hypothetical_stock_at_origin'],
    scenarios: ['current_stock','lead_time_days','selling_price','existing_unit_cost','unit_purchase_cost','cash_budget','order_quantity','freight','other_costs','moq','discount_percent','demand_uplift_percent','max_unmet_units','stock_as_of','hypothetical_stock_at_origin','on_order_units','acknowledge_excluded_on_order']
  };
  // Presentation only: API field names and stored values remain unchanged.
  const labels = {
    current_stock:'Current stock', lead_time_days:'Supplier delivery time', safety_stock:'Backup stock',
    on_order_units:'Stock already ordered', excess_cover_days:'Excess stock warning after',
    stock_as_of:'Stock count date', hypothetical_stock_at_origin:'Hypothetical stock at forecast start',
    selling_price:'Selling price', existing_unit_cost:'Cost of stock already held',
    unit_purchase_cost:'New supplier unit cost', order_quantity:'New order quantity',
    freight:'Delivery charge', other_costs:'Other purchase charges', moq:'Minimum order quantity',
    discount_percent:'Customer discount', demand_uplift_percent:'Assumed extra demand',
    cash_budget:'Purchase budget', max_unmet_units:'Maximum unfilled demand',
    acknowledge_excluded_on_order:'Confirmation to exclude stock already ordered',
    item_id:'Product', store_id:'Store', series_id:'Product and store', dataset_id:'Uploaded dataset',
    currency:'Currency', time_zone:'Business time zone', tax_basis:'Tax treatment',
    sales_basis:'Sales quantity definition', gross_units:'sales before returns',
    units_sold:'Units sold', unit_price:'Unit price', unit_cost:'Unit cost', start_date:'History start', end_date:'History end'
  };
  function fieldLabel(name) { return labels[name] || String(name || 'CSV').replace(/_/g,' ').replace(/^./,c=>c.toUpperCase()); }
  function businessText(value) {
    let text=String(value??'');
    Object.keys(labels).sort((a,b)=>b.length-a.length).forEach(name=>{text=text.replace(new RegExp('\\b'+name+'\\b','g'),labels[name]);});
    return text.replace(/\bMOQ\b/g,'minimum order quantity')
      .replace(/\bCOGS\b/g,'cost of goods sold (COGS)')
      .replace(/\blead-time demand\b/gi,'demand during supplier delivery time')
      .replace(/\bsafety-stock target\b/gi,'backup stock target')
      .replace(/\bprocurement cash\b/gi,'cash needed for the new purchase')
      .replace(/\buser service constraint\b/gi,'maximum unfilled demand you set')
      .replace(/lost sales are not backlogged/gi,'missed sales are not carried forward as later orders')
      .replace(/holding costs/gi,'stock storage costs')
      .replace(/real-world optimum/gi,'best result for your actual business');
  }
  function friendlyError(error) {
    const guidance={
      uploads_disabled:'Analyse My Business is temporarily unavailable. You can use Synthetic Demo while private uploads are being checked.',
      file_too_large:'Choose a CSV no larger than 5 MiB. Reduce the number of products or dates, then upload again.',
      http_413:'This upload is too large. Choose one CSV no larger than 5 MiB and try again.',
      normalized_too_large:'This dataset is too large to analyse here. Include fewer products or a shorter history, keeping at least 42 complete days per selection.',
      unsupported_file_type:'Choose a .csv file saved as UTF-8. Excel workbooks and other file types are not accepted.',
      session_required:'Start a temporary session from Analyse My Business, then upload your CSV.',
      session_expired:'Your temporary session has expired. Return to Analyse My Business and upload again.',
      dataset_expired:'This temporary upload has expired. Upload the CSV again and confirm the history you want to analyse.',
      dataset_not_found:'This temporary dataset is unavailable in this browser session. Return to Analyse My Business and upload again.',
      csrf_rejected:'Your secure request check has expired. Reload this page, review your inputs and try again.',
      origin_rejected:'Open this page directly on MarginGuard, then retry your upload or calculation.',
      revision_conflict:'Your uploaded data has changed. Reload the page and select the current product and store.',
      invalid_time_zone:'Choose your business time zone, for example Australia/Sydney, then try again.',
      invalid_stock_date:'Enter a valid stock count date as YYYY-MM-DD, or confirm hypothetical stock at the forecast start.',
      stock_date_required:'Use a stock count at the end of the selected history, or tick the option to use hypothetical stock at the forecast start.',
      on_order_not_supported:'This financial model cannot schedule stock already ordered. Set that quantity to zero if there is none, or explicitly confirm a separate scenario that excludes it.',
      currency_conflict:'Use the currency selected when you uploaded this CSV for every price, cost and budget. No currency conversion is provided.',
      processing_timeout:'The calculation took too long. Try fewer products or a shorter complete history, then retry. No new result has been accepted.',
      processing_busy:'Other analyses are using the available capacity. Wait a moment, then retry; your current inputs have not been applied.',
      rate_limit:'Too many requests were made in a short time. Wait before retrying; do not repeatedly click Upload or Calculate.',
      session_capacity:'All temporary sessions are currently in use. Please try again later.',
      storage_capacity:'Temporary upload storage is full. Please try again later; no new dataset has been saved.',
      processing_failed:'The analysis could not finish within its limits. Try a smaller CSV or fewer selected products, then retry.',
      processing_unavailable:'Private analysis is temporarily unavailable. Please retry later; Synthetic Demo and Market Intelligence remain available.',
      service_unavailable:'Private analysis is temporarily unavailable. Please retry later; do not rely on an earlier result for changed inputs.',
      missing_parameter:'Complete every required input. Enter 0 only when the actual or assumed value is zero.',
      unknown_parameter:'This page and the server may be out of date. Reload MarginGuard, review the inputs and try again.',
      invalid_parameters:'Review the highlighted inputs: use non-negative amounts, whole units for stock and whole days for delivery time.',
      invalid_selection:'Select a product and store with at least 42 consecutive known sales days, and choose dates within that complete history.'
    };
    if(guidance[error?.code])return guidance[error.code];
    if(error?.status>=500)return 'MarginGuard could not complete this request. Please retry shortly. No new result is available.';
    const message=businessText(error?.message||error||'The request could not be completed.');
    if(/must be (?:finite|numeric|a whole number)|between 0|decimal places|must be greater than zero/i.test(message))return message+' Correct this input and run the calculation again.';
    return message;
  }
  function assumptionValue(name,value) {
    if(value===undefined||value===null||value==='')return 'Not entered';
    if(typeof value==='boolean')return value?'Yes':'No';
    if(name==='stock_as_of')return String(value);
    const number=Number(value);
    return Number.isFinite(number)?number.toLocaleString('en-US',{maximumFractionDigits:6})+(name==='lead_time_days'?' days':name==='current_stock'||name==='order_quantity'?' units':''):String(value);
  }
  function assumptionChanges(current,incoming) {
    return Object.entries(incoming).filter(([name,value])=>{
      const before=current[name];
      if(typeof value==='boolean'||typeof before==='boolean')return value!==before;
      if(value===''||value===null||value===undefined||before===''||before===null||before===undefined)return value!==before;
      return String(value)!==String(before)&&!(Number.isFinite(Number(value))&&Number.isFinite(Number(before))&&Number(value)===Number(before));
    }).map(([name,value])=>({name,label:fieldLabel(name),before:assumptionValue(name,current[name]),after:assumptionValue(name,value)}));
  }
  function identity(context) {
    if (!context || !['m5_demo','synthetic_demo','user_csv'].includes(context.source_kind)) throw Error('Missing analysis context.');
    const values = ['source_kind','dataset_id','revision','series_id','forecast_origin','currency'].map(k => context[k]);
    if (values.some(v => typeof v !== 'string' || !v || v.length > 300) || !['AUD','USD'].includes(context.currency)) throw Error('Invalid analysis context.');
    return values;
  }
  function key(context) { return PREFIX + encodeURIComponent(JSON.stringify(identity(context))); }
  function sanitize(section, inputs) {
    if (!fields[section] || !inputs || typeof inputs !== 'object' || Array.isArray(inputs)) return {};
    const clean = {};
    fields[section].forEach(name => {
      const value = inputs[name];
      if (typeof value === 'boolean' || typeof value === 'string' && value.length <= 128 || typeof value === 'number' && Number.isFinite(value)) clean[name] = value;
    });
    return clean;
  }
  function create(storage, onUnavailable) {
    let available = !!storage;
    function failed() { available = false; if (onUnavailable) onUnavailable(); }
    function read(context) {
      if (!available) return {};
      try {
        const value = JSON.parse(storage.getItem(key(context)) || 'null');
        if (!value || value.schema !== 1) return {};
        return {inventory:sanitize('inventory',value.inventory),scenarios:sanitize('scenarios',value.scenarios)};
      } catch (error) { if (error instanceof SyntaxError) return {}; failed(); return {}; }
    }
    function save(context, section, inputs) {
      if (!available || !fields[section]) return false;
      try { const value=read(context); if(!available)return false; value[section]=sanitize(section,inputs); storage.setItem(key(context),JSON.stringify({schema:1,...value})); return true; }
      catch (error) { failed(); return false; }
    }
    function clear(context) {
      if (!available) return;
      try { storage.removeItem(key(context)); } catch (error) { failed(); }
    }
    function clearMatching(predicate) {
      if (!available) return;
      try {
        const keys=[]; for(let i=0;i<storage.length;i++) keys.push(storage.key(i));
        keys.filter(k=>k && k.startsWith(PREFIX)).forEach(k=>{
          try { if(predicate(JSON.parse(decodeURIComponent(k.slice(PREFIX.length))))) storage.removeItem(k); }
          catch (error) { storage.removeItem(k); }
        });
      } catch (error) { failed(); }
    }
    return {read,save,clear,available:()=>available,
      clearDataset:id=>clearMatching(values=>values[0]==='user_csv'&&values[1]===id),
      clearUploads:()=>clearMatching(values=>values[0]==='user_csv')};
  }
  return {create,key,sanitize,fields,fieldLabel,businessText,friendlyError,assumptionValue,assumptionChanges};
});
