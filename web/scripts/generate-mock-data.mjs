#!/usr/bin/env node
/**
 * SaddSAR – mock data generator (Track D, mock-first).
 *
 * Writes a fake but contract-compliant (README "Contract 4") web dataset into
 * web/public/data/ so the web GIS can be built before Track A's real export lands:
 *
 *   reservoirs.geojson            Contract 1 + latest status fields
 *   basins.geojson                basin polygons + aggregated latest status
 *   months.json                   ["2025-01", ..., "2026-10"]
 *   timeseries/<id>.json          monthly series per reservoir
 *   extents/<id>_<YYYY-MM>.png    transparent water-extent overlays
 *   extents/index.json            bounds per overlay
 *
 * Geometry and numbers are ILLUSTRATIVE ONLY. The reservoir outline is hand-drawn
 * and approximate; areas are derived from a synthetic bathymetry so that the chart
 * values and the PNG overlays are consistent with each other.
 *
 * Usage:  npm run mock:data   (no dependencies, Node >= 18)
 */
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { deflateSync } from 'node:zlib';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'data');
const MONTHS = monthRange('2025-01', '2026-10');
const PIXEL_KM = 0.06; // ~60 m overlay pixels

/** Long-term mean % full by calendar month (Jan..Dec) – drives the "normal" climatology. */
const NORMAL_FILL = [58, 64, 70, 72, 71, 67, 62, 57, 53, 51, 52, 55];

/** Area–storage relation used by the mock: area_fraction = fill_fraction ^ AREA_EXP. */
const AREA_EXP = 0.8;

// ---------------------------------------------------------------------------
// Reservoir definitions (add the other demo dams here later)
// ---------------------------------------------------------------------------
const RESERVOIRS = [
  {
    reservoir_id: 'MAR_0001',
    name: 'Al Wahda',
    basin: 'Sebou',
    basin_id: 'SEBOU',
    river: 'Ouergha',
    capacity_mcm: 3522,
    dam_year: 1997,
    priority: true,
    nisar_from: '2025-10',
    partial_months: ['2026-02'],
    // Lake shape as channel "arms" traced by eye from satellite imagery (approximate).
    // Each arm: [lon, lat, half-width km] points. arms[0] = main channel, starting at the dam wall
    // (west) and running upstream along the Ouergha valley (east-south-east).
    arms: [
      [
        [-5.1963, 34.5975, 1.6], [-5.1650, 34.6063, 2.4], [-5.1350, 34.5888, 2.3], [-5.1050, 34.5700, 2.1],
        [-5.0750, 34.5550, 1.5], [-5.0450, 34.5500, 1.3], [-5.0175, 34.5463, 1.5], [-4.9925, 34.5325, 1.3],
        [-4.9725, 34.5300, 0.8], [-4.9588, 34.5363, 0.35], [-4.9475, 34.5450, 0.12],
      ],
      // north arm
      [[-5.1700, 34.6075, 1.7], [-5.1775, 34.6300, 1.5], [-5.1788, 34.6500, 0.7], [-5.1763, 34.6675, 0.25], [-5.1725, 34.6775, 0.08]],
      // north-east arm
      [[-5.1500, 34.6150, 1.3], [-5.1250, 34.6350, 0.6], [-5.1025, 34.6425, 0.25], [-5.0988, 34.6525, 0.08]],
      // southern bays
      [[-5.1100, 34.5680, 1.0], [-5.1163, 34.5450, 0.7], [-5.1175, 34.5350, 0.15]],
      [[-5.0950, 34.5550, 0.6], [-5.0888, 34.5275, 0.4], [-5.0850, 34.5150, 0.08]],
    ],
    // Mock "official" fill rate (% of capacity): 2025 drought → 2026 wet-season recovery.
    official_fill: {
      '2025-01': 36.5, '2025-02': 41.0, '2025-03': 47.5, '2025-04': 49.8, '2025-05': 48.1, '2025-06': 45.0,
      '2025-07': 41.2, '2025-08': 37.6, '2025-09': 34.9, '2025-10': 31.8, '2025-11': 33.2, '2025-12': 44.6,
      '2026-01': 61.3, '2026-02': 83.7, '2026-03': 96.2, '2026-04': 97.5, '2026-05': 95.4, '2026-06': 91.8,
      '2026-07': 87.3, '2026-08': 82.6, '2026-09': 78.9, '2026-10': 77.4,
    },
  },
];

