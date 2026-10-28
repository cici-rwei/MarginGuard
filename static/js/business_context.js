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
  return {create,key,sanitize,fields};
});
