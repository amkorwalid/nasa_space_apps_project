import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// MapLibre v6 locates its worker relative to import.meta.url, which breaks once bundled.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import { statusColorExpression, statusOf, STATUS } from './status.js';
import { centroid, bbox } from './data.js';
import { escapeHtml, fmt, formatMonth } from './store.js';

if (typeof maplibregl.setWorkerUrl === 'function') maplibregl.setWorkerUrl(workerUrl);

export { maplibregl };

export const MOROCCO_BOUNDS = [[-13.2, 27.6], [-1.0, 35.95]];

export const BASEMAPS = {
  light: {
    label: 'Light gray',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Basemap © Esri, HERE, Garmin, © OpenStreetMap contributors',
    maxzoom: 16,
  },
  satellite: {
    label: 'Satellite (optical)',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    maxzoom: 18,
  },
  streets: {
    label: 'Streets',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxzoom: 19,
  },
  dark: {
    label: 'Dark gray',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Basemap © Esri, HERE, Garmin, © OpenStreetMap contributors',
    maxzoom: 16,
  },
};

const TRANSPARENT_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

const boundsToCorners = ([[w, s], [e, n]]) => [[w, n], [e, n], [e, s], [w, s]];

function baseStyle(active) {
  const sources = {};
  const layers = [{ id: 'background', type: 'background', paint: { 'background-color': '#dfe6ec' } }];
  for (const [key, b] of Object.entries(BASEMAPS)) {
    sources[`basemap-${key}`] = { type: 'raster', tiles: b.tiles, tileSize: 256, attribution: b.attribution, maxzoom: b.maxzoom ?? 20 };
    layers.push({
      id: `basemap-${key}`,
      type: 'raster',
      source: `basemap-${key}`,
      layout: { visibility: key === active ? 'visible' : 'none' },
    });
  }
  return { version: 8, sources, layers };
}

/**
 * One MapLibre map showing the SaddSAR layers for a given month.
 * The main view and the swipe-comparison view are both MapViews.
 */
export class MapView {
  constructor(container, data, { basemap = 'light', layers = {}, month, onSelect, bounds = MOROCCO_BOUNDS } = {}) {
    this.data = data;
    this.onSelect = onSelect;
    this.month = month;
    this.selectedId = null;
    this.hoverId = null;
    this.visibleIds = null;
    this.layerVis = { reservoirs: true, basins: true, extents: true, ...layers };
    this.basemap = basemap;

    this.map = new maplibregl.Map({
      container,
      style: baseStyle(basemap),
      bounds,
      fitBoundsOptions: { padding: 30 },
      attributionControl: { compact: true },
      maxPitch: 0,
      dragRotate: false,
    });
    this.map.touchZoomRotate.disableRotation();

    this.ready = new Promise((resolve) => {
      this.map.on('load', () => {
        this._addLayers();
        this._bindEvents();
        this.setLayerVisibility(this.layerVis);
        if (month) this.setMonth(month);
        resolve(this);
      });
    });
  }

  addControls() {
    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    this.map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
    this.map.addControl(new maplibregl.FullscreenControl({ container: document.querySelector('#map-wrap') }), 'top-left');
    return this;
  }

  _addLayers() {
    const { map, data } = this;

    map.addSource('basins', { type: 'geojson', data: data.basins, promoteId: 'basin_id' });
    map.addLayer({
      id: 'basins-fill',
      type: 'fill',
      source: 'basins',
      paint: { 'fill-color': '#5b6b7a', 'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.1, 0.04] },
    });
    map.addLayer({
      id: 'basins-line',
      type: 'line',
      source: 'basins',
      paint: { 'line-color': '#4a5a6a', 'line-width': 1.4, 'line-dasharray': [3, 2], 'line-opacity': 0.8 },
    });

    map.addSource('reservoirs', { type: 'geojson', data: data.reservoirs, promoteId: 'reservoir_id' });
    map.addLayer({
      id: 'reservoirs-fill',
      type: 'fill',
      source: 'reservoirs',
      paint: {
        'fill-color': statusColorExpression,
        'fill-opacity': ['case', ['boolean', ['feature-state', 'dimmed'], false], 0.05, ['boolean', ['feature-state', 'hover'], false], 0.45, 0.28],
      },
    });

    // One image source per reservoir: monthly water-extent PNG overlay
    this.extentLayers = [];
    for (const f of data.reservoirs.features) {
      const id = f.properties.reservoir_id;
      const corners = boundsToCorners(bbox(f.geometry));
      map.addSource(`extent-${id}`, { type: 'image', url: TRANSPARENT_PNG, coordinates: corners });
      map.addLayer({
        id: `extent-${id}`,
        type: 'raster',
        source: `extent-${id}`,
        paint: { 'raster-opacity': 0.9, 'raster-fade-duration': 0, 'raster-resampling': 'nearest' },
      });
      this.extentLayers.push(id);
    }

    map.addLayer({
      id: 'reservoirs-line',
      type: 'line',
      source: 'reservoirs',
      paint: {
        'line-color': statusColorExpression,
        'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 4, ['boolean', ['feature-state', 'hover'], false], 3, 2],
        'line-opacity': ['case', ['boolean', ['feature-state', 'dimmed'], false], 0.25, 1],
      },
    });

    // Centroid symbols so reservoirs stay visible / clickable at national zoom
    const points = {
      type: 'FeatureCollection',
      features: data.reservoirs.features.map((f) => ({
        type: 'Feature',
        properties: { reservoir_id: f.properties.reservoir_id, capacity_mcm: f.properties.capacity_mcm ?? 0 },
        geometry: { type: 'Point', coordinates: centroid(f.geometry) },
      })),
    };
    map.addSource('reservoir-points', { type: 'geojson', data: points, promoteId: 'reservoir_id' });
    map.addLayer({
      id: 'reservoirs-points',
      type: 'circle',
      source: 'reservoir-points',
      maxzoom: 9,
      paint: {
        'circle-color': statusColorExpression,
        'circle-radius': ['interpolate', ['linear'], ['sqrt', ['get', 'capacity_mcm']], 0, 5, 60, 14],
        'circle-stroke-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#111827', '#ffffff'],
        'circle-stroke-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, 2],
        'circle-opacity': ['case', ['boolean', ['feature-state', 'dimmed'], false], 0.25, 0.95],
        'circle-stroke-opacity': ['case', ['boolean', ['feature-state', 'dimmed'], false], 0.25, 1],
        'circle-opacity-transition': { duration: 300 },
      },
    });
  }

