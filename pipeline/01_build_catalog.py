"""Step 01 (Track A) - polygons -> reservoir catalog (Contract 1).

Inputs : geo_data/{dams,lakes,ponds}.geojson (merged JRC max extent + OSM polygons with
         GDW / Wikidata / GeoDAR attributes), HydroBASINS level 6 (downloaded on first run)
Outputs: data/processed/reservoirs.geojson     Contract 1 (+ extra attributes)
         data/processed/analysis_zones.geojson same IDs, polygon + 500 m buffer
         data/processed/basins.geojson         basin outlines (HydroBASINS, dissolved)
         data/reference/id_map.csv             source id -> stable MAR_#### (append-only)
         contracts/demo_bboxes.geojson         bounding boxes of the 5 demo reservoirs

Usage:   python pipeline/01_build_catalog.py --country MAR
"""
from __future__ import annotations

import argparse
import csv
import io as _io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shapely.geometry import box, mapping  # noqa: E402

from utils import geo  # noqa: E402
from utils.io import ROOT, load_settings, path, rel, slugify, step, write_json  # noqa: E402

TYPE_BY_TIER = {"A_reservoir": "reservoir", "B_natural_lake": "lake", "C_small": "pond"}
PREFIXES = [r"lac du barrage", r"r[ée]servoir du barrage", r"retenue du barrage", r"barrage d['’]",
            r"barrage de", r"barrage du", r"barrage", r"lac de", r"lac d['’]", r"lac"]


def display_name(p: dict) -> str:
    raw = (p.get("name") or p.get("dam_name") or "").strip()
    if not raw:
        kind = TYPE_BY_TIER.get(p.get("tier"), "water body")
        return f"Unnamed {kind} ({p.get('target_id')})"
    low = raw.lower()
    for pre in PREFIXES:
        m = re.match(pre + r"\s*", low)
        if m and len(raw) > m.end():
            out = raw[m.end():].strip()
            return out[0].upper() + out[1:]
    return raw


def as_year(v):
    try:
        y = int(str(v)[:4])
        return y if 1800 < y < 2100 else None
    except (TypeError, ValueError):
        return None


def as_float(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def load_id_map(file: Path) -> dict:
    if not file.is_file():
        return {}
    with open(file, newline="", encoding="utf-8") as f:
        return {r["source_id"]: r["reservoir_id"] for r in csv.DictReader(f)}


def save_id_map(file: Path, mapping_: dict, names: dict) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["reservoir_id", "source_id", "name"])
        for sid, rid in sorted(mapping_.items(), key=lambda kv: kv[1]):
            w.writerow([rid, sid, names.get(sid, "")])


def ensure_hydrobasins(cfg) -> Path | None:
    shp = ROOT / cfg["catalog"]["hydrobasins"]["shapefile"]
    if shp.is_file():
        return shp
    url = cfg["catalog"]["hydrobasins"]["url"]
    step(f"Downloading HydroBASINS ({url})")
    try:
        data = urllib.request.urlopen(url, timeout=300).read()
    except Exception as e:
        step(f"  HydroBASINS download failed ({e}); basins will be convex hulls of their reservoirs")
        return None
    shp.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(_io.BytesIO(data)) as z:
        for n in z.namelist():
            if n.endswith((".shp", ".shx", ".dbf", ".prj", ".cpg")):
                (shp.parent / Path(n).name).write_bytes(z.read(n))
    return shp


def build_basins(cfg, feats: list[dict], shapes: dict) -> dict:
    """Basin outlines: HydroBASINS level-6 units whose MAIN_BAS hosts reservoirs of that
    national basin, dissolved per basin name (each MAIN_BAS goes to its majority basin)."""
    by_basin: dict = {}
    votes: dict = {}
    for f in feats:
        p = f["properties"]
        b = p.get("basin") or "Unknown"
        by_basin.setdefault(b, []).append(p["reservoir_id"])
        mb = p.get("main_bas")
        if mb:
            votes.setdefault(int(float(mb)), {}).setdefault(b, 0)
            votes[int(float(mb))][b] += 1
    owner = {mb: max(v, key=v.get) for mb, v in votes.items()}
    shp = ensure_hydrobasins(cfg)
    geoms: dict = {}
    if shp is not None:
        import geopandas as gpd

        allb = [shapes[i] for ids in by_basin.values() for i in ids]
        minx, miny, maxx, maxy = geo.union(allb).bounds
        hb = gpd.read_file(shp, bbox=(minx - 2, miny - 2, maxx + 2, maxy + 2))
        hb = hb[hb["MAIN_BAS"].isin(owner.keys())]
        for name in by_basin:
            mbs = [mb for mb, o in owner.items() if o == name]
            sub = hb[hb["MAIN_BAS"].isin(mbs)]
            if len(sub):
                geoms[name] = sub.geometry.union_all().buffer(0)
    out = []
    for name, ids in sorted(by_basin.items()):
        g = geoms.get(name)
        method = "hydrobasins_lev06"
        if g is None or g.is_empty:
            g = geo.buffer_m(geo.union([shapes[i] for i in ids]).convex_hull, 10000)
            method = "convex_hull"
        out.append({"type": "Feature",
                    "properties": {"basin_id": slugify(name).upper(), "name": name, "n_reservoirs": len(ids),
                                   "capacity_mcm": round(sum(next(f["properties"].get("capacity_mcm") or 0
                                                                  for f in feats if f["properties"]["reservoir_id"] == i)
                                                             for i in ids), 1),
                                   "geometry_method": method},
                    "geometry": geo.web_geometry(g, 0.005, 4)})
    return {"type": "FeatureCollection", "features": out}