const BASINS = [
  {
    basin_id: 'SEBOU',
    name: 'Sebou',
    // Very rough outline of the Sebou hydrological basin (illustrative).
    ring: [
      [-6.65, 34.25], [-6.30, 34.85], [-5.80, 34.97], [-5.20, 34.98], [-4.60, 34.88], [-4.20, 34.56],
      [-3.95, 34.00], [-4.10, 33.45], [-4.60, 33.18], [-5.20, 33.25], [-5.70, 33.55], [-6.10, 33.85],
      [-6.65, 34.25],
    ],
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function monthRange(start, end) {
  const out = [];
  let [y, m] = start.split('-').map(Number);
  const [ey, em] = end.split('-').map(Number);
  while (y < ey || (y === ey && m <= em)) {
    out.push(`${y}-${String(m).padStart(2, '0')}`);
    m += 1;
    if (m > 12) { m = 1; y += 1; }
  }
  return out;
}

const round = (v, d = 1) => (v == null || Number.isNaN(v) ? null : Math.round(v * 10 ** d) / 10 ** d);

/** Deterministic pseudo-random in [0, 1) from integer-ish inputs. */
function hash(...nums) {
  let h = 2166136261;
  for (const n of nums) {
    h ^= Math.floor(n * 1000) | 0;
    h = Math.imul(h, 16777619);
    h ^= h >>> 13;
  }
  return ((h >>> 0) % 100000) / 100000;
}

function classify(pct) {
  if (pct == null) return 'no_data';
  if (pct > 110) return 'above_normal';
  if (pct >= 90) return 'normal';
  if (pct >= 75) return 'watch';
  if (pct >= 50) return 'drought';
  return 'severe';
}

/** Local equirectangular projection in km around an origin. */
function makeProjection(lon0, lat0) {
  const kx = 111.32 * Math.cos((lat0 * Math.PI) / 180);
  const ky = 110.57;
  return {
    toKm: ([lon, lat]) => [(lon - lon0) * kx, (lat - lat0) * ky],
    toLonLat: ([x, y]) => [lon0 + x / kx, lat0 + y / ky],
  };
}

/** Catmull-Rom densification of [x, y, w] control points. */
function densify(points, steps = 12) {
  const out = [];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];
    for (let s = 0; s < steps; s++) {
      const t = s / steps;
      const t2 = t * t;
      const t3 = t2 * t;
      const cr = (a, b, c, d) =>
        0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
      out.push([cr(p0[0], p1[0], p2[0], p3[0]), cr(p0[1], p1[1], p2[1], p3[1]), p1[2] + (p2[2] - p1[2]) * t]);
    }
  }
  out.push(points[points.length - 1]);
  return out;
}

// ---------------------------------------------------------------------------
// Minimal PNG encoder (RGBA, no dependencies)
// ---------------------------------------------------------------------------
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}