  _bindEvents() {
    const { map } = this;
    const clickable = ['reservoirs-fill', 'reservoirs-points'];
    this.popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'hover-popup' });

    const setHover = (id) => {
      if (this.hoverId === id) return;
      if (this.hoverId) this._setState(this.hoverId, { hover: false });
      this.hoverId = id;
      if (id) this._setState(id, { hover: true });
    };

    map.on('mousemove', (e) => {
      const hit = map.queryRenderedFeatures(e.point, { layers: clickable.filter((l) => map.getLayer(l)) })[0];
      const id = hit?.properties?.reservoir_id;
      map.getCanvas().style.cursor = id ? 'pointer' : '';
      setHover(id || null);
      if (!id) {
        this.popup.remove();
        return;
      }
      const f = this.data.byId.get(id);
      const rec = this.data.record(id, this.month);
      const st = statusOf(rec);
      this.popup
        .setLngLat(e.lngLat)
        .setHTML(
          `<strong>${escapeHtml(f.properties.name)}</strong><br>` +
            `<span class="dot" style="background:${STATUS[st].color}"></span>${STATUS[st].label}` +
            (rec ? ` · ${fmt(rec.pct_of_normal, 0, '%')} of normal` : '') +
            `<br><small>${formatMonth(this.month)}</small>`,
        )
        .addTo(map);
    });
    map.getCanvas().addEventListener('mouseleave', () => {
      setHover(null);
      this.popup.remove();
    });

    map.on('click', (e) => {
      const hit = map.queryRenderedFeatures(e.point, { layers: clickable.filter((l) => map.getLayer(l)) })[0];
      this.onSelect?.(hit?.properties?.reservoir_id ?? null);
    });
  }

  _setState(id, state) {
    if (!this.map.getSource('reservoirs')) return;
    this.map.setFeatureState({ source: 'reservoirs', id }, state);
    this.map.setFeatureState({ source: 'reservoir-points', id }, state);
  }

  setBasemap(key) {
    this.basemap = key;
    if (!this.map.getLayer(`basemap-${key}`)) {
      this.map.once('load', () => this.setBasemap(key));
      return;
    }
    for (const k of Object.keys(BASEMAPS)) this.map.setLayoutProperty(`basemap-${k}`, 'visibility', k === key ? 'visible' : 'none');
  }

  setLayerVisibility(vis) {
    this.layerVis = { ...this.layerVis, ...vis };
    if (!this.map.getLayer('reservoirs-fill')) return;
    const v = (on) => (on ? 'visible' : 'none');
    for (const l of ['reservoirs-fill', 'reservoirs-line', 'reservoirs-points']) this.map.setLayoutProperty(l, 'visibility', v(this.layerVis.reservoirs));
    for (const l of ['basins-fill', 'basins-line']) this.map.setLayoutProperty(l, 'visibility', v(this.layerVis.basins));
    this._updateExtents();
  }

  setMonth(month) {
    this.month = month;
    if (!this.map.getSource('reservoirs')) return;
    for (const f of this.data.reservoirs.features) {
      const id = f.properties.reservoir_id;
      this._setState(id, { status: statusOf(this.data.record(id, month)) });
    }
    this._updateExtents();
  }

  _updateExtents() {
    if (!this.extentLayers) return;
    for (const id of this.extentLayers) {
      const ext = this.month ? this.data.extent(id, this.month) : null;
      const show = this.layerVis.extents && ext && (!this.visibleIds || this.visibleIds.has(id));
      if (ext) this.map.getSource(`extent-${id}`).updateImage({ url: ext.url, coordinates: boundsToCorners(ext.bounds) });
      this.map.setLayoutProperty(`extent-${id}`, 'visibility', show ? 'visible' : 'none');
    }
  }

  setSelected(id) {
    if (this.selectedId) this._setState(this.selectedId, { selected: false });
    this.selectedId = id;
    if (id) this._setState(id, { selected: true });
  }

  /** Dim reservoirs not matching the search/filter (null = show all). */
  setVisibleIds(ids) {
    this.visibleIds = ids;
    for (const f of this.data.reservoirs.features) {
      const id = f.properties.reservoir_id;
      this._setState(id, { dimmed: ids ? !ids.has(id) : false });
    }
    this._updateExtents();
  }

  flyToReservoir(id) {
    const f = this.data.byId.get(id);
    if (!f) return;
    const isMobile = window.matchMedia('(max-width: 800px)').matches;
    this.map.fitBounds(bbox(f.geometry), { padding: isMobile ? 40 : { top: 60, bottom: 120, left: 60, right: 60 }, maxZoom: 12, duration: 1200 });
  }

  fitMorocco() {
    this.map.fitBounds(MOROCCO_BOUNDS, { padding: 30, duration: 1000 });
  }

  resize() {
    this.map.resize();
  }

  remove() {
    this.popup?.remove();
    this.map.remove();
  }
}
