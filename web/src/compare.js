import Compare from '@maplibre/maplibre-gl-compare';
import '@maplibre/maplibre-gl-compare/dist/maplibre-gl-compare.css';
import { MapView } from './map.js';
import { changed, formatMonth } from './store.js';

/**
 * Before/after swipe: a second MapView (right side) stacked over the main one,
 * synced with maplibre-gl-compare. Left = slider month, right = compareMonth.
 */
export function initCompare({ wrap, mainView, data, store, onViewsChange }) {
  let view = null;
  let compare = null;
  let container = null;
  const labels = document.querySelector('#compare-labels');
  const labelL = document.querySelector('#compare-label-left');
  const labelR = document.querySelector('#compare-label-right');
  const btn = document.querySelector('#btn-compare');

  async function enable(s) {
    container = document.createElement('div');
    container.id = 'map-compare';
    container.className = 'map';
    wrap.querySelector('#map').after(container);
    const m = mainView.map;
    view = new MapView(container, data, {
      basemap: s.basemap,
      layers: s.layers,
      month: s.compareMonth,
      onSelect: (id) => store.set({ selectedId: id }),
      bounds: m.getBounds().toArray(),
    });
    await view.ready;
    if (!store.get().compare) return; // toggled off while loading
    view.map.jumpTo({ center: m.getCenter(), zoom: m.getZoom() });
    view.setSelected(s.selectedId);
    view.setVisibleIds(s.visibleIds);
    compare = new Compare(mainView.map, view.map, wrap, { mousemove: false, orientation: 'vertical' });
    labels.hidden = false;
    onViewsChange([mainView, view]);
  }

  function disable() {
    compare?.remove();
    compare = null;
    view?.remove();
    view = null;
    container?.remove();
    container = null;
    labels.hidden = true;
    // maplibre-gl-compare clips the left map; reset it
    mainView.map.getContainer().style.clip = '';
    mainView.map.getContainer().style.clipPath = '';
    mainView.resize();
    onViewsChange([mainView]);
  }

  btn.addEventListener('click', () => {
    const s = store.get();
    if (s.compare) return store.set({ compare: false });
    // Default: right = current month ("after"), left = same month one year earlier ("before")
    const months = data.months;
    const prevYear = `${Number(s.month.slice(0, 4)) - 1}${s.month.slice(4)}`;
    store.set({ compare: true, compareMonth: s.month, month: months.includes(prevYear) ? prevYear : months[0] });
  });

  store.subscribe((s, prev) => {
    if (changed(s, prev, 'compare')) {
      btn.setAttribute('aria-pressed', String(s.compare));
      btn.classList.toggle('active', s.compare);
      s.compare ? enable(s) : disable();
    }
    if (view && changed(s, prev, 'compareMonth')) view.setMonth(s.compareMonth);
    if (s.compare) {
      labelL.textContent = `◀ ${formatMonth(s.month)}`;
      labelR.textContent = `${formatMonth(s.compareMonth)} ▶`;
    }
  });
}
