"""Sentinel-1 RTC monthly water areas on Planetary Computer (Contract 5, scene by scene +
monthly majority vote), plus the reference layers (JRC max extent, Copernicus DEM) shared
with the NISAR steps."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from scipy.ndimage import binary_dilation

from . import geo, sar, stac
from .io import month_bounds, path, read_json, step, write_json


# ---------------------------------------------------------------------------
# Reference layers on a grid (cached)
# ---------------------------------------------------------------------------
def reference_layers(cfg, rid: str, reservoir_geom, zone_geom, grid, tag: str) -> dict:
    """JRC max extent + DEM on `grid` and the masks derived from them:
    reservoir (polygon), search zone ((JRC U polygon) + 500 m, inside the analysis zone), hand_ok."""
    cache = path(cfg, "reference", "rasters", f"{rid}_{tag}.npz")
    if cache.is_file():
        d = np.load(cache)
        jrc, dem = d["jrc"].astype(bool), d["dem"]
    else:
        jrc = stac.jrc_max_extent(grid, zone_geom)
        dem = stac.copernicus_dem(grid, zone_geom)
        dem = dem if dem is not None else np.full((grid.height, grid.width), np.nan, "float32")
        np.savez_compressed(cache, jrc=jrc, dem=dem.astype("float32"), grid=np.array([str(grid.to_dict())]))
    det = cfg["detection"]
    reservoir = grid.rasterize(reservoir_geom, all_touched=True)
    zone = grid.rasterize(zone_geom, all_touched=True)
    px = max(1, int(round(cfg["catalog"]["zone_buffer_m"] / grid.res)))
    search = binary_dilation(jrc | reservoir, iterations=px) & zone
    hand_ok = sar.hand_ok_mask(dem, jrc | reservoir, det["hand_max_m"])
    return {"jrc": jrc, "dem": dem, "reservoir": reservoir, "zone": zone, "search": search,
            "hand_ok": hand_ok, "land_clip": np.ones_like(zone)}


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------
def group_scenes(items: list[dict], orbit: int) -> dict:
    """{month: [[slice items of one date], ...]} for one relative orbit, dates ascending."""
    by_date: dict = {}
    for it in items:
        if it["orbit"] == orbit:
            by_date.setdefault(it["date"], []).append(it)
    months: dict = {}
    for d in sorted(by_date):
        months.setdefault(d[:7], []).append(by_date[d])
    return months


def pick_even(seq: list, n: int) -> list:
    if len(seq) <= n:
        return seq
    idx = np.linspace(0, len(seq) - 1, n).round().astype(int)
    return [seq[i] for i in sorted(set(idx))]


def read_scene(group: list[dict], grid, pol: str = "vv") -> np.ndarray | None:
    arrs = [stac.read_to_grid(it[pol], grid, "average") for it in group if it.get(pol)]
    lin = stac.mosaic(arrs, "first")
    if lin is None:
        return None
    lin[(lin <= 0)] = np.nan
    return sar.to_db(lin)


def detect_scene(group, grid, ref, params: sar.DetectParams, vh_params: sar.DetectParams | None = None):
    """VV detection (Contract 5). When VV finds no water mode (fallback) - typically a lake
    roughened by wind, which turns calm-water darkness into bright clutter in VV - the scene is
    re-detected on VH, which wind affects much less. VH is kept only if it shows a water-like dark
    mode, so an empty lake bed (dark mean around -19 dB VH) still yields no water."""
    vv = read_scene(group, grid, "vv")
    if vv is None:
        return None, None
    vh = read_scene(group, grid, "vh") if params.use_cross else None
    valid = np.isfinite(vv)
    d = sar.detect_water(vv, valid, ref["search"], params, reservoir=ref["reservoir"],
                         hand_ok=ref["hand_ok"], cross_db=vh)
    if d.method == "fallback" and vh_params is not None:
        vh = vh if vh is not None else read_scene(group, grid, "vh")
        if vh is not None:
            dv = sar.detect_water(vh, valid & np.isfinite(vh), ref["search"], vh_params,
                                  reservoir=ref["reservoir"], hand_ok=ref["hand_ok"])
            if dv.method in ("otsu", "capped"):
                dv.method = "vh"
                return dv, valid & np.isfinite(vh)
    return d, valid


def vh_params_from_cfg(det: dict) -> sar.DetectParams | None:
    s = det["s1"]
    if not s.get("vh_rescue"):
        return None
    base = sar.DetectParams.from_cfg(det, "s1")
    from dataclasses import replace

    return replace(base, plausible_db=tuple(s["vh_plausible_db"]), fallback_db=float(s["vh_plausible_db"][1]),
                   cap_dark_mean_db=float(s["vh_cap_dark_mean_db"]), otsu_region="search", use_cross=False)


# ---------------------------------------------------------------------------
# One reservoir, many months
# ---------------------------------------------------------------------------
def process_reservoir(cfg, feat: dict, zone_geom, months: list[str], done: set, images_from: str,
                      workers: int = 8, orbit: int | None = None, quicklook_last: int = 3):
    """Returns (monthly_rows, scene_rows, extents_index_entries, meta)."""
    p = feat["properties"]
    rid = p["reservoir_id"]
    res_geom = geo.to_shape(feat["geometry"])
    base = cfg["baseline"]
    det = cfg["detection"]
    params = sar.DetectParams.from_cfg(det, "s1")
    vh_params = vh_params_from_cfg(det)
    grid = geo.grid_for(zone_geom, base["scale_m"], margin_m=det["land_buffer_m"])
    ref = reference_layers(cfg, rid, res_geom, zone_geom, grid, f"s1_{base['scale_m']}m")
    px_area = grid.res ** 2

    items_file = path(cfg, "interim", "s1", rid, "items.json")
    cached = read_json(items_file, default={})
    lo, hi = month_bounds(months[0])[0], month_bounds(months[-1])[1]
    if cached.get("range") == [lo, hi]:
        items = cached["items"]
    else:
        items = []
        for y in range(int(lo[:4]), int(hi[:4]) + 1):  # one search per year keeps responses small
            a, b = max(lo, f"{y}-01-01"), min(hi, f"{y + 1}-01-01")
            if a < b:
                items += stac.s1_items(zone_geom, a, b)
        write_json(items_file, {"range": [lo, hi], "items": items})
    orbit = stac.choose_orbit(items, orbit)
    if orbit is None:
        return [], [], {}, {"orbit": None, "n_items": 0}
    by_month = group_scenes(items, orbit)
    todo = [m for m in months if m in by_month and m not in done]
    step(f"  {rid} {p['name']}: {len(items)} S1 items, orbit {orbit}, "
         f"{len(by_month)} months with data, {len(todo)} to process (grid {grid.width}x{grid.height} @ {grid.res:.0f} m)")

    recent = set(sorted(by_month)[-quicklook_last:])
    ext_dir = path(cfg, "processed", "extents_s1")
    ql_dir = path(cfg, "processed", "quicklooks", "s1")

    def run_month(m):
        n_max = base["max_scenes_per_month"] if m >= images_from else             base.get("max_scenes_per_month_archive", base["max_scenes_per_month"])
        groups = pick_even(by_month[m], n_max)
        masks, valids, scenes = [], [], []
        last_db = None
        for g in groups:
            try:
                d, valid = detect_scene(g, grid, ref, params, vh_params)
            except Exception as e:  # one bad scene never stops the month
                print(f"      {rid} {g[0]['date']}: read failed ({str(e)[:120]})")
                continue
            if d is None:
                continue
            masks.append(d.water)
            valids.append(valid)
            last_db = d.co_filtered
            scenes.append({"reservoir_id": rid, "date": g[0]["date"], "sensor": "S1", "orbit": orbit,
                           "area_km2": round(d.area_km2(px_area), 3), "threshold_db": round(d.threshold_db, 2),
                           "threshold_method": d.method, "valid_fraction": round(d.valid_fraction, 3)})
        if not masks:
            return None
        comp, nvotes = sar.majority_composite(masks, valids, det["majority"])
        valid_frac = float(np.mean([s["valid_fraction"] for s in scenes]))
        q = sar.month_quality(valid_frac, len(masks), any(s["threshold_method"] == "fallback" for s in scenes))
        row = {"reservoir_id": rid, "month": m, "sensor": "S1",
               "area_km2": round(float(comp.sum() * px_area / 1e6), 3), "n_obs": len(masks), "quality": q}
        ext = None
        if m >= images_from:
            key = f"{rid}_{m}"
            ext = (key, {"bounds": sar.mask_to_png(comp, grid, ext_dir / f"{key}.png"), "sensor": "S1"})
        if m in recent and last_db is not None:
            sar.quicklook(last_db, comp, ref["search"], ql_dir / f"{rid}_{m}.png",
                          f"{rid} {p['name']} {m} S1 VV - water {row['area_km2']:.1f} km2 ({len(masks)} scenes)")
        return row, scenes, ext

    monthly, scene_rows, index = [], [], {}
    t0 = time.time()
    def safe_month(m):
        try:
            return run_month(m)
        except Exception as e:  # never lose a whole reservoir to one month
            print(f"      {rid} {m}: failed ({str(e)[:150]})")
            return None

    with ThreadPoolExecutor(workers) as ex:
        for i, res in enumerate(ex.map(safe_month, todo), 1):
            if res is None:
                continue
            row, scenes, ext = res
            monthly.append(row)
            scene_rows += scenes
            if ext:
                index[ext[0]] = ext[1]
            if i % 24 == 0:
                step(f"    {rid}: {i}/{len(todo)} months ({time.time() - t0:.0f} s)")
    meta = {"orbit": orbit, "n_items": len(items), "grid": grid.to_dict(),
            "search_zone_km2": round(float(ref["search"].sum() * px_area / 1e6), 2),
            "hand_filter": ref["hand_ok"] is not None}
    return monthly, scene_rows, index, meta
