import { STORY } from '../content/story.js';
import { lang, t } from './i18n.js';
import { fmt, fmtSigned, formatMonth } from './store.js';

/** Guided tour: a floating card that drives the store (month, selection) step by step. */
export function initStory({ card, button, data, store, mainView }) {
  const steps = STORY.filter((s) => !s.target.reservoir || data.byId.has(s.target.reservoir));
  if (!steps.length) {
    button.hidden = true;
    return;
  }
  let i = -1;
  const latest = data.months[data.months.length - 1];
  const lowest = data.national.length
    ? data.national.reduce((a, b) => (b.pct_of_normal < a.pct_of_normal ? b : a)).month
    : latest;

  function vars(target) {
    const month = target.month === 'lowest' ? lowest : target.month === 'latest' ? latest : target.month;
    if (target.reservoir) {
      const r = data.record(target.reservoir, month) || {};
      return { month, vals: { month: formatMonth(month), area: fmt(r.area_km2, 1), pct: fmt(r.pct_of_normal, 0, '%'), yoy: fmtSigned(r.yoy_change_pct, 0) } };
    }
    const nat = data.national.find((r) => r.month === month) || {};
    const n = data.reservoirs.features.filter((f) => data.isMonitored(f)).length;
    return { month, vals: { month: formatMonth(month), pct: fmt(nat.pct_of_normal, 0, '%'), n } };
  }

  function show(k) {
    i = k;
    if (i < 0 || i >= steps.length) {
      card.hidden = true;
      button.setAttribute('aria-pressed', 'false');
      return;
    }
    const s = steps[i];
    const { month, vals } = vars(s.target);
    const [title, body] = s.text[lang] || s.text.en;
    const fill = (str) => str.replace(/\{(\w+)\}/g, (_, key) => vals[key] ?? '—');
    store.set({ compare: false, month, selectedId: s.target.reservoir || null, visibleIds: null });
    if (s.target.reservoir) store.set({ flyTo: { id: s.target.reservoir, t: Date.now() } });
    else mainView.fitMorocco();
    card.hidden = false;
    button.setAttribute('aria-pressed', 'true');
    card.innerHTML = `
      <p class="eyebrow">${i + 1} / ${steps.length}</p>
      <h3>${fill(title)}</h3>
      <p>${fill(body)}</p>
      <div class="story-nav">
        <button type="button" class="btn small" data-story="prev" ${i === 0 ? 'disabled' : ''}>${t('storyPrev')}</button>
        <button type="button" class="btn small primary" data-story="next">${i === steps.length - 1 ? t('storyEnd') : t('storyNext')}</button>
        <button type="button" class="icon-btn" data-story="close" aria-label="${t('close')}">✕</button>
      </div>`;
  }

  button.addEventListener('click', () => (card.hidden ? show(0) : show(-1)));
  card.addEventListener('click', (e) => {
    const b = e.target.closest('[data-story]');
    if (!b) return;
    if (b.dataset.story === 'next') show(i + 1);
    else if (b.dataset.story === 'prev') show(i - 1);
    else show(-1);
  });
  document.addEventListener('keydown', (e) => {
    if (card.hidden) return;
    if (e.key === 'Escape') show(-1);
  });
}
