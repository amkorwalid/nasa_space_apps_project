import { STATUS, STATUS_ORDER, statusOf, classify } from './status.js';
import { changed, escapeHtml, fmt, fmtSigned, formatMonth } from './store.js';
import { createSeriesChart } from './charts.js';

const badge = (s) =>
  `<span class="status-badge" style="--c:${STATUS[s].color}"><span class="dot"></span>${STATUS[s].label}</span>`;

function download(filename, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function seriesToCSV(id, months, series) {
  const cols = ['month', 'area_km2', 'normal_km2', 'p10_km2', 'p90_km2', 'pct_of_normal', 'z_score', 'status', 'mom_change_pct', 'yoy_change_pct', 'sensor', 'n_obs', 'quality', 'official_fill_pct'];
  const lines = [['reservoir_id', ...cols].join(',')];
  for (const m of months) {
    const r = series.get(m);
    if (r) lines.push([id, ...cols.map((c) => r[c] ?? '')].join(','));
  }
  return lines.join('\n') + '\n';
}

/** Side panel: national/basin overview, or reservoir detail with chart. */
export function initPanel(el, data, store) {
  let chart = null;
  let chartFor = null;

  const select = (id) => store.set({ selectedId: id });

  function renderOverview({ month, visibleIds }) {
    chart?.destroy();
    chart = chartFor = null;
    const feats = data.reservoirs.features.filter((f) => !visibleIds || visibleIds.has(f.properties.reservoir_id));
    const counts = Object.fromEntries(STATUS_ORDER.map((s) => [s, 0]));
    const rows = feats.map((f) => {
      const id = f.properties.reservoir_id;
      const rec = data.record(id, month);
      const st = statusOf(rec);
      counts[st] += 1;
      return { f, id, rec, st };
    });

    // Basin aggregation: total area / total normal for the month
    const basins = new Map();
    for (const { f, rec } of rows) {
      const b = f.properties.basin || 'Unknown';
      const agg = basins.get(b) || { n: 0, area: 0, normal: 0, cap: 0 };
      agg.n += 1;
      agg.cap += f.properties.capacity_mcm || 0;
      if (rec && rec.quality !== 'bad') {
        agg.area += rec.area_km2;
        agg.normal += rec.normal_km2;
      }
      basins.set(b, agg);
    }

    const total = rows.length || 1;
    el.innerHTML = `
      <div class="panel-head">
        <p class="eyebrow">National overview · ${formatMonth(month)}</p>
        <h2>${rows.length} monitored water bod${rows.length === 1 ? 'y' : 'ies'}</h2>
        ${data.isMock ? '<p class="note">Showing illustrative <strong>mock data</strong> for Al Wahda while the radar pipeline runs.</p>' : ''}
      </div>
      <section class="panel-section">
        <h3>Status this month</h3>
        <div class="status-bar" role="img" aria-label="Status distribution">
          ${STATUS_ORDER.filter((s) => counts[s])
            .map((s) => `<span style="flex:${counts[s]};background:${STATUS[s].color}" title="${STATUS[s].label}: ${counts[s]}"></span>`)
            .join('')}
        </div>
        <ul class="status-counts">
          ${STATUS_ORDER.filter((s) => counts[s])
            .map((s) => `<li>${badge(s)}<span>${counts[s]} <small>(${Math.round((counts[s] / total) * 100)}%)</small></span></li>`)
            .join('')}
        </ul>
      </section>
      <section class="panel-section">
        <h3>Basins</h3>
        <table class="basin-table">
          <thead><tr><th>Basin</th><th>Reservoirs</th><th>% of normal</th></tr></thead>
          <tbody>
            ${[...basins.entries()]
              .map(([name, a]) => {
                const pct = a.normal ? (a.area / a.normal) * 100 : null;
                return `<tr><td>${escapeHtml(name)}</td><td>${a.n}</td><td>${badge(classify(pct))} ${fmt(pct, 0, '%')}</td></tr>`;
              })
              .join('')}
          </tbody>
        </table>
      </section>
      <section class="panel-section">
        <h3>Reservoirs</h3>
        <ul class="reservoir-list">
          ${rows
            .sort((a, b) => (b.f.properties.capacity_mcm || 0) - (a.f.properties.capacity_mcm || 0))
            .map(
              ({ f, id, rec, st }) => `
            <li><button type="button" data-id="${escapeHtml(id)}">
              <span class="swatch" style="background:${STATUS[st].color}"></span>
              <span class="r-name">${escapeHtml(f.properties.name)}<small>${escapeHtml(f.properties.basin || '')} · ${fmt(f.properties.capacity_mcm, 0)} Mm³</small></span>
              <span class="r-pct">${rec ? fmt(rec.pct_of_normal, 0, '%') : '—'}</span>
            </button></li>`,
            )
            .join('')}
        </ul>
      </section>`;
  }

  function renderDetail({ selectedId: id, month }) {
    const f = data.byId.get(id);
    if (!f) return select(null);
    const p = f.properties;
    const series = data.series[id] || new Map();
    const rec = series.get(month);
    const st = statusOf(rec);

    if (chartFor !== id) {
      chart?.destroy();
      chart = null;
      el.innerHTML = `
        <div class="panel-head">
          <button type="button" class="link back" data-action="back">← Overview</button>
          <p class="eyebrow">${escapeHtml(p.basin || '')} basin${p.river ? ` · ${escapeHtml(p.river)} river` : ''}</p>
          <h2>${escapeHtml(p.name)}</h2>
          <dl class="facts">
            <div><dt>Capacity</dt><dd>${fmt(p.capacity_mcm, 0)} Mm³</dd></div>
            <div><dt>Dam year</dt><dd>${p.dam_year ?? '—'}</dd></div>
            <div><dt>Max area</dt><dd>${fmt(p.polygon_area_km2, 1)} km²</dd></div>
            <div><dt>Confidence</dt><dd>${escapeHtml(p.confidence || '—')}</dd></div>
          </dl>
        </div>
        <section class="panel-section" id="month-card"></section>
        <section class="panel-section">
          <h3>Monthly water area</h3>
          <div class="chart-box">${series.size ? '<canvas id="series-chart" aria-label="Monthly water area time series"></canvas>' : '<p class="empty">No time series available for this reservoir yet.</p>'}</div>
          <p class="hint">Click a point to jump to that month.</p>
        </section>
        <section class="panel-section actions">
          <button type="button" class="btn small" data-action="zoom">Zoom to reservoir</button>
          <button type="button" class="btn small" data-action="csv" ${series.size ? '' : 'disabled'}>Download CSV</button>
          <button type="button" class="btn small" data-action="geojson">Download GeoJSON</button>
          <p class="id-line">ID <code>${escapeHtml(id)}</code></p>
        </section>`;
      const canvas = el.querySelector('#series-chart');
      if (canvas) chart = createSeriesChart(canvas, { months: data.months, series, month, onPickMonth: (m) => store.set({ month: m }) });
      chartFor = id;
    } else {
      chart?.setMonth(month);
    }

    const card = el.querySelector('#month-card');
    if (!rec) {
      card.innerHTML = `<h3>${formatMonth(month)}</h3>${badge('no_data')}<p class="empty">No radar observation for this month.</p>`;
      return;
    }
    const warn =
      rec.quality && rec.quality !== 'good'
        ? `<p class="warn">⚠ ${rec.quality === 'partial' ? 'Partial' : 'Low-quality'} month: only ${rec.n_obs ?? '?'} usable scene(s). Interpret with care.</p>`
        : '';
    card.innerHTML = `
      <div class="month-head"><h3>${formatMonth(month)}</h3>${badge(st)}</div>
      <div class="kpis">
        <div class="kpi"><span class="kpi-v">${fmt(rec.area_km2, 1)}<small> km²</small></span><span class="kpi-l">Water area</span></div>
        <div class="kpi"><span class="kpi-v" style="color:${STATUS[st].color}">${fmt(rec.pct_of_normal, 0)}<small>%</small></span><span class="kpi-l">of normal (${fmt(rec.normal_km2, 1)} km²)</span></div>
        <div class="kpi"><span class="kpi-v">${fmtSigned(rec.mom_change_pct)}</span><span class="kpi-l">vs last month</span></div>
        <div class="kpi"><span class="kpi-v">${fmtSigned(rec.yoy_change_pct)}</span><span class="kpi-l">vs last year</span></div>
      </div>
      <dl class="facts small">
        <div><dt>Official fill</dt><dd>${fmt(rec.official_fill_pct, 1, '%')}</dd></div>
        <div><dt>z-score</dt><dd>${fmtSigned(rec.z_score, 2, '')}</dd></div>
        <div><dt>Sensor</dt><dd>${rec.sensor === 'S1' ? 'Sentinel-1' : escapeHtml(rec.sensor || '—')}</dd></div>
        <div><dt>Scenes</dt><dd>${rec.n_obs ?? '—'}</dd></div>
      </dl>
      ${warn}`;
  }

  function render(state) {
    el.classList.toggle('has-selection', Boolean(state.selectedId));
    if (state.selectedId) renderDetail(state);
    else renderOverview(state);
  }

  el.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    if (btn.dataset.id) return select(btn.dataset.id);
    const id = store.get().selectedId;
    switch (btn.dataset.action) {
      case 'back':
        return select(null);
      case 'zoom':
        return store.set({ flyTo: { id, t: Date.now() } });
      case 'csv':
        return download(`${id}_timeseries.csv`, seriesToCSV(id, data.months, data.series[id]), 'text/csv');
      case 'geojson':
        return download(`${id}.geojson`, JSON.stringify({ type: 'FeatureCollection', features: [data.byId.get(id)] }, null, 2), 'application/geo+json');
    }
  });

  store.subscribe((s, prev) => {
    if (changed(s, prev, 'selectedId', 'month', 'visibleIds')) render(s);
  });
  render(store.get());
}
