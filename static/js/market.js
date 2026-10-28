'use strict';
// Only UI selection, formatting and SVG geometry live here. Python supplies all statistics.
(() => {
  const byId = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  const format = value => value === null || value === undefined ? 'Unavailable' : Number(value).toLocaleString('en-AU', {maximumFractionDigits:2});
  const percent = value => value === null || value === undefined ? 'Unavailable' : `${format(value)}%`;
  const label = value => ({'Total (Household Spending Categories)':'Total household spending', 'Total (Industry)':'All retail industries', 'Non Discretionary':'Non-discretionary'}[value] || value);
  const STATES = {'New South Wales':'NSW', 'Victoria':'VIC', 'Queensland':'QLD', 'South Australia':'SA', 'Western Australia':'WA', 'Tasmania':'TAS', 'Northern Territory':'NT', 'Australian Capital Territory':'ACT'};
  const FINANCIAL = {business_sales:'Quarterly sales', inventories:'Quarter-end inventories', business_gross_operating_profits:'Business gross operating profits', wages:'Wages'};
  const COLORS = ['#3568e8', '#149983', '#bd8452'];
  const sectionRequests = new Map();
  const chartRenderers = new Map();
  let catalog = [], sourceCatalog = [], countsCache = null;

  async function api(endpoint, parameters = {}, signal) {
    const query = new URLSearchParams(parameters).toString();
    let response;
    try {
      response = await fetch(`/api/market/${endpoint}${query ? '?' + query : ''}`, {signal});
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      throw new Error('Cannot reach the MarginGuard server. Start ./start.command, then retry this section.');
    }
    let body;
    try { body = await response.json(); } catch { throw new Error('The server returned an unreadable response. Check the local server and retry.'); }
    if (!response.ok) throw new Error(body.error || 'The market data request failed.');
    return body;
  }

  async function updateSection(section, work) {
    sectionRequests.get(section)?.abort();
    const controller = new AbortController();
    sectionRequests.set(section, controller);
    byId(`${section}-error`).hidden = true;
    byId(`${section}-output`).hidden = true;
    byId(`${section}-loading`).hidden = false;
    byId(`${section}-output`).setAttribute('aria-busy', 'true');
    try {
      const render = await work(controller.signal);
      if (controller.signal.aborted) return;
      // Show the panel before measuring chart width, but only after all responses arrive.
      byId(`${section}-output`).hidden = false;
      render();
    } catch (error) {
      if (error.name === 'AbortError' || controller.signal.aborted) return;
      byId(`${section}-output`).hidden = true;
      const box = byId(`${section}-error`);
      box.innerHTML = `<span>${escape(error.message)}</span><button type="button" class="secondary">Retry</button>`;
      box.querySelector('button').onclick = () => updateSection(section, work);
      box.hidden = false;
    } finally {
      if (!controller.signal.aborted) {
        byId(`${section}-loading`).hidden = true;
        byId(`${section}-output`).setAttribute('aria-busy', 'false');
      }
    }
  }

  function options(id, values, selected, display = label) {
    byId(id).innerHTML = values.map(value => `<option value="${escape(value)}">${escape(display(value))}</option>`).join('');
    if (values.includes(selected)) byId(id).value = selected;
  }
  function distinct(values) { return [...new Set(values)]; }
  function selected(id) { return byId(id).value; }
  function matching(filters) {
    return catalog.filter(series => Object.entries(filters).every(([key, value]) => key === 'table' ? series.table_ids.includes(value) : series[key] === value));
  }
  function findSeries(filters) {
    const matches = matching(filters);
    if (matches.length !== 1) throw new Error('This selection does not identify one published ABS series. Choose a supported combination.');
    return matches[0];
  }
  function monthlyPeriods(start, end) {
    const result = [];
    let [year, month] = start.split('-').map(Number);
    while (`${year}-${String(month).padStart(2,'0')}` <= end) {
      result.push(`${year}-${String(month).padStart(2,'0')}`);
      month += 1;
      if (month > 12) { month = 1; year += 1; }
    }
    return result;
  }
  function quarterlyPeriods(start, end) {
    const result = [];
    let [year, quarter] = start.split('-Q').map(Number);
    while (`${year}-Q${quarter}` <= end) {
      result.push(`${year}-Q${quarter}`);
      quarter += 1;
      if (quarter > 4) { quarter = 1; year += 1; }
    }
    return result;
  }
  function recentStart(series, end, count) {
    const periods = series.frequency === 'monthly' ? monthlyPeriods(series.start_period, end) : quarterlyPeriods(series.start_period, end);
    return periods[Math.max(0, periods.length - count)];
  }
  function fetchSeries(series, signal, start, end) {
    return api('series', {dataset_id:series.dataset_id, series_id:series.series_id, ...(start ? {start} : {}), ...(end ? {end} : {})}, signal);
  }
  function sourceName(source) {
    const dataset = {abs_mhsi:'MHSI', abs_business_indicators:'Business Indicators', abs_business_counts:'Business Counts'}[source.dataset_id] || 'ABS';
    return `${dataset} · ${source.table_ids ? 'Tables ' + source.table_ids.join(', ') : 'Table ' + source.table_id}`;
  }
  function sourceLink(source) {
    if (!source.url?.startsWith('https://www.abs.gov.au/')) return escape(sourceName(source));
    return `<a href="${escape(source.url)}" target="_blank" rel="noopener">ABS ${escape(sourceName(source))} ↗</a>`;
  }
  function sources(id, list, basis = '') {
    const unique = [...new Map(list.map(source => [source.source_id, source])).values()];
    byId(id).innerHTML = `${basis ? escape(basis) + '<br>' : ''}` + unique.map(source => `<span class="source-item">${sourceLink(source)} · released ${escape(source.release_date)}</span>`).join('');
  }
  function insights(id, items, heading = false) {
    byId(id).innerHTML = `${heading ? '<span class="insight-label">BUSINESS INSIGHTS</span>' : ''}` + (items?.length ? items : ['There is insufficient published data to assess this selection.']).map(text => `<p>${escape(text)}</p>`).join('');
  }
  function summary(labelText, value, note = '') {
    return `<div><span class="summary-label">${escape(labelText)}</span><strong>${escape(value)}</strong><small>${escape(note)}</small></div>`;
  }
  function kpi(name, value, note, experimental = false, source = null) {
    return `<div class="kpi"><div class="market-kpi-label"><span class="kpi-label">${escape(name)}</span>${experimental ? '<span class="tag amber experimental-label">Experimental</span>' : ''}</div><div class="kpi-value">${escape(format(value))}</div><div class="kpi-note">${escape(note)}</div>${source ? `<div class="market-kpi-source">${sourceLink(source)}<br>Released ${escape(source.release_date)}</div>` : ''}</div>`;
  }
  function comparisonTable(id, result) {
    byId(id).innerHTML = `<table><thead><tr><th>Category / state</th><th>Reference month</th><th>${escape(result.unit)}</th><th>${escape(result.growth_label)} (%)</th></tr></thead><tbody>${result.rows.map(row => `<tr><td>${escape(row.name)}</td><td>${escape(row.period)}</td><td>${escape(format(row.value))}</td><td>${escape(percent(row.growth_pct))}</td></tr>`).join('')}</tbody></table>`;
  }

  // Charts consume supplied values. Coordinates, labels and segments are presentation only.
  function lineChart(id, periods, lines, unit, description) {
    const draw = () => {
      const container = byId(id), values = lines.flatMap(line => line.values.filter(value => value !== null && Number.isFinite(value)));
      if (!values.length) { container.innerHTML = '<div class="chart-empty">No published values for this selection. Missing observations are not zero.</div>'; return; }
      const width = Math.max(300, container.clientWidth), height = 260, left = 67, right = 15, top = 29, bottom = 34;
      let low = Math.min(...values), high = Math.max(...values);
      const padding = (high - low || Math.abs(high) || 1) * 0.12;
      low = low >= 0 ? Math.max(0, low - padding) : low - padding;
      high += padding;
      const x = index => left + index / Math.max(1, periods.length - 1) * (width - left - right);
      const y = value => top + (high - value) / (high - low) * (height - top - bottom);
      let content = `<text class="axis-unit" x="${left}" y="13">${escape(unit)}</text>`;
      for (let tick = 0; tick <= 4; tick += 1) {
        const value = low + (high - low) * tick / 4;
        content += `<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="#e7edf5"/><text x="${left-8}" y="${y(value)+3}" text-anchor="end">${escape(format(value))}</text>`;
      }
      lines.forEach((line, index) => {
        let path = '', connected = false, segments = 0;
        line.values.forEach((value, position) => {
          if (value === null || !Number.isFinite(value)) { connected = false; return; }
          if (!connected) segments += 1;
          path += `${connected ? 'L' : 'M'}${x(position).toFixed(2)},${y(value).toFixed(2)} `;
          connected = true;
        });
        content += `<path d="${path}" fill="none" stroke="${COLORS[index % COLORS.length]}" stroke-width="2.2" stroke-linecap="round" data-segments="${segments}" data-null-count="${line.values.filter(value=>value===null).length}"/>`;
        if (periods.length <= 48) line.values.forEach((value, position) => {
          if (value !== null && Number.isFinite(value)) content += `<circle cx="${x(position)}" cy="${y(value)}" r="2.5" fill="${COLORS[index % COLORS.length]}"><title>${escape(periods[position])} · ${escape(line.name)}: ${escape(format(value))} ${escape(unit)}</title></circle>`;
        });
      });
      distinct([0, Math.floor((periods.length - 1)/2), periods.length-1]).forEach(index => {
        content += `<text x="${x(index)}" y="${height-8}" text-anchor="${index===0?'start':index===periods.length-1?'end':'middle'}">${escape(periods[index])}</text>`;
      });
      container.innerHTML = `<svg class="market-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(description)}"><title>${escape(description)} · ${escape(unit)}</title>${content}</svg><div class="market-legend">${lines.map((line,index)=>`<span><i style="background:${COLORS[index % COLORS.length]}"></i>${escape(line.name)}</span>`).join('')}<span>Gaps = unavailable</span></div>`;
    };
    chartRenderers.set(id, draw); draw();
  }
  function wrapWords(text, maxCharacters) {
    const lines = []; let current = '';
    String(text).split(' ').forEach(word => {
      if (current && (current + ' ' + word).length > maxCharacters) { lines.push(current); current = word; }
      else current += (current ? ' ' : '') + word;
    });
    if (current) lines.push(current);
    return lines;
  }
  function barChart(id, rows, unit, description, field = 'growth_pct') {
    const draw = () => {
      const container = byId(id), width = Math.max(300, container.clientWidth), left = width < 420 ? 137 : 196, right = 57, top = 29;
      const values = rows.map(row=>row[field]).filter(value=>value !== null && Number.isFinite(value));
      if (!values.length) { container.innerHTML = '<div class="chart-empty">No comparable values are available. A ranking cannot be assessed.</div>'; return; }
      const low = Math.min(0,...values), high = Math.max(0,...values), range = high-low || 1;
      const x = value=>left+(value-low)/range*(width-left-right);
      const wrapped = rows.map(row=>wrapWords(STATES[row.name] ? `${STATES[row.name]} · ${row.name}` : row.name, width<420?23:32));
      const rowHeights = wrapped.map(lines=>Math.max(40,lines.length*12+12));
      const height = top + rowHeights.reduce((a,b)=>a+b,0)+27;
      let cursor=top, content=`<text class="axis-unit" x="${left}" y="13">${escape(unit)}</text><line x1="${x(0)}" x2="${x(0)}" y1="${top-8}" y2="${height-24}" stroke="#d8e2ee"/>`;
      rows.forEach((row,index)=>{
        const value=row[field], center=cursor+rowHeights[index]/2;
        wrapped[index].forEach((text,line)=>content+=`<text class="bar-label" x="0" y="${center-(wrapped[index].length-1)*6+line*12+3}">${escape(text)}</text>`);
        if(value===null || !Number.isFinite(value)) content+=`<text x="${left+3}" y="${center+3}">Unavailable</text>`;
        else {
          content+=`<rect x="${Math.min(x(0),x(value))}" y="${center-8}" width="${Math.max(1,Math.abs(x(value)-x(0)))}" height="16" rx="3" fill="${value<0?'#bd5867':'#3568e8'}"><title>${escape(row.name)}: ${escape(format(value))} ${escape(unit)}</title></rect><text class="bar-value" x="${width-3}" y="${center+4}" text-anchor="end">${escape(format(value))}${unit==='%'?'%':''}</text>`;
        }
        cursor+=rowHeights[index];
      });
      container.innerHTML=`<svg class="market-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(description)}"><title>${escape(description)} · ${escape(unit)}</title>${content}</svg>`;
    };
    chartRenderers.set(id,draw); draw();
  }

  function loadOverview() {
    return updateSection('overview', async signal => {
      const result=await api('overview',{},signal);
      return () => {
        byId('market-kpis').innerHTML=result.kpis.map(row=>kpi(row.label,row.value,`${row.unit} · ${row.period} · ${row.adjustment}`,row.experimental,result.sources.find(source=>row.source_ids.includes(source.source_id)))).join('');
        sources('overview-sources',result.sources,'Reference periods differ by source. Monthly and quarterly values are not one common-period snapshot.');
      };
    });
  }
  function loadConsumer() {
    return updateSection('consumer',async signal=>{
      const adjustment=selected('consumer-adjustment'), category=selected('consumer-metric'), start=selected('consumer-start'), end=selected('consumer-end');
      if(start>end) throw new Error('From month must be on or before To month.');
      const base={dataset_id:'abs_mhsi',table:1,measure:'household_spending',adjustment,geography:'Australia'};
      const [result,goods,services]=await Promise.all([category,'Goods','Services'].map(category=>fetchSeries(findSeries({...base,category}),signal,start,end)));
      return()=>{
        byId('consumer-summary').innerHTML=summary('Selected month',format(result.latest.value),`${end} · AUD million`)+summary('Month-on-month',percent(result.latest.period_change_pct),adjustment)+summary('Year-on-year',percent(result.latest.year_change_pct),'Calculated from published levels');
        byId('consumer-chart-title').textContent=`${label(category)} · ${adjustment}`;
        lineChart('consumer-chart',result.series.periods,[{name:label(category),values:result.series.values}],result.series.unit,`${label(category)} ${start} to ${end}`);
        lineChart('goods-services-chart',goods.series.periods,[{name:'Goods',values:goods.series.values},{name:'Services',values:services.series.values}],goods.series.unit,`Goods and services · ${adjustment}`);
        insights('consumer-insights',result.insights);
        sources('consumer-sources',result.sources,`${start} to ${end} · ${adjustment} · Current prices · Monthly`);
      };
    });
  }
  function loadIndustry(section) {
    return updateSection(section,async signal=>{
      const isRetail=section==='retail', period=selected(`${section}-month`), adjustment=selected(`${section}-adjustment`), category=selected(`${section}-category`), growth=selected(`${section}-growth`);
      const table=isRetail?19:2, measure=isRetail?'retail_turnover':'household_spending';
      const series=findSeries({dataset_id:'abs_mhsi',table,measure,adjustment,category,geography:'Australia'});
      const [comparison,trend]=await Promise.all([api('compare',{dataset_id:'abs_mhsi',table_id:String(table),measure,adjustment,period,growth,group:'category',geography:'Australia'},signal),fetchSeries(series,signal,recentStart(series,period,24),period)]);
      return()=>{
        barChart(`${section}-chart`,comparison.rows,'%',`${comparison.growth_label} category comparison · ${period}`);
        insights(`${section}-insights`,comparison.insights,true);
        byId(`${section}-trend-title`).textContent=`${label(category)} · ${adjustment} · ${isRetail?'Experimental · ':''}AUD million`;
        lineChart(`${section}-trend`,trend.series.periods,[{name:label(category),values:trend.series.values}],trend.series.unit,`${category} history ending ${period}${isRetail?' · Experimental':''}`);
        comparisonTable(`${section}-table`,comparison);
        sources(`${section}-sources`,comparison.sources,`${period} · ${comparison.growth_label} · ${adjustment} · ${isRetail?'Experimental · ANZSIC retail groups':'COICOP consumption categories'}`);
      };
    });
  }
  function loadStates() {
    return updateSection('states',async signal=>{
      const period=selected('states-month'),category=selected('states-category'),adjustment=selected('states-adjustment'), geography=selected('states-state');
      const series=findSeries({dataset_id:'abs_mhsi',measure:'household_spending',category,adjustment,geography});
      const [comparison,trend]=await Promise.all([api('compare',{dataset_id:'abs_mhsi',table_id:'states',measure:'household_spending',adjustment,period,growth:'year',group:'geography',category},signal),fetchSeries(series,signal,recentStart(series,period,24),period)]);
      return()=>{
        barChart('states-chart',comparison.rows,'%',`State year-on-year growth · ${period} · ${label(category)}`);
        insights('states-insights',comparison.insights);
        byId('states-trend-title').textContent=`${STATES[geography]} · ${label(category)} · year-on-year growth`;
        lineChart('states-trend',trend.series.periods,[{name:geography,values:trend.series.derived.year_change_pct}],'%',`${geography} year-on-year growth ending ${period}`);
        comparisonTable('states-table',comparison);
        sources('states-sources',comparison.sources,`${period} · ${label(category)} · ${adjustment} · Year-on-year growth, not spending-size ranking`);
      };
    });
  }
  function loadFinancial() {
    return updateSection('financial',async signal=>{
      const period=selected('financial-quarter'),adjustment=selected('financial-adjustment'),measure=selected('financial-metric');
      const results=await Promise.all(Object.keys(FINANCIAL).map(metric=>{
        const series=findSeries({dataset_id:'abs_business_indicators',measure:metric,category:'Retail trade',adjustment});
        return fetchSeries(series,signal,recentStart(series,period,20),period);
      }));
      const result=results.find(result=>result.series.measure===measure);
      return()=>{
        byId('financial-kpis').innerHTML=results.map(result=>kpi(FINANCIAL[result.series.measure],result.latest.value,`${period} · AUD million · ${adjustment}`)).join('');
        byId('financial-chart-title').textContent=`${FINANCIAL[measure]} · ${adjustment}`;
        lineChart('financial-chart',result.series.periods,[{name:FINANCIAL[measure],values:result.series.values}],result.series.unit,`${FINANCIAL[measure]} ending ${period}`);
        insights('financial-insights',result.insights);
        sources('financial-sources',results.flatMap(result=>result.sources),`${period} · ${adjustment} · Current prices · Australia · ANZSIC Retail trade · TOTAL scope`);
      };
    });
  }
  function loadRatio() {
    return updateSection('ratio',async signal=>{
      const series=findSeries({dataset_id:'abs_business_indicators',measure:'inventory_to_sales_ratio',category:'Retail trade',adjustment:'Original'});
      const result=await fetchSeries(series,signal);
      return()=>{
        byId('ratio-summary').innerHTML=summary('Latest official ratio',format(result.latest.value),`${result.latest.period} · Original · dimensionless`)+summary('Quarter-on-quarter difference',format(result.latest.period_delta),'Ratio units · not a percentage');
        lineChart('ratio-chart',result.series.periods,[{name:'Official inventory-to-sales ratio',values:result.series.values}],'Ratio',`Official quarterly retail inventory-to-sales ratio · Original`);
        insights('ratio-insights',result.insights);
        sources('ratio-sources',result.sources,`${result.series.periods[0]} to ${result.latest.period} · Original · Current-price components`);
      };
    });
  }
  function renderCounts(result) {
    const row=result.annual_flows.observations[0],cohort=result.survival_cohorts.find(cohort=>cohort.cohort_type===selected('counts-cohort'));
    byId('counts-kpis').innerHTML=kpi('Retail businesses',row.closing,`At ${row.period_end} · businesses`)+kpi('Business entries',row.entries_total,`${row.period} financial year · businesses`)+kpi('Business exits',row.exits_total,`${row.period} financial year · businesses`)+kpi('Net change',row.derived_net_change,`${row.period} financial year · businesses`);
    barChart('counts-flow-chart',[{name:'Business entries',value:row.entries_total},{name:'Business exits',value:row.exits_total}],'Businesses',`Business entries and exits · ${row.period}`,'value');
    const cohortLabel=cohort.cohort_type==='existing_businesses'?'Existing businesses':'New entrants';
    byId('counts-survival-title').textContent=`${cohortLabel} · ${cohort.cohort_period} cohort`;
    lineChart('counts-survival-chart',cohort.observations.map(row=>row.period),[{name:'Official survival rate',values:cohort.observations.map(row=>row.official_survival_rate_pct)}],'%',`${cohortLabel} survival · fixed ${cohort.cohort_period} cohort`);
    byId('counts-cohort-note').textContent=`Fixed starting cohort: ${format(cohort.cohort_size)} businesses (${cohort.cohort_period}). Survival observations are annual snapshots, independent of the flow financial-year selector.`;
    insights('counts-insights',result.insights,true);
    byId('counts-table').innerHTML=`<table><thead><tr><th>Fixed cohort</th><th>Starting businesses</th><th>Latest snapshot</th><th>Surviving businesses</th><th>Official survival rate</th></tr></thead><tbody>${result.survival_cohorts.map(cohort=>{const latest=cohort.observations.at(-1);return `<tr><td>${escape(cohort.cohort_type==='existing_businesses'?'Existing · '+cohort.cohort_period:'Entrants · '+cohort.cohort_period)}</td><td>${escape(format(cohort.cohort_size))}</td><td>${escape(latest.period)}</td><td>${escape(format(latest.surviving_businesses))}</td><td>${escape(percent(latest.official_survival_rate_pct))}</td></tr>`;}).join('')}</tbody></table>`;
    sources('counts-sources',[result.source],`Flows: ${row.period} financial year · Survival: separate annual snapshots · Original · ANZSIC Retail trade`);
  }
  function loadCounts() {
    return updateSection('counts',async signal=>{
      const result=await api('business-counts',{financial_year:selected('counts-year')},signal);
      return()=>{countsCache=result;renderCounts(result);};
    });
  }
  function initializeControls(countYears) {
    const mhsi=matching({dataset_id:'abs_mhsi',table:1,measure:'household_spending'}), months=monthlyPeriods(mhsi[0].start_period,mhsi[0].end_period),last=months.at(-1);
    const adjustmentValues=['Seasonally Adjusted','Original','Trend'];
    ['consumer','categories','retail','states'].forEach(section=>options(`${section}-adjustment`,adjustmentValues,'Seasonally Adjusted',value=>value));
    options('consumer-metric',distinct(mhsi.map(series=>series.category)),'Total (Household Spending Categories)');
    options('consumer-start',months,months[Math.max(0,months.length-36)]);
    options('consumer-end',months,last);
    ['categories','retail','states'].forEach(section=>options(`${section}-month`,[...months].reverse(),last));
    options('categories-category',distinct(matching({dataset_id:'abs_mhsi',table:2,measure:'household_spending',classification:'COICOP'}).map(series=>series.category)).sort(),'Food');
    options('retail-category',distinct(matching({dataset_id:'abs_mhsi',table:19,measure:'retail_turnover',geography:'Australia'}).map(series=>series.category)).sort(),'Food retailing');
    options('states-category',distinct(matching({dataset_id:'abs_mhsi',table:3,measure:'household_spending'}).map(series=>series.category)).sort(),'Total (Household Spending Categories)');
    options('states-state',Object.keys(STATES),'New South Wales',state=>`${STATES[state]} — ${state}`);
    const financial=matching({dataset_id:'abs_business_indicators',category:'Retail trade'}).filter(series=>Object.keys(FINANCIAL).includes(series.measure));
    const allAdjustments=['Original','Seasonally Adjusted'].filter(adjustment=>Object.keys(FINANCIAL).every(measure=>financial.some(series=>series.adjustment===adjustment && series.measure===measure)));
    options('financial-adjustment',allAdjustments,'Original',value=>value);
    options('financial-metric',Object.keys(FINANCIAL),'business_sales',value=>FINANCIAL[value]);
    const firstQuarter=financial.map(series=>series.start_period).sort().at(-1),lastQuarter=financial.map(series=>series.end_period).sort()[0];
    options('financial-quarter',quarterlyPeriods(firstQuarter,lastQuarter).reverse(),lastQuarter);
    options('counts-year',countYears.slice().reverse(),countYears.at(-1));
    ['consumer-metric','consumer-adjustment','consumer-start','consumer-end'].forEach(id=>byId(id).onchange=loadConsumer);
    ['categories','retail'].forEach(section=>['month','growth','adjustment','category'].forEach(suffix=>byId(`${section}-${suffix}`).onchange=()=>loadIndustry(section)));
    ['states-month','states-category','states-adjustment','states-state'].forEach(id=>byId(id).onchange=loadStates);
    ['financial-quarter','financial-metric','financial-adjustment'].forEach(id=>byId(id).onchange=loadFinancial);
    byId('counts-year').onchange=loadCounts;
    byId('counts-cohort').onchange=()=>{if(countsCache&&!byId('counts-output').hidden)renderCounts(countsCache);};
  }

  // Five workspace destinations share this page; subtopics keep their old anchors.
  const marketSections = ['market-overview', 'industry', 'states', 'financial', 'dynamics'];
  const sectionParents = {consumer:'market-overview', ratio:'financial'};
  let navigationReady = false;
  function navigateMarketSection(scroll = true) {
    const target = location.hash.slice(1);
    const subsection = Object.prototype.hasOwnProperty.call(sectionParents, target);
    const section = subsection ? sectionParents[target] : (marketSections.includes(target) ? target : 'market-overview');
    document.querySelectorAll('[data-market-section]').forEach(link => {
      const active = link.dataset.marketSection === section;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
    // The content is initially hidden; resolve a deep link only after data rendering.
    if (scroll && navigationReady && (marketSections.includes(target) || subsection)) {
      byId(target).scrollIntoView({block:'start', behavior:'auto'});
    }
  }
  window.addEventListener('hashchange', () => navigateMarketSection());
  document.querySelectorAll('[data-market-section]').forEach(link => {
    link.addEventListener('click', () => {
      // Clicking an already-selected anchor does not fire hashchange.
      if (link.hash === location.hash) navigateMarketSection();
    });
  });
  navigateMarketSection(false);

  let resizeTimer;
  window.addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=setTimeout(()=>chartRenderers.forEach((draw,id)=>{if(byId(id).getClientRects().length)draw();}),120);
  });
  byId('retry-connection').onclick=()=>location.reload();
  (async()=>{
    try {
      const [metadata,provenance]=await Promise.all([api('catalog'),api('sources')]);
      catalog=metadata.series;sourceCatalog=provenance.sources;
      initializeControls(metadata.counts.financial_years);
      byId('market-asof').textContent=`Prepared snapshot · ${metadata.as_of}`;
      byId('market-source-list').innerHTML=sourceCatalog.map(source=>`<div class="market-source-list-item">${sourceLink(source)}<br><small>Released ${escape(source.release_date)} · Reference cutoff ${escape(source.reference_end_date)} · Downloaded ${escape(source.download_date)} · ${escape(source.license)}</small></div>`).join('');
      byId('content').hidden=false;
      byId('loading').hidden=true;
      await Promise.all([loadOverview(),loadConsumer(),loadIndustry('categories'),loadIndustry('retail'),loadStates(),loadFinancial(),loadRatio(),loadCounts()]);
      navigationReady = true;
      navigateMarketSection();
    } catch(error) {
      byId('loading').hidden=true;
      byId('error').textContent=error.message;
      byId('error').hidden=false;
      byId('retry-connection').hidden=false;
    }
  })();
})();