def jrc_outline(sid: str, roi, res_m: float = 30.0):
    """Maximum water outline = JRC GSW 'extent' pixels inside the region of interest, vectorised.
    Returns a WGS84 (Multi)Polygon or None when JRC has no water there."""
    import numpy as np
    from rasterio.features import shapes as rio_shapes
    from shapely.geometry import shape as to_geom

    from utils import stac

    grid = geo.grid_for(roi, res_m, margin_m=0)
    ext = stac.jrc_max_extent(grid, roi) & grid.rasterize(roi, all_touched=True)
    if ext.sum() < 3:
        return None
    polys = [to_geom(g) for g, v in rio_shapes(ext.astype("uint8"), mask=ext, transform=grid.transform) if v == 1]
    polys = [p for p in polys if p.area >= 2 * res_m * res_m]
    if not polys:
        return None
    g = geo.union(polys).buffer(res_m / 2).buffer(-res_m / 2)
    g = g.simplify(res_m / 2)
    return geo.to_crs(g, grid.crs, 4326).buffer(0)


def outlines_for(cfg, kept) -> dict:
    """Cached JRC outlines per source id (data/reference/jrc_outlines.geojson)."""
    from concurrent.futures import ThreadPoolExecutor

    cache_file = path(cfg, "reference", "jrc_outlines.geojson")
    cache = {}
    if cache_file.is_file():
        for f in json.load(open(cache_file, encoding="utf-8"))["features"]:
            cache[f["properties"]["source_id"]] = geo.to_shape(f["geometry"]) if f["geometry"] else None
    todo = [(p["target_id"], g) for _, p, g in kept if p["target_id"] not in cache]
    if todo:
        step(f"Tracing JRC max-extent outlines for {len(todo)} water bodies (Planetary Computer)...")

        def run(t):
            sid, roi = t
            try:
                return sid, jrc_outline(sid, roi)
            except Exception as e:  # network or no tile
                print(f"    {sid}: JRC outline failed ({e}); using the region polygon")
                return sid, "fail"

        done = 0
        with ThreadPoolExecutor(8) as ex:
            for sid, g in ex.map(run, todo):
                done += 1
                if g != "fail":
                    cache[sid] = g
                if done % 50 == 0:
                    step(f"    {done}/{len(todo)}")
        write_json(cache_file, {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"source_id": k},
             "geometry": geo.round_coords(mapping(v), 6) if v is not None else None} for k, v in sorted(cache.items())]})
    return cache


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", default=None, help="ISO3 country code used in reservoir IDs (default from settings)")
    ap.add_argument("--no-jrc", action="store_true", help="skip JRC outline tracing (use the region polygons)")
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    cc = (a.country or cfg["country"]).upper()
    cat = cfg["catalog"]

    # ---- 1. load sources ------------------------------------------------------
    raw = []
    for src in cat["sources"]:
        data = json.load(open(ROOT / src, encoding="utf-8"))
        for f in data["features"]:
            if f.get("geometry"):
                raw.append((src, f["properties"] or {}, geo.to_shape(f["geometry"])))
    step(f"{len(raw)} polygons read from {len(cat['sources'])} file(s)")

    # ---- 2. rank + deduplicate (spatial overlap) -------------------------------
    tier_rank = {"A_reservoir": 0, "B_natural_lake": 1, "C_small": 2}
    raw.sort(key=lambda t: (tier_rank.get(t[1].get("tier"), 3), -(as_float(t[1].get("capacity_mm3")) or 0),
                            -(as_float(t[1].get("area_max_km2")) or 0), t[1].get("target_id", "")))
    kept, dropped = [], 0
    for src, p, g in raw:
        dup = False
        for _, _, kg in kept:
            if g.intersects(kg):
                inter = g.intersection(kg).area
                if inter / min(g.area, kg.area) > cat["dedup_overlap"]:
                    dup = True
                    break
        if dup:
            dropped += 1
        else:
            kept.append((src, p, g))
    step(f"{len(kept)} unique water bodies ({dropped} overlapping duplicates removed)")

    # ---- 3. stable IDs ---------------------------------------------------------
    id_file = ROOT / cat["id_map"]
    idmap = load_id_map(id_file)
    used = {int(v.split("_")[1]) for v in idmap.values()}
    nxt = max(used, default=0) + 1
    for _, p, _ in sorted(kept, key=lambda t: (tier_rank.get(t[1].get("tier"), 3), t[1].get("target_id", ""))):
        sid = p.get("target_id")
        if sid and sid not in idmap:
            idmap[sid] = f"{cc}_{nxt:04d}"
            nxt += 1

    # ---- 4. attributes -----------------------------------------------------------
    caps = sorted((as_float(p.get("capacity_mm3")) or 0, p.get("target_id")) for _, p, _ in kept
                  if p.get("tier") == "A_reservoir")
    priority_ids = {sid for _, sid in sorted(caps, reverse=True)[:cat["n_priority"]]}
    demo = set(cat.get("demo_reservoirs", []))
    outlines = {} if a.no_jrc else outlines_for(cfg, kept)
    feats, zones, shapes, names = [], [], {}, {}
    for _, p, roi in kept:
        sid = p["target_id"]
        rid = idmap[sid]
        outline = outlines.get(sid)
        src_area = as_float(p.get("area_max_km2"))
        if outline is not None and src_area and geo.area_km2(outline) < 0.5 * src_area:
            # Dam filled after the JRC record (ends 2021, e.g. M'Dez 2025): JRC misses the lake.
            outline = None
        g = outline if outline is not None and not outline.is_empty else roi
        area = geo.area_km2(g) if outline is not None else (as_float(p.get("area_max_km2")) or geo.area_km2(g))
        name = display_name(p)
        names[sid] = name
        low = area < cat["low_confidence_km2"] or p.get("sar_size_class") == "too_small"
        props = {
            "reservoir_id": rid,
            "name": name,
            "basin": p.get("basin") or None,
            "capacity_mcm": as_float(p.get("capacity_mm3")),
            "dam_year": as_year(p.get("year_commissioned")),
            "polygon_area_km2": round(area, 3),
            "priority": sid in priority_ids or sid in demo,
            "confidence": "low" if low else "high",
            # extensions
            "demo": sid in demo,
            "type": TYPE_BY_TIER.get(p.get("tier"), "other"),
            "official_name": p.get("name") or p.get("dam_name") or None,
            "name_ar": p.get("name_ar") or None,
            "river": p.get("river") or None,
            "slug": slugify(name),
            "source_id": sid,
            "main_bas": p.get("main_bas") or None,
            "sar_size_class": p.get("sar_size_class") or None,
            "geometry_source": "jrc_gsw_max_extent" if outline is not None else (p.get("geometry_source") or "roi"),
            "area_max_km2_source": as_float(p.get("area_max_km2")),
        }
        feats.append({"type": "Feature", "properties": props, "geometry": geo.round_coords(mapping(g), 6)})
        # analysis zone = region of interest U (max-extent outline + 500 m)
        z = geo.union([roi, geo.buffer_m(g, cat["zone_buffer_m"])]).buffer(0)
        zones.append({"type": "Feature", "properties": {"reservoir_id": rid, "name": name,
                                                         "priority": props["priority"],
                                                         "buffer_m": cat["zone_buffer_m"]},
                      "geometry": mapping(z)})
        shapes[rid] = g
    feats.sort(key=lambda f: f["properties"]["reservoir_id"])
    zones.sort(key=lambda f: f["properties"]["reservoir_id"])

    meta = {"country": cc, "n": len(feats), "sources": cat["sources"],
            "note": "Polygons = JRC max water extent merged with OSM (geo_data/); IDs never change."}
    write_json(path(cfg, "processed", "reservoirs.geojson"),
               {"type": "FeatureCollection", "metadata": meta, "features": feats})
    write_json(path(cfg, "processed", "analysis_zones.geojson"),
               {"type": "FeatureCollection", "metadata": meta, "features": zones})
    save_id_map(id_file, idmap, names)
    basins = build_basins(cfg, feats, shapes)
    write_json(path(cfg, "processed", "basins.geojson"), basins)

    # Demo bounding boxes (Contract kickoff item)
    demo_boxes = [{"type": "Feature", "properties": {"reservoir_id": f["properties"]["reservoir_id"],
                                                     "name": f["properties"]["name"]},
                   "geometry": mapping(box(*geo.buffer_m(shapes[f["properties"]["reservoir_id"]], 1000).bounds))}
                  for f in feats if f["properties"]["demo"]]
    write_json(ROOT / "contracts" / "demo_bboxes.geojson",
               {"type": "FeatureCollection", "features": demo_boxes}, indent=1)

    n_pri = sum(f["properties"]["priority"] for f in feats)
    n_low = sum(f["properties"]["confidence"] == "low" for f in feats)
    step(f"Catalog: {len(feats)} water bodies, {n_pri} priority, {n_low} low confidence, "
         f"{len(basins['features'])} basins")
    for f in feats:
        if f["properties"]["priority"]:
            p = f["properties"]
            print(f"    {p['reservoir_id']}  {p['name'][:34]:34s} {p['basin'] or '':20s} "
                  f"{p['capacity_mcm'] or 0:7.0f} Mm3  {p['polygon_area_km2']:7.1f} km2{'  (demo)' if p['demo'] else ''}")
    step(f"Wrote {rel(path(cfg, 'processed', 'reservoirs.geojson'))}, analysis_zones.geojson, basins.geojson")


if __name__ == "__main__":
    main()