function encodePNG(width, height, rgba) {
  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0; // filter: none
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', deflateSync(raw, { level: 9 })),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

// ---------------------------------------------------------------------------
// Reservoir model: outline polygon + synthetic bathymetry raster
// ---------------------------------------------------------------------------
function buildArm(ctrlKm) {
  const line = densify(ctrlKm);
  const s = [0];
  for (let i = 1; i < line.length; i++) s.push(s[i - 1] + Math.hypot(line[i][0] - line[i - 1][0], line[i][1] - line[i - 1][1]));
  // Irregular shoreline: modulate half-width along the channel (coves and headlands)
  const width = line.map(([, , w], i) => {
    const si = s[i];
    const mod = 1 + 0.14 * Math.sin(si * 1.7) + 0.09 * Math.sin(si * 4.3 + 1.1) + 0.05 * Math.sin(si * 9.7 + 0.4);
    return Math.max(0.05, w * mod);
  });
  const maxW = Math.max(...width);
  const xs = line.map((p) => p[0]);
  const ys = line.map((p) => p[1]);
  return {
    line, s, width, s0: 0,
    bbox: [Math.min(...xs) - maxW, Math.min(...ys) - maxW, Math.max(...xs) + maxW, Math.max(...ys) + maxW],
  };
}

/** Nearest point on an arm's centreline: distance d, along-distance s, local half-width w, raw t on first segment. */
function nearestOnArm(arm, x, y) {
  const { line, s, width } = arm;
  let best = { d: Infinity, s: 0, w: 1, before: false };
  for (let i = 0; i < line.length - 1; i++) {
    const [ax, ay] = line[i];
    const [bx, by] = line[i + 1];
    const vx = bx - ax;
    const vy = by - ay;
    const seg2 = vx * vx + vy * vy || 1e-9;
    const raw = ((x - ax) * vx + (y - ay) * vy) / seg2;
    const t = Math.max(0, Math.min(1, raw));
    const d = Math.hypot(x - (ax + t * vx), y - (ay + t * vy));
    if (d < best.d) best = { d, s: s[i] + t * (s[i + 1] - s[i]), w: width[i] + t * (width[i + 1] - width[i]), before: i === 0 && raw < 0 };
  }
  return best;
}

/** Outer boundary of a binary mask, traced along pixel edges → ring of [col, row] corner coordinates. */
function traceOuterRing(mask, W, H) {
  const at = (r, c) => r >= 0 && c >= 0 && r < H && c < W && mask[r * W + c] === 1;
  const key = (r, c) => r * (W + 1) + c;
  const next = new Map();
  const add = (r0, c0, r1, c1) => {
    const k = key(r0, c0);
    if (!next.has(k)) next.set(k, []);
    next.get(k).push(key(r1, c1));
  };
  for (let r = 0; r < H; r++)
    for (let c = 0; c < W; c++) {
      if (!at(r, c)) continue;
      if (!at(r - 1, c)) add(r, c, r, c + 1);
      if (!at(r, c + 1)) add(r, c + 1, r + 1, c + 1);
      if (!at(r + 1, c)) add(r + 1, c + 1, r + 1, c);
      if (!at(r, c - 1)) add(r + 1, c, r, c);
    }
  let best = [];
  while (next.size) {
    const start = next.keys().next().value;
    const ring = [];
    let k = start;
    while (next.has(k)) {
      ring.push(k);
      const outs = next.get(k);
      const n = outs.pop();
      if (!outs.length) next.delete(k);
      k = n;
    }
    if (ring.length > best.length) best = ring;
  }
  const pts = best.map((k) => [k % (W + 1), Math.floor(k / (W + 1))]);
  pts.push(pts[0]);
  return pts;
}

/** Douglas–Peucker simplification. */
function simplify(points, tol) {
  if (points.length < 3) return points;
  const keep = new Uint8Array(points.length);
  keep[0] = keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop();
    const [ax, ay] = points[a];
    const [bx, by] = points[b];
    const len = Math.hypot(bx - ax, by - ay) || 1e-9;
    let maxD = 0;
    let idx = -1;
    for (let i = a + 1; i < b; i++) {
      const d = Math.abs((bx - ax) * (ay - points[i][1]) - (ax - points[i][0]) * (by - ay)) / len;
      if (d > maxD) { maxD = d; idx = i; }
    }
    if (maxD > tol && idx > 0) {
      keep[idx] = 1;
      stack.push([a, idx], [idx, b]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

/** Simplify a closed ring: split at the vertex farthest from the start so neither half is degenerate. */
function simplifyRing(ring, tol) {
  const open = ring.slice(0, -1);
  const [x0, y0] = open[0];
  let far = 1;
  open.forEach(([x, y], i) => {
    if (Math.hypot(x - x0, y - y0) > Math.hypot(open[far][0] - x0, open[far][1] - y0)) far = i;
  });
  const a = simplify(open.slice(0, far + 1), tol);
  const b = simplify([...open.slice(far), open[0]], tol);
  return [...a, ...b.slice(1)];
}

function buildReservoirModel(def) {
  const [lon0, lat0] = def.arms[0][0];
  const proj = makeProjection(lon0, lat0);
  const arms = def.arms.map((a) => buildArm(a.map(([lon, lat, w]) => [...proj.toKm([lon, lat]), w])));
  const main = arms[0];
  const L = main.s[main.s.length - 1];
  // Side arms inherit the along-channel distance of their junction with the main channel
  for (const arm of arms.slice(1)) arm.s0 = nearestOnArm(main, arm.line[0][0], arm.line[0][1]).s;

  // Raster grid over all arms
  const minX = Math.min(...arms.map((a) => a.bbox[0])) - PIXEL_KM;
  const minY = Math.min(...arms.map((a) => a.bbox[1])) - PIXEL_KM;
  const maxX = Math.max(...arms.map((a) => a.bbox[2])) + PIXEL_KM;
  const maxY = Math.max(...arms.map((a) => a.bbox[3])) + PIXEL_KM;
  const W = Math.ceil((maxX - minX) / PIXEL_KM);
  const H = Math.ceil((maxY - minY) / PIXEL_KM);
  const [minLon, minLat] = proj.toLonLat([minX, minY]);
  const [maxLon, maxLat] = proj.toLonLat([minX + W * PIXEL_KM, minY + H * PIXEL_KM]);

  // Synthetic depth: deepest at the dam, shallower upstream, toward the shore and up side arms
  const depth = new Float32Array(W * H);
  const full = new Uint8Array(W * H);
  const inside = [];
  for (let r = 0; r < H; r++) {
    const y = minY + (H - r - 0.5) * PIXEL_KM; // row 0 = north
    for (let c = 0; c < W; c++) {
      const x = minX + (c + 0.5) * PIXEL_KM;
      let dep = 0;
      arms.forEach((arm, ai) => {
        const [bx0, by0, bx1, by1] = arm.bbox;
        if (x < bx0 || x > bx1 || y < by0 || y > by1) return;
        const n = nearestOnArm(arm, x, y);
        if (n.d >= n.w || (ai === 0 && n.before)) return; // nothing downstream of the dam wall
        const along = Math.pow(Math.max(0, 1 - (arm.s0 + n.s) / L), 1.3);
        const lateral = 1 - (n.d / n.w) ** 2;
        dep = Math.max(dep, 0.02 + along * (0.25 + 0.75 * lateral));
      });
      if (dep > 0) {
        const idx = r * W + c;
        depth[idx] = dep;
        full[idx] = 1;
        inside.push(idx);
      }
    }
  }

  // Outline polygon = traced boundary of the full-reservoir raster (so overlays and outline agree)
  const ringPx = simplifyRing(traceOuterRing(full, W, H), 0.75);
  const ring = ringPx.map(([c, r]) => proj.toLonLat([minX + c * PIXEL_KM, minY + (H - r) * PIXEL_KM]).map((v) => round(v, 5)));

  return {
    ring,
    areaKm2: inside.length * PIXEL_KM * PIXEL_KM,
    grid: { W, H, minX, minY, depth, inside },
    bounds: [[round(minLon, 6), round(minLat, 6)], [round(maxLon, 6), round(maxLat, 6)]],
  };
}

/** Water mask for a target area: keep the deepest pixels (with a little month-specific noise). */
function waterMask(model, targetKm2, monthIdx) {
  const { W, minX, minY, depth, inside } = model.grid;
  const H = model.grid.H;
  const ph = monthIdx * 0.77;
  const scored = inside.map((idx) => {
    const r = Math.floor(idx / W);
    const c = idx % W;
    const x = minX + (c + 0.5) * PIXEL_KM;
    const y = minY + (H - r - 0.5) * PIXEL_KM;
    const noise =
      0.5 * Math.sin(x * 0.9 + ph) * Math.sin(y * 1.3 + ph * 0.7) +
      0.3 * Math.sin(x * 2.7 - y * 1.9 + ph * 1.3) +
      0.2 * (hash(r, c, monthIdx) - 0.5);
    return [idx, depth[idx] + 0.035 * noise];
  });
  scored.sort((a, b) => b[1] - a[1]);
  const pixelKm2 = PIXEL_KM * PIXEL_KM;
  const k = Math.min(scored.length, Math.round(targetKm2 / pixelKm2));
  const mask = new Uint8Array(W * H);
  for (let i = 0; i < k; i++) mask[scored[i][0]] = 1;
  return { mask, areaKm2: k * pixelKm2 };
}

function maskToPNG(model, mask) {
  const { W, H } = model.grid;
  const rgba = Buffer.alloc(W * H * 4);
  for (let r = 0; r < H; r++) {
    for (let c = 0; c < W; c++) {
      const i = r * W + c;
      if (!mask[i]) continue;
      const edge =
        c === 0 || r === 0 || c === W - 1 || r === H - 1 ||
        !mask[i - 1] || !mask[i + 1] || !mask[i - W] || !mask[i + W];
      const o = i * 4;
      if (edge) {
        rgba[o] = 140; rgba[o + 1] = 220; rgba[o + 2] = 255; rgba[o + 3] = 255;
      } else {
        rgba[o] = 18; rgba[o + 1] = 120; rgba[o + 2] = 235; rgba[o + 3] = 215;
      }
    }
  }
  return encodePNG(W, H, rgba);
}

// ---------------------------------------------------------------------------
// Build everything
// ---------------------------------------------------------------------------
function writeJSON(path, data) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(data, null, 2) + '\n');
}

function main() {
  rmSync(join(OUT, 'extents'), { recursive: true, force: true });
  rmSync(join(OUT, 'timeseries'), { recursive: true, force: true });
  mkdirSync(join(OUT, 'extents'), { recursive: true });
  mkdirSync(join(OUT, 'timeseries'), { recursive: true });

  const extentIndex = {};
  const features = [];
  const latestByReservoir = [];
  const lastMonth = MONTHS[MONTHS.length - 1];

  for (const def of RESERVOIRS) {
    const model = buildReservoirModel(def);
    const full = model.areaKm2;
    const areaAt = (fillPct) => full * Math.pow(Math.max(0, Math.min(100, fillPct)) / 100, AREA_EXP);

    const series = [];
    MONTHS.forEach((month, mi) => {
      const cal = Number(month.slice(5)) - 1;
      const fill = def.official_fill[month];
      const isNisar = month >= def.nisar_from;
      const quality = def.partial_months.includes(month) ? 'partial' : 'good';

      // "Measured" SAR area = area–storage relation ± a little sensor noise
      const sensorNoise = 1 + (hash(mi, 42) - 0.5) * 0.04;
      const target = Math.min(full, areaAt(fill) * sensorNoise);
      const { mask, areaKm2 } = waterMask(model, target, mi);

      const nf = NORMAL_FILL[cal];
      const normal = areaAt(nf);
      const p10 = areaAt(Math.max(10, nf - 20));
      const p90 = areaAt(Math.min(100, nf + 20));
      const std = (p90 - p10) / 2.563;
      const pct = (areaKm2 / normal) * 100;

      const key = `${def.reservoir_id}_${month}`;
      writeFileSync(join(OUT, 'extents', `${key}.png`), maskToPNG(model, mask));
      extentIndex[key] = { bounds: model.bounds };

      series.push({
        month,
        area_km2: round(areaKm2, 2),
        normal_km2: round(normal, 2),
        p10_km2: round(p10, 2),
        p90_km2: round(p90, 2),
        pct_of_normal: round(pct, 1),
        z_score: round((areaKm2 - normal) / std, 2),
        status: classify(pct),
        sensor: isNisar ? 'NISAR' : 'S1',
        n_obs: isNisar ? (quality === 'partial' ? 1 : 2 + (mi % 2)) : 4 + (mi % 2),
        quality,
        official_fill_pct: fill,
      });
    });

    // Month-over-month and year-over-year change
    series.forEach((row, i) => {
      const prev = series[i - 1];
      const lastYear = series.find((r) => r.month === `${Number(row.month.slice(0, 4)) - 1}${row.month.slice(4)}`);
      row.mom_change_pct = prev ? round(((row.area_km2 - prev.area_km2) / prev.area_km2) * 100, 1) : null;
      row.yoy_change_pct = lastYear ? round(((row.area_km2 - lastYear.area_km2) / lastYear.area_km2) * 100, 1) : null;
    });

    writeJSON(join(OUT, 'timeseries', `${def.reservoir_id}.json`), {
      reservoir_id: def.reservoir_id,
      series,
    });

    const latest = series.find((r) => r.month === lastMonth);
    latestByReservoir.push({ def, latest });
    features.push({
      type: 'Feature',
      properties: {
        reservoir_id: def.reservoir_id,
        name: def.name,
        basin: def.basin,
        river: def.river,
        capacity_mcm: def.capacity_mcm,
        dam_year: def.dam_year,
        polygon_area_km2: round(full, 1),
        priority: def.priority,
        confidence: full < 0.5 ? 'low' : 'high',
        // latest status merged in (Contract 4)
        month: latest.month,
        area_km2: latest.area_km2,
        normal_km2: latest.normal_km2,
        pct_of_normal: latest.pct_of_normal,
        status: latest.status,
        mom_change_pct: latest.mom_change_pct,
        yoy_change_pct: latest.yoy_change_pct,
        official_fill_pct: latest.official_fill_pct,
      },
      geometry: { type: 'Polygon', coordinates: [model.ring] },
    });
    console.log(
      `${def.reservoir_id} ${def.name}: polygon ${full.toFixed(1)} km², raster ${model.grid.W}×${model.grid.H}, ` +
        `${series.length} months, latest ${latest.status} (${latest.pct_of_normal}% of normal)`,
    );
  }

  const meta = {
    mock: true,
    generated_by: 'web/scripts/generate-mock-data.mjs',
    note: 'Illustrative mock data for UI development. Not real measurements.',
  };

  writeJSON(join(OUT, 'reservoirs.geojson'), { type: 'FeatureCollection', metadata: meta, features });

  writeJSON(join(OUT, 'basins.geojson'), {
    type: 'FeatureCollection',
    metadata: meta,
    features: BASINS.map((b) => {
      const members = latestByReservoir.filter((r) => r.def.basin_id === b.basin_id);
      const area = members.reduce((acc, r) => acc + r.latest.area_km2, 0);
      const normal = members.reduce((acc, r) => acc + r.latest.normal_km2, 0);
      const pct = normal ? (area / normal) * 100 : null;
      return {
        type: 'Feature',
        properties: {
          basin_id: b.basin_id,
          name: b.name,
          n_reservoirs: members.length,
          capacity_mcm: members.reduce((acc, r) => acc + r.def.capacity_mcm, 0),
          month: lastMonth,
          area_km2: round(area, 2),
          normal_km2: round(normal, 2),
          pct_of_normal: round(pct, 1),
          status: classify(pct),
        },
        geometry: { type: 'Polygon', coordinates: [b.ring] },
      };
    }),
  });

  writeJSON(join(OUT, 'months.json'), MONTHS);
  writeJSON(join(OUT, 'extents', 'index.json'), extentIndex);
  console.log(`Wrote mock dataset to ${OUT}`);
}

main();
