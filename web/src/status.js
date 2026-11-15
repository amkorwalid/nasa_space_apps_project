// Status classes (README "Key features"): single source of truth for map, legend and panel.
import { t } from './i18n.js';

const DEF = {
  above_normal: { range: '> 110%', color: '#2f6fd6' },
  normal: { range: '90–110%', color: '#2a9d5c' },
  watch: { range: '75–90%', color: '#e3b505' },
  drought: { range: '50–75%', color: '#ee7d2b' },
  severe: { range: '< 50%', color: '#d23c3c' },
  no_data: { range: '—', color: '#9aa3ad' },
};

export const STATUS = Object.fromEntries(
  Object.entries(DEF).map(([k, v]) => [k, { ...v, get label() { return t(`status.${k}`); } }]),
);

export const STATUS_ORDER = ['above_normal', 'normal', 'watch', 'drought', 'severe', 'no_data'];

export function classify(pct) {
  if (pct == null || Number.isNaN(pct)) return 'no_data';
  if (pct > 110) return 'above_normal';
  if (pct >= 90) return 'normal';
  if (pct >= 75) return 'watch';
  if (pct >= 50) return 'drought';
  return 'severe';
}

/** Status for a time-series record (missing record, bad quality → no_data). */
export function statusOf(rec) {
  if (!rec || rec.quality === 'bad') return 'no_data';
  return STATUS[rec.status] ? rec.status : classify(rec.pct_of_normal);
}

export const statusColor = (s) => (STATUS[s] || STATUS.no_data).color;

/** MapLibre expression coloring by feature-state "status". */
export const statusColorExpression = [
  'match',
  ['coalesce', ['feature-state', 'status'], 'no_data'],
  ...STATUS_ORDER.filter((s) => s !== 'no_data').flatMap((s) => [s, STATUS[s].color]),
  STATUS.no_data.color,
];
