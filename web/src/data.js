// Loads the Contract 4 web dataset from public/data/ (mock now, Track A export later).
const BASE = `${import.meta.env.BASE_URL}data/`;

async function getJSON(path, { optional = false } = {}) {
  const res = await fetch(BASE + path);
  if (!res.ok) {
    if (optional) return null;
    throw new Error(`Failed to load ${path} (HTTP ${res.status})`);
  }
  return res.json();
}

export async function loadData() {
  const [reservoirs, basins, months, extents] = await Promise.all([
    getJSON('reservoirs.geojson'),
    getJSON('basins.geojson', { optional: true }),
    getJSON('months.json'),
    getJSON('extents/index.json', { optional: true }),
  ]);

  const ids = reservoirs.features.map((f) => f.properties.reservoir_id);
  const series = {};
  await Promise.all(
    ids.map(async (id) => {
      const ts = await getJSON(`timeseries/${id}.json`, { optional: true }).catch(() => null);
      series[id] = new Map((ts?.series || []).map((r) => [r.month, r]));
    }),
  );

  const byId = new Map(reservoirs.features.map((f) => [f.properties.reservoir_id, f]));

  return {
    reservoirs,
    basins: basins || { type: 'FeatureCollection', features: [] },
    months,
    extents: extents || {},
    series,
    byId,
    isMock: Boolean(reservoirs.metadata?.mock),
    /** Time-series record for a reservoir and month (or undefined). */
    record: (id, month) => series[id]?.get(month),
    /** Overlay image info for a reservoir-month, or null if none was exported. */
    extent: (id, month) => {
      const key = `${id}_${month}`;
      const entry = extents?.[key];
      return entry ? { url: `${BASE}extents/${key}.png`, bounds: entry.bounds } : null;
    },
    timeseriesUrl: (id) => `${BASE}timeseries/${id}.json`,
  };
}

/** Polygon centroid (area-weighted, outer ring) for point symbols at national zoom. */
export function centroid(geometry) {
  const polys = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates];
  let ax = 0;
  let ay = 0;
  let aa = 0;
  for (const poly of polys) {
    const ring = poly[0];
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const f = ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
      ax += (ring[j][0] + ring[i][0]) * f;
      ay += (ring[j][1] + ring[i][1]) * f;
      aa += f;
    }
  }
  if (!aa) return polys[0][0][0];
  return [ax / (3 * aa), ay / (3 * aa)];
}

export function bbox(geometry) {
  const polys = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates];
  let b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const poly of polys)
    for (const [x, y] of poly[0]) b = [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)];
  return [[b[0], b[1]], [b[2], b[3]]];
}
