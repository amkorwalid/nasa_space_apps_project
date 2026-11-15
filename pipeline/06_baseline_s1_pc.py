"""Step 06 (Track C) - Sentinel-1 long-term baseline on Microsoft Planetary Computer.

Same Contract 5 algorithm as the NISAR steps (pipeline/utils/sar.py), run scene by scene on
Sentinel-1 RTC (VV, gamma0, terrain corrected) from 2015 to the last complete month:
one relative orbit per reservoir, up to 3 scenes per month, JRC max-extent search zone,
HAND-style terrain filter from the Copernicus DEM, 3x3 opening, blobs < 10 px removed,
monthly majority vote. No account is needed (anonymous SAS tokens).

Outputs: data/processed/monthly_area_s1.csv       (Contract 2, sensor = S1)
         data/processed/scene_areas_s1.csv        (one row per scene, for QA)
         data/processed/extents_s1/<id>_<YYYY-MM>.png + index.json   (web overlays)
         data/processed/quicklooks/s1/<id>_<YYYY-MM>.png            (radar + water, last months)

Usage:
    python pipeline/06_baseline_s1_pc.py --reservoir demo
    python pipeline/06_baseline_s1_pc.py --reservoir priority --start 2015-01
    python pipeline/06_baseline_s1_pc.py --reservoir al_massira --start 2026-01 --force
The Earth Engine version of the same step is pipeline/06_baseline_s1_gee.py.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import geo, s1  # noqa: E402
from utils.io import load_settings, month_range, path, read_json, rel, resolve_reservoirs, step, upsert_csv, write_json  # noqa: E402

MONTHLY_COLS = ["reservoir_id", "month", "sensor", "area_km2", "n_obs", "quality"]
SCENE_COLS = ["reservoir_id", "date", "sensor", "orbit", "area_km2", "threshold_db", "threshold_method",
              "valid_fraction"]


def done_months(file: Path, rid: str) -> set:
    if not file.is_file():
        return set()
    with open(file, newline="", encoding="utf-8") as f:
        return {r["month"] for r in csv.DictReader(f) if r["reservoir_id"] == rid}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reservoir", default="priority")
    ap.add_argument("--start", default=None, help="YYYY-MM (default baseline.start)")
    ap.add_argument("--end", default=None, help="YYYY-MM (default last complete month)")
    ap.add_argument("--orbit", type=int, default=None, help="force a relative orbit")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="recompute months already in the CSV")
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    base = cfg["baseline"]
    months = month_range(a.start or base["start"], a.end or base["end"])
    feats = resolve_reservoirs(cfg, a.reservoir)
    zones = {f["properties"]["reservoir_id"]: geo.to_shape(f["geometry"])
             for f in read_json(path(cfg, "processed", "analysis_zones.geojson"))["features"]}
    out = path(cfg, "processed", "monthly_area_s1.csv")
    scenes_out = path(cfg, "processed", "scene_areas_s1.csv")
    idx_file = path(cfg, "processed", "extents_s1", "index.json")
    meta_file = path(cfg, "processed", "s1_runs.json")
    index = read_json(idx_file, default={})
    runs = read_json(meta_file, default={})
    step(f"Sentinel-1 baseline: {len(feats)} reservoir(s), {months[0]}..{months[-1]} ({len(months)} months)")

    for n, f in enumerate(feats, 1):
        rid = f["properties"]["reservoir_id"]
        step(f"[{n}/{len(feats)}] {rid} {f['properties']['name']}")
        try:
            monthly, scenes, ext, meta = s1.process_reservoir(
                cfg, f, zones[rid], months, set() if a.force else done_months(out, rid),
                cfg["web"]["start_month"], a.workers or base["workers"], a.orbit)
        except Exception as e:
            step(f"  {rid} failed: {e}")
            continue
        upsert_csv(out, monthly, ["reservoir_id", "month", "sensor"], MONTHLY_COLS)
        upsert_csv(scenes_out, scenes, ["reservoir_id", "date", "sensor"], SCENE_COLS)
        index.update(ext)
        write_json(idx_file, index, indent=1)
        runs[rid] = meta
        write_json(meta_file, runs, indent=1)
        good = sum(r["quality"] == "good" for r in monthly)
        step(f"  {rid}: {len(monthly)} new months ({good} good) -> {rel(out)}")
    step("Done.")


if __name__ == "__main__":
    main()
