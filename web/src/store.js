// Tiny observable app state.
export function createStore(initial) {
  let state = { ...initial };
  const subs = new Set();
  return {
    get: () => state,
    set(patch) {
      const prev = state;
      state = { ...state, ...patch };
      subs.forEach((fn) => fn(state, prev));
    },
    subscribe(fn) {
      subs.add(fn);
      return () => subs.delete(fn);
    },
  };
}

export const changed = (state, prev, ...keys) => keys.some((k) => state[k] !== prev[k]);

import { locale } from './i18n.js';

const MONTH_FMT = new Intl.DateTimeFormat(locale, { month: 'short', year: 'numeric', timeZone: 'UTC', numberingSystem: 'latn' });
export const formatMonth = (m) => (m ? MONTH_FMT.format(Date.UTC(Number(m.slice(0, 4)), Number(m.slice(5)) - 1, 15)) : '—');

export const fmt = (v, digits = 1, unit = '') =>
  v == null || Number.isNaN(v) ? '—' : `${Number(v).toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })}${unit}`;

export const fmtSigned = (v, digits = 1, unit = '%') =>
  v == null || Number.isNaN(v) ? '—' : `${v > 0 ? '+' : ''}${fmt(v, digits)}${unit}`;

export function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}
