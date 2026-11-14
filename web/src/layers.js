import { BASEMAPS } from './map.js';

const LAYERS = [
  ['reservoirs', 'Reservoirs & lakes'],
  ['extents', 'Water extent (radar)'],
  ['basins', 'River basins'],
];

/** Layer control: overlay toggles + basemap switcher. Writes into the store. */
export function initLayerControl(el, store) {
  const { layers, basemap } = store.get();
  el.innerHTML = `
    <details>
      <summary aria-label="Layers">☰ Layers</summary>
      <fieldset>
        <legend>Overlays</legend>
        ${LAYERS.map(
          ([key, label]) =>
            `<label><input type="checkbox" name="layer" value="${key}" ${layers[key] ? 'checked' : ''}> ${label}</label>`,
        ).join('')}
      </fieldset>
      <fieldset>
        <legend>Basemap</legend>
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
