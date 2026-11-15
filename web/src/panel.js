import { STATUS, STATUS_ORDER, statusOf, classify } from './status.js';
import { changed, escapeHtml, fmt, fmtSigned, formatMonth } from './store.js';
import { createSeriesChart } from './charts.js';
import { t } from './i18n.js';

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
  const cols = ['month', 'area_km2', 'normal_km2', 'p10_km2', 'p90_km2', 'pct_of_normal', 'z_score', 'status', 'mom_change_pct', 'yoy_change_pct', 'sensor', 'n_obs', 'quality', 'official_fill_pct', 'est_fill_pct'];
  const lines = [['reservoir_id', ...cols].join(',')];
  for (const m of months) {
    const r = series.get(m);
    if (r) lines.push([id, ...cols.map((c) => r[c] ?? '')].join(','));
  }
  return lines.join('\n') + '\n';
}

/** Small inline SVG: national water area (line) against normal (dashed), selected month marked. */
function nationalSpark(national, months, month) {
  const rows = months.map((m) => national.find((r) => r.month === m) || null);
  const vals = rows.flatMap((r) => (r ? [r.area_km2, r.normal_km2] : []));
  if (vals.length < 4) return '';
  const W = 300;
  const H = 70;
  const lo = Math.min(...vals) * 0.95;
  const hi = Math.max(...vals) * 1.03;
  const x = (i) => (i / Math.max(months.length - 1, 1)) * W;
  const y = (v) => H - ((v - lo) / (hi - lo)) * H;
  const path = (k) =>
    rows
      .map((r, i) => (r ? `${x(i).toFixed(1)},${y(r[k]).toFixed(1)}` : null))
      .filter(Boolean)
      .map((p, i) => `${i ? 'L' : 'M'}${p}`)
      .join('');
  const i = months.indexOf(month);
  return `<svg class="spark" viewBox="0 0 ${W} ${H + 4}" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(t('nationalTrend'))}">
      <path d="${path('normal_km2')}" fill="none" stroke="#2a9d5c" stroke-width="1.5" stroke-dasharray="5 4"/>
      <path d="${path('area_km2')}" fill="none" stroke="#1e5fbf" stroke-width="2.2"/>
      ${i >= 0 ? `<line x1="${x(i)}" x2="${x(i)}" y1="0" y2="${H}" stroke="#111827" stroke-opacity=".5" stroke-dasharray="3 3"/>` : ''}
    </svg>`;
}

