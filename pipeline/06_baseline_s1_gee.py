"""Step 06 (Track C, Earth Engine variant) - Sentinel-1 monthly water area in Google Earth Engine.

Same Contract 5 algorithm as pipeline/06_baseline_s1_pc.py, computed on Google's servers:
  * COPERNICUS/S1_GRD, IW, VV, one relative orbit (the most frequent)
  * 5x5 median filter per scene, Otsu threshold from the month's histogram over zone + 1 km land
    (fallback when implausible), applied to every scene of the month
  * search zone = (JRC/GSW1_4 max_extent U reservoir polygon) + 500 m, inside the analysis zone
  * HAND filter: MERIT/Hydro/v1_0_1 'hnd' < 15 m
  * 3x3 opening, blobs < 10 px removed
  * monthly majority vote: water where >= 50 % of the month's scenes say water

Prerequisites: `earthengine authenticate` once, GEE_PROJECT in .env (or --project).
Ported from prototypes/water_detection/sentinel1_gee.py (Track C prototype).

Usage:
    python pipeline/06_baseline_s1_gee.py --reservoir demo --start 2015-01
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import geo, sar  # noqa: E402
from utils.io import load_env, load_settings, month_range, path, read_json, resolve_reservoirs, step, upsert_csv  # noqa: E402

COLS = ["reservoir_id", "month", "sensor", "area_km2", "n_obs", "quality"]
HIST = (-35.0, 0.0, 140)
BATCH = 24


def run_reservoir(ee, cfg, feat, zone_geom, months):
    det, base = cfg["detection"], cfg["baseline"]
    rid = feat["properties"]["reservoir_id"]
    scale = base["scale_m"]
    lake_g = geo.to_shape(feat["geometry"]).simplify(0.0002)
    lake = ee.Geometry(mapping(lake_g))
    zone = ee.Geometry(mapping(zone_geom.simplify(0.0002)))
    window = zone.bounds().buffer(det["land_buffer_m"]).bounds()
    jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("max_extent").unmask(0)
    search = jrc.Or(ee.Image.constant(0).paint(lake, 1)).focal_max(cfg["catalog"]["zone_buffer_m"], "circle", "meters") \
        .clip(zone)
    hand_ok = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").lt(det["hand_max_m"]).unmask(1)
    allowed = search.And(hand_ok)

    col = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(lake)
           .filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")).select("VV"))
    orbits = col.aggregate_histogram("relativeOrbitNumber_start").getInfo()
    if not orbits:
        return []
    orbit = int(float(max(orbits, key=orbits.get)))
    col = col.filter(ee.Filter.eq("relativeOrbitNumber_start", orbit)) \
        .map(lambda i: i.focal_median(radius=det["median_filter_px"] // 2, kernelType="square", units="pixels")
             .copyProperties(i, ["system:time_start"]))
    step(f"  {rid}: orbit {orbit}")
    s1p = det["s1"]

    def month_info(m):
        d0 = ee.Date(ee.String(m).cat("-01"))
        mc = col.filterDate(d0, d0.advance(1, "month"))
        hist = ee.Algorithms.If(mc.size().gt(0), ee.Array(mc.median().reduceRegion(
            ee.Reducer.fixedHistogram(*HIST), window, scale, maxPixels=1e9).get("VV")).toList(), [])
        return ee.Dictionary({"month": m, "n": mc.size(), "hist": hist})

    def month_area(pair):
        pair = ee.List(pair)
        m, thr = ee.String(pair.get(0)), ee.Number(pair.get(1))
        d0 = ee.Date(m.cat("-01"))
        mc = col.filterDate(d0, d0.advance(1, "month"))

        def scene_water(img):
            w = img.lt(thr).And(allowed)
            w = w.focal_min(1, "square", "pixels").focal_max(1, "square", "pixels")
            size = w.selfMask().connectedPixelCount(det["min_blob_px"] + 1, True)
            return w.updateMask(size.gte(det["min_blob_px"])).unmask(0)

        maj = mc.map(scene_water).mean().gte(det["majority"])
        a = maj.multiply(ee.Image.pixelArea()).reduceRegion(ee.Reducer.sum(), zone, scale, maxPixels=1e9).get("VV")
        return ee.Dictionary({"month": m, "m2": a})

    rows = []
    for i in range(0, len(months), BATCH):
        infos = ee.List(months[i:i + BATCH]).map(month_info).getInfo()
        thr = {}
        for info in infos:
            if info["n"] and info["hist"]:
                h = np.array(info["hist"], float)
                centres = h[:, 0] + (HIST[1] - HIST[0]) / HIST[2] / 2
                t = sar.otsu_from_histogram(centres, h[:, 1])
                ok = t is not None and s1p["plausible_db"][0] <= t <= s1p["plausible_db"][1]
                thr[info["month"]] = (t if ok else s1p["fallback_db"], "otsu" if ok else "fallback", info["n"])
        if thr:
            for r in ee.List([[m, v[0]] for m, v in thr.items()]).map(month_area).getInfo():
                t, method, n = thr[r["month"]]
                rows.append({"reservoir_id": rid, "month": r["month"], "sensor": "S1",
                             "area_km2": round((r["m2"] or 0) / 1e6, 3), "n_obs": n,
                             "quality": "good" if n >= 2 and method == "otsu" else "partial"})
        step(f"    {rid}: {min(i + BATCH, len(months))}/{len(months)} months")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reservoir", default="priority")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--project", default=None)
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    load_env()
    project = a.project or os.environ.get("GEE_PROJECT")
    if not project:
        raise SystemExit("Set GEE_PROJECT in .env or pass --project.")
    import ee

    ee.Initialize(project=project)
    months = month_range(a.start or cfg["baseline"]["start"], a.end or cfg["baseline"]["end"])
    zones = {f["properties"]["reservoir_id"]: geo.to_shape(f["geometry"])
             for f in read_json(path(cfg, "processed", "analysis_zones.geojson"))["features"]}
    out = path(cfg, "processed", "monthly_area_s1.csv")
    for f in resolve_reservoirs(cfg, a.reservoir):
        rows = run_reservoir(ee, cfg, f, zones[f["properties"]["reservoir_id"]], months)
        upsert_csv(out, rows, ["reservoir_id", "month", "sensor"], COLS)
    step(f"Done -> {out}")


if __name__ == "__main__":
    main()
