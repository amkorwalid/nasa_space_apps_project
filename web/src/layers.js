import { BASEMAPS } from './map.js';
import { t } from './i18n.js';

const LAYERS = [
  ['reservoirs', 'lyrReservoirs'],
  ['extents', 'lyrExtents'],
  ['basins', 'lyrBasins'],
];

/** Layer control: overlay toggles + basemap switcher. Writes into the store. */
export function initLayerControl(el, store) {
  const { layers, basemap } = store.get();
  el.innerHTML = `
    <details>
      <summary aria-label="${t('layers')}">☰ ${t('layers')}</summary>
      <fieldset>
        <legend>${t('overlays')}</legend>
        ${LAYERS.map(
          ([key, label]) =>
            `<label><input type="checkbox" name="layer" value="${key}" ${layers[key] ? 'checked' : ''}> ${t(label)}</label>`,
        ).join('')}
      </fieldset>
      <fieldset>
        <legend>${t('basemap')}</legend>
        ${Object.entries(BASEMAPS)
          .map(
            ([key, b]) =>
              `<label><input type="radio" name="basemap" value="${key}" ${key === basemap ? 'checked' : ''}> ${b.label}</label>`,
          )
          .join('')}
      </fieldset>
    </details>`;

  el.addEventListener('change', (e) => {
    const t = e.target;
    if (t.name === 'layer') store.set({ layers: { ...store.get().layers, [t.value]: t.checked } });
    if (t.name === 'basemap') store.set({ basemap: t.value });
  });

  // Open by default on wide screens
  if (window.matchMedia('(min-width: 801px)').matches) el.querySelector('details').open = true;
}