/** Side panel: national/basin overview, or reservoir detail with chart. */
export function initPanel(el, data, store) {
  let chart = null;
  let chartFor = null;

  const select = (id) => store.set({ selectedId: id });

  function renderOverview({ month, visibleIds }) {
    chart?.destroy();
    chart = chartFor = null;
    const all = data.reservoirs.features.filter((f) => !visibleIds || visibleIds.has(f.properties.reservoir_id));
    const feats = all.filter((f) => data.isMonitored(f));
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
    for (const { f, rec, st } of rows) {
      const b = f.properties.basin || 'Unknown';
      const agg = basins.get(b) || { n: 0, area: 0, normal: 0, cap: 0 };
      agg.n += 1;
      agg.cap += f.properties.capacity_mcm || 0;
      if (rec && st !== 'no_data' && rec.normal_km2) {
        agg.area += rec.area_km2;
        agg.normal += rec.normal_km2;
      }
      basins.set(b, agg);
    }
    const rain = (b) => (data.rainfall[b] || []).find((r) => r.month === month);
    const hasRain = Object.keys(data.rainfall).length > 0;

    const nat = data.national.find((r) => r.month === month);
    const alerts = data.alerts.filter((a) => a.month === month);
    const total = rows.length || 1;
    el.innerHTML = `
      <div class="panel-head">
        <p class="eyebrow">${t('overview')} · ${formatMonth(month)}</p>
        <h2>${t('monitored', { n: rows.length })}</h2>
        ${data.isMock ? `<p class="note">${t('mockNote')}</p>` : `<p class="hint">${t('catalogNote', { n: data.reservoirs.features.length })}</p>`}
      </div>
      ${
        data.national.length
          ? `<section class="panel-section">
        <h3>${t('nationalTrend')}</h3>
        ${nat ? `<p class="nat-now">${badge(nat.status)} ${t('nationalNow', { pct: fmt(nat.pct_of_normal, 0, '%'), n: nat.n })}</p>` : ''}
        ${nationalSpark(data.national, data.months, month)}
      </section>`
          : ''
      }
      <section class="panel-section">
        <h3>${t('statusMonth')}</h3>
        <div class="status-bar" role="img" aria-label="${escapeHtml(t('statusMonth'))}">
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
      ${
        month === data.months[data.months.length - 1] && !data.isMock
          ? `<section class="panel-section">
        <h3>🔔 ${t('alerts')}</h3>
        ${
          alerts.length
            ? `<ul class="alert-list">${alerts
                .map((a) => `<li><button type="button" data-id="${escapeHtml(a.reservoir_id)}">${escapeHtml(a.name)}: ${badge(a.from)} → ${badge(a.to)}</button></li>`)
                .join('')}</ul>`
            : `<p class="empty">${t('noAlerts')}</p>`
        }
      </section>`
          : ''
      }
      <section class="panel-section">
        <h3>${t('basins')}</h3>
        <table class="basin-table">
          <thead><tr><th>${t('basin')}</th><th>${t('reservoirs')}</th><th>${t('pctNormal')}</th>${hasRain ? `<th>${t('rain12')}</th>` : ''}</tr></thead>
          <tbody>
            ${[...basins.entries()]
              .sort((a, b) => b[1].cap - a[1].cap)
              .map(([name, a]) => {
                const pct = a.normal ? (a.area / a.normal) * 100 : null;
                const r = rain(name);
                return `<tr><td>${escapeHtml(name)}</td><td>${a.n}</td><td>${badge(classify(pct))} ${fmt(pct, 0, '%')}</td>${
                  hasRain ? `<td class="${r && r.anomaly_12m_pct < 0 ? 'neg' : 'pos'}">${r ? fmtSigned(r.anomaly_12m_pct, 0) : '—'}</td>` : ''
                }</tr>`;
              })
              .join('')}
          </tbody>
        </table>
      </section>
      <section class="panel-section">
        <h3>${t('reservoirs')}</h3>
        <ul class="reservoir-list">
          ${rows
            .sort((a, b) => (b.f.properties.capacity_mcm || 0) - (a.f.properties.capacity_mcm || 0))
            .map(
              ({ f, id, rec, st }) => `
            <li><button type="button" data-id="${escapeHtml(id)}">
              <span class="swatch" style="background:${STATUS[st].color}"></span>
              <span class="r-name">${escapeHtml(f.properties.name)}<small>${escapeHtml(f.properties.basin || '')} · ${fmt(f.properties.capacity_mcm, 0)} Mm³</small></span>
              <span class="r-pct">${rec && st !== 'no_data' ? fmt(rec.pct_of_normal, 0, '%') : '—'}</span>
            </button></li>`,
            )
            .join('')}
        </ul>
      </section>
      ${
        data.isMock
          ? ''
          : `<section class="panel-section actions">
        <h3>${t('downloads')}</h3>
        <a class="btn small" href="${data.downloadUrl('status.csv')}" download>status.csv</a>
        <a class="btn small" href="${data.downloadUrl('monthly_area.csv')}" download>monthly_area.csv</a>
        <a class="btn small" href="${data.downloadUrl('reservoirs.csv')}" download>reservoirs.csv</a>
        ${data.meta.generated ? `<p class="id-line">${escapeHtml(data.meta.generated)} · ${(data.meta.sources || []).map(escapeHtml).join(' · ')}</p>` : ''}
      </section>`
      }`;
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
          <button type="button" class="link back" data-action="back">${t('back')}</button>
          <p class="eyebrow">${p.basin ? escapeHtml(t('basinOf', { b: p.basin })) : ''}${p.river ? ` · ${escapeHtml(t('river', { r: p.river }))}` : ''}</p>
          <h2>${escapeHtml(p.name)}${p.name_ar ? ` <small class="name-ar" dir="rtl">${escapeHtml(p.name_ar)}</small>` : ''}</h2>
          <dl class="facts">
            <div><dt>${t('capacity')}</dt><dd>${fmt(p.capacity_mcm, 0)} Mm³</dd></div>
            <div><dt>${t('damYear')}</dt><dd>${p.dam_year ?? '—'}</dd></div>
            <div><dt>${t('maxArea')}</dt><dd>${fmt(p.polygon_area_km2, 1)} km²</dd></div>
            <div><dt>${t('confidence')}</dt><dd>${escapeHtml(p.confidence || '—')}</dd></div>
          </dl>
        </div>
        <section class="panel-section" id="month-card"></section>
        <section class="panel-section">
          <h3>${t('monthlyArea')}</h3>
          <div class="chart-box">${series.size ? '<canvas id="series-chart" aria-label="' + escapeHtml(t('monthlyArea')) + '"></canvas>' : `<p class="empty">${t('noSeries')}</p>`}</div>
          ${series.size ? `<p class="hint">${t('clickHint')}</p>` : ''}
        </section>
        <section class="panel-section actions">
          <button type="button" class="btn small" data-action="zoom">${t('zoom')}</button>
          <button type="button" class="btn small" data-action="csv" ${series.size ? '' : 'disabled'}>${t('csv')}</button>
          <button type="button" class="btn small" data-action="geojson">${t('geojson')}</button>
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
      card.innerHTML = `<h3>${formatMonth(month)}</h3>${badge('no_data')}<p class="empty">${t('noObs')}</p>`;
      return;
    }
    const warn =
      rec.quality && rec.quality !== 'good'
        ? `<p class="warn">⚠ ${rec.quality === 'partial' ? t('partialWarn', { n: rec.n_obs ?? '?' }) : t('badWarn')}</p>`
        : '';
    const sensor = rec.sensor === 'S1' ? 'Sentinel-1' : escapeHtml(rec.sensor || '—');
    card.innerHTML = `
      <div class="month-head"><h3>${formatMonth(month)}</h3>${badge(st)}</div>
      <div class="kpis">
        <div class="kpi"><span class="kpi-v">${fmt(rec.area_km2, 1)}<small> km²</small></span><span class="kpi-l">${t('waterArea')}</span></div>
        <div class="kpi"><span class="kpi-v" style="color:${STATUS[st].color}">${fmt(rec.pct_of_normal, 0)}<small>%</small></span><span class="kpi-l">${t('ofNormal', { v: fmt(rec.normal_km2, 1) })}</span></div>
        <div class="kpi"><span class="kpi-v">${fmtSigned(rec.mom_change_pct)}</span><span class="kpi-l">${t('vsLastMonth')}</span></div>
        <div class="kpi"><span class="kpi-v">${fmtSigned(rec.yoy_change_pct)}</span><span class="kpi-l">${t('vsLastYear')}</span></div>
      </div>
      <dl class="facts small">
        <div><dt>${t('officialFill')}</dt><dd>${fmt(rec.official_fill_pct, 1, '%')}</dd></div>
        ${rec.est_fill_pct != null ? `<div><dt>${t('estFill')}</dt><dd>${fmt(rec.est_fill_pct, 0, '%')}</dd></div>` : ''}
        <div><dt>${t('zscore')}</dt><dd>${fmtSigned(rec.z_score, 2, '')}</dd></div>
        <div><dt>${t('sensor')}</dt><dd>${sensor}</dd></div>
        <div><dt>${t('scenes')}</dt><dd>${rec.n_obs ?? '—'}</dd></div>
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
