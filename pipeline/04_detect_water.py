"""Step 04 (Track B) - NISAR water detection, one scene at a time (Contract 5 steps 4-6).

Otsu threshold on filtered HH (fixed fallback when not bimodal / implausible), HV check against
dry sand and smooth soil, search-zone + terrain filters, 3x3 opening, blobs < 10 px removed,
only blobs touching the reservoir kept.

Outputs: data/interim/nisar_masks/<id>/<date>.npz       (water + valid masks, for step 05)
         data/processed/scene_areas_nisar.csv            (one row per scene)
         data/processed/quicklooks/nisar/<id>_<date>.png (HH + detected water, for visual QA)

Usage:  python pipeline/04_detect_water.py --reservoir al_massira [--no-hv]
"""
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import geo, sar  # noqa: E402
from utils.io import load_settings, path, resolve_reservoirs, step, upsert_csv  # noqa: E402

SCENE_COLS = ["reservoir_id", "date", "sensor", "area_km2", "threshold_db", "threshold_method",
              "hv_threshold_db", "valid_fraction", "scene"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reservoir", default="demo")
    ap.add_argument("--no-hv", action="store_true", help="disable the HV dry-sand check")
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    params = sar.DetectParams.from_cfg(cfg["detection"], "nisar")
    params = replace(params, median_px=1, use_cross=params.use_cross and not a.no_hv)  # filtered in step 03
    rows = []
    for f in resolve_reservoirs(cfg, a.reservoir):
        rid, name = f["properties"]["reservoir_id"], f["properties"]["name"]
        files = sorted(path(cfg, "interim", "nisar_pre", rid).glob("*.npz"))
        if not files:
            continue
        step(f"{rid} {name}: {len(files)} scene(s)")
        for file in files:
            d = np.load(file, allow_pickle=False)
            grid = geo.Grid.from_dict(ast.literal_eval(str(d["grid"][0])))
            hv = d["hv_f"] if d["hv_f"].shape == d["hh_f"].shape else None
            hand = d["hand_ok"] if d["hand_ok"].shape == d["hh_f"].shape else None
            r = sar.detect_water(d["hh_f"], d["valid"], d["search"], params, reservoir=d["reservoir"],
                                 hand_ok=hand, cross_db=hv)
            area = r.area_km2(grid.res * abs(grid.transform.e))
            date = str(d["date"])
            np.savez_compressed(path(cfg, "interim", "nisar_masks", rid, f"{date}.npz"), water=r.water,
                                valid=d["valid"], grid=d["grid"], date=date, method=r.method,
                                valid_fraction=r.valid_fraction)
            sar.quicklook(d["hh_f"], r.water, d["search"], path(cfg, "processed", "quicklooks", "nisar", f"{rid}_{date}.png"),
                          f"{rid} {name} {date} NISAR HH - water {area:.1f} km2 (threshold {r.threshold_db:.1f} dB, {r.method})")
            rows.append({"reservoir_id": rid, "date": date, "sensor": "NISAR", "area_km2": round(area, 3),
                         "threshold_db": round(r.threshold_db, 2), "threshold_method": r.method,
                         "hv_threshold_db": None if r.cross_threshold_db is None else round(r.cross_threshold_db, 2),
                         "valid_fraction": round(r.valid_fraction, 3), "scene": str(d["scene"])})
            step(f"    {date}: {area:7.2f} km2, threshold {r.threshold_db:.1f} dB ({r.method}), "
                 f"valid {100 * r.valid_fraction:.0f} %")
    upsert_csv(path(cfg, "processed", "scene_areas_nisar.csv"), rows, ["reservoir_id", "date", "sensor"], SCENE_COLS)
    step("Done.")


if __name__ == "__main__":
    main()
