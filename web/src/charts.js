import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';
import { statusColor, statusOf } from './status.js';
import { formatMonth } from './store.js';
import { t } from './i18n.js';

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip, Legend);

/** Draws a vertical line at the selected month. */
const monthMarker = {
  id: 'monthMarker',
  afterDatasetsDraw(chart, _args, opts) {
    const idx = opts?.index;
    if (idx == null || idx < 0) return;
    const x = chart.scales.x.getPixelForValue(idx);
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = 'rgba(17,24,39,0.55)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.restore();
  },
};

/**
 * Time-series chart: water area vs normal range (p10–p90) and normal,
 * with the official fill rate on a secondary axis.
 */
export function createSeriesChart(canvas, { months, series, month, onPickMonth }) {
  const rows = months.map((m) => series.get(m));
  const val = (k) => rows.map((r) => (r && r[k] != null ? r[k] : null));
  const pointColors = rows.map((r) => statusColor(statusOf(r)));
  const hasOfficial = rows.some((r) => r?.official_fill_pct != null);
  const hasNisar = rows.some((r) => r?.area_nisar_km2 != null);

  const chart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        {
          label: t('chartRange'),
          data: val('p90_km2'),
          borderWidth: 0,
          pointRadius: 0,
          backgroundColor: 'rgba(42,157,92,0.14)',
          fill: '+1',
          order: 4,
        },
        { label: 'p10', data: val('p10_km2'), borderWidth: 0, pointRadius: 0, fill: false, order: 5 },
        {
          label: t('chartNormal'),
          data: val('normal_km2'),
          borderColor: '#2a9d5c',
          borderDash: [6, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          order: 3,
        },
        {
          label: t('chartArea'),
          data: val('area_km2'),
          borderColor: '#1e5fbf',
          backgroundColor: pointColors,
          pointBackgroundColor: pointColors,
          pointBorderColor: '#fff',
          pointBorderWidth: 1,
          pointRadius: 4,
          pointHoverRadius: 6,
          borderWidth: 2.5,
          tension: 0.25,
          spanGaps: false,
          order: 1,
        },
        ...(hasNisar
          ? [
              {
                label: t('chartNisar'),
                data: val('area_nisar_km2'),
                borderColor: 'rgba(124,58,237,0.9)',
                backgroundColor: 'rgba(124,58,237,0.9)',
                showLine: false,
                pointStyle: 'triangle',
                pointRadius: 4,
                order: 0,
              },
            ]
          : []),
        ...(hasOfficial
          ? [
              {
                label: t('chartOfficial'),
                data: val('official_fill_pct'),
                yAxisID: 'y1',
                borderColor: '#8a5cc7',
                borderDash: [2, 3],
                borderWidth: 1.5,
                pointRadius: 0,
                tension: 0.25,
                order: 2,
              },
            ]
          : []),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          ticks: {
            autoSkip: true,
            maxRotation: 0,
            callback: (v, i) => {
              const m = months[i];
              return m.endsWith('-01') || i === 0 ? m.slice(0, 4) : m.endsWith('-07') ? 'Jul' : '';
            },
          },
          grid: { display: false },
        },
        y: { title: { display: true, text: t('chartArea') }, beginAtZero: true, grace: '8%' },
        ...(hasOfficial
          ? { y1: { position: 'right', min: 0, max: 100, title: { display: true, text: 'Fill (%)' }, grid: { display: false } } }
          : {}),
      },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 14, boxHeight: 8, font: { size: 11 }, filter: (item) => item.text !== 'p10' },
        },
        tooltip: {
          filter: (item) => item.dataset.label !== 'p10',
          callbacks: {
            title: (items) => formatMonth(months[items[0].dataIndex]),
            label: (item) => {
              if (item.datasetIndex === 0) {
                const r = rows[item.dataIndex];
                return r ? ` ${t('chartRange')}: ${r.p10_km2}–${r.p90_km2} km²` : '';
              }
              const unit = item.dataset.yAxisID === 'y1' ? '%' : ' km²';
              return ` ${item.dataset.label.replace(/ \(.*\)/, '')}: ${item.formattedValue}${unit}`;
            },
          },
        },
        monthMarker: { index: months.indexOf(month) },
      },
      onClick: (_e, elements) => {
        if (elements.length && onPickMonth) onPickMonth(months[elements[0].index]);
      },
    },
    plugins: [monthMarker],
  });

  return {
    setMonth(m) {
      chart.options.plugins.monthMarker.index = months.indexOf(m);
      chart.update('none');
    },
    destroy: () => chart.destroy(),
  };
}
