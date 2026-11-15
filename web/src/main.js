import './style.css';
import { loadData } from './data.js';
import { createStore, changed } from './store.js';
import { MapView } from './map.js';
import { renderLegend } from './legend.js';
import { initLayerControl } from './layers.js';
import { initPanel } from './panel.js';
import { initTimeSlider } from './timeslider.js';
import { initCompare } from './compare.js';
import { initSearch } from './search.js';
import { initExplainer } from './explainer.js';
import { initStory } from './story.js';
import { LANGS, applyDocumentLang, lang, setLang, t } from './i18n.js';

const $ = (sel) => document.querySelector(sel);

/** Shareable state in the URL hash: #r=MAR_0001&m=2026-03 */
function readHash(data) {
  const p = new URLSearchParams(location.hash.slice(1));
  const r = p.get('r');
  const m = p.get('m');
  return {
    ...(r && data.byId.has(r) ? { selectedId: r } : {}),
    ...(m && data.months.includes(m) ? { month: m } : {}),
  };
}

function writeHash({ selectedId, month }) {
  const p = new URLSearchParams();
  if (selectedId) p.set('r', selectedId);
  if (month) p.set('m', month);
  history.replaceState(null, '', `#${p}`);
}

function initChrome() {
  applyDocumentLang();
  document.querySelectorAll('[data-i18n]').forEach((el) => (el.innerHTML = t(el.dataset.i18n)));
  document.querySelectorAll('[data-i18n-title]').forEach((el) => (el.title = t(el.dataset.i18nTitle)));
  const box = $('#lang');
  box.setAttribute('aria-label', t('lang'));
  box.innerHTML = LANGS.map(
    ([code, label]) => `<button type="button" class="lang-btn${code === lang ? ' active' : ''}" data-lang="${code}" aria-pressed="${code === lang}">${label}</button>`,
  ).join('');
  box.addEventListener('click', (e) => {
    const b = e.target.closest('[data-lang]');
    if (b && b.dataset.lang !== lang) setLang(b.dataset.lang);
  });
}

async function main() {
  initChrome();
  let data;
  try {
    data = await loadData();
  } catch (err) {
    console.error(err);
    $('#loading').classList.add('error');
    $('#loading').innerHTML = `${t('loadError')}<br><small>${err.message}. ${t('loadHint')}</small>`;
    return;
  }
  $('#mock-badge').hidden = !data.isMock;

  const store = createStore({
    month: data.months[data.months.length - 1],
    selectedId: null,
    visibleIds: null,
    basemap: 'light',
    layers: { reservoirs: true, extents: true, basins: true },
    compare: false,
    compareMonth: null,
    flyTo: null,
    ...readHash(data),
  });

  const mainView = new MapView($('#map'), data, {
    basemap: store.get().basemap,
    layers: store.get().layers,
    month: store.get().month,
    onSelect: (id) => store.set({ selectedId: id }),
  }).addControls();
  let views = [mainView];

  renderLegend($('#legend'));
  initLayerControl($('#layer-control'), store);
  initPanel($('#panel'), data, store);
  initTimeSlider($('#timebar'), data.months, store);
  initSearch($('#search'), data, store);
  initExplainer($('#explainer'), $('#btn-explainer'));
  initCompare({ wrap: $('#map-wrap'), mainView, data, store, onViewsChange: (v) => (views = v) });
  initStory({ card: $('#story-card'), button: $('#btn-story'), data, store, mainView });

  store.subscribe((s, prev) => {
    if (changed(s, prev, 'month')) mainView.setMonth(s.month);
    if (changed(s, prev, 'basemap')) views.forEach((v) => v.setBasemap(s.basemap));
    if (changed(s, prev, 'layers')) views.forEach((v) => v.setLayerVisibility(s.layers));
    if (changed(s, prev, 'visibleIds')) views.forEach((v) => v.setVisibleIds(s.visibleIds));
    if (changed(s, prev, 'selectedId')) {
      views.forEach((v) => v.setSelected(s.selectedId));
      if (s.selectedId && !prev.selectedId) mainView.flyToReservoir(s.selectedId);
    }
    if (changed(s, prev, 'flyTo') && s.flyTo) mainView.flyToReservoir(s.flyTo.id);
    if (changed(s, prev, 'selectedId', 'month')) writeHash(s);
  });

  await mainView.ready;
  $('#loading').remove();
  const s = store.get();
  mainView.setSelected(s.selectedId);
  if (s.selectedId) mainView.flyToReservoir(s.selectedId);

  // Handy for debugging from the browser console
  window.__saddsar = { data, store, views: () => views };

  // Keep the map sized correctly when the panel/bottom-sheet changes size
  new ResizeObserver(() => views.forEach((v) => v.resize())).observe($('#map-wrap'));
}

main();
