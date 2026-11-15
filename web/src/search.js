import { STATUS, STATUS_ORDER, statusOf } from './status.js';
import { changed, escapeHtml } from './store.js';
import { t } from './i18n.js';

/** Search by name + filters (basin, status for the current month, minimum capacity). */
export function initSearch(el, data, store) {
  const feats = data.reservoirs.features;
  const basins = [...new Set(feats.map((f) => f.properties.basin).filter(Boolean))].sort();

  el.innerHTML = `
    <div class="search-box">
      <input type="search" placeholder="${t('search')}" aria-label="${t('search')}" autocomplete="off" />
      <button type="button" class="icon-btn filter-toggle" aria-label="${t('filters')}" aria-expanded="false">⚲</button>
      <ul class="search-results" role="listbox" hidden></ul>
    </div>
    <div class="filters" hidden>
      <label>${t('basin')} <select name="basin"><option value="">${t('all')}</option>${basins.map((b) => `<option>${escapeHtml(b)}</option>`).join('')}</select></label>
      <label>${t('status')} <select name="status"><option value="">${t('all')}</option>${STATUS_ORDER.map((s) => `<option value="${s}">${STATUS[s].label}</option>`).join('')}</select></label>
      <label>${t('minCap')} <select name="cap"><option value="0">${t('any')}</option><option value="100">100 Mm³</option><option value="500">500 Mm³</option><option value="1000">1,000 Mm³</option></select></label>
      <button type="button" class="link" data-action="clear">${t('clear')}</button>
    </div>`;

  const input = el.querySelector('input');
  const results = el.querySelector('.search-results');
  const filters = el.querySelector('.filters');
  const toggle = el.querySelector('.filter-toggle');
  const f = { q: '', basin: '', status: '', cap: 0 };

  const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  function apply() {
    const { month } = store.get();
    const q = norm(f.q);
    const active = q || f.basin || f.status || f.cap;
    const matched = feats.filter(({ properties: p }) => {
      if (q && !norm(p.name).includes(q) && !norm(p.basin).includes(q)) return false;
      if (f.basin && p.basin !== f.basin) return false;
      if (f.cap && (p.capacity_mcm || 0) < f.cap) return false;
      if (f.status && statusOf(data.record(p.reservoir_id, month)) !== f.status) return false;
      return true;
    });
    store.set({ visibleIds: active ? new Set(matched.map((m) => m.properties.reservoir_id)) : null });
    toggle.classList.toggle('active', Boolean(f.basin || f.status || f.cap));

    if (!q) {
      results.hidden = true;
      return;
    }
    results.hidden = false;
    results.innerHTML = matched.length
      ? matched
          .slice(0, 8)
          .map(({ properties: p }) => {
            const st = statusOf(data.record(p.reservoir_id, month));
            return `<li role="option"><button type="button" data-id="${escapeHtml(p.reservoir_id)}">
              <span class="swatch" style="background:${STATUS[st].color}"></span>${escapeHtml(p.name)} <small>${escapeHtml(p.basin || '')}</small></button></li>`;
          })
          .join('')
      : `<li class="empty">${t('noMatch')}</li>`;
  }

  input.addEventListener('input', () => {
    f.q = input.value.trim();
    apply();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') results.querySelector('button')?.click();
    if (e.key === 'Escape') {
      input.value = f.q = '';
      apply();
    }
  });
  results.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-id]');
    if (!b) return;
    results.hidden = true;
    store.set({ selectedId: b.dataset.id, flyTo: { id: b.dataset.id, t: Date.now() } });
  });
  toggle.addEventListener('click', () => {
    filters.hidden = !filters.hidden;
    toggle.setAttribute('aria-expanded', String(!filters.hidden));
  });
  filters.addEventListener('change', (e) => {
    const t = e.target;
    f[t.name] = t.name === 'cap' ? Number(t.value) : t.value;
    apply();
  });
  filters.querySelector('[data-action=clear]').addEventListener('click', () => {
    filters.querySelectorAll('select').forEach((s) => (s.selectedIndex = 0));
    Object.assign(f, { basin: '', status: '', cap: 0 });
    apply();
  });
  document.addEventListener('click', (e) => {
    if (!el.contains(e.target)) results.hidden = true;
  });

  // Status filter depends on the month
  store.subscribe((s, prev) => {
    if (f.status && changed(s, prev, 'month')) apply();
  });
}
