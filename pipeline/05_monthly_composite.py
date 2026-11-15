"""Step 05 (Track B) - NISAR monthly composite (Contract 5 step 7).

Majority vote per pixel across the month's scenes (water if detected in >= 50 % of the scenes
where the pixel is valid). Scenes on a different grid are resampled onto the first scene's grid.

Outputs: data/processed/monthly_area_nisar.csv                 (Contract 2, sensor = NISAR)
         data/processed/extents_nisar/<id>_<YYYY-MM>.png + index.json

Usage:  python pipeline/05_monthly_composite.py --reservoir al_massira
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import geo, sar  # noqa: E402
from utils.io import load_settings, path, read_json, resolve_reservoirs, step, upsert_csv, write_json  # noqa: E402

COLS = ["reservoir_id", "month", "sensor", "area_km2", "n_obs", "quality"]


def to_grid(arr: np.ndarray, src: geo.Grid, dst: geo.Grid) -> np.ndarray:
    if src.to_dict() == dst.to_dict():
        return arr
    from rasterio.warp import Resampling, reproject

    out = np.zeros((dst.height, dst.width), np.uint8)
    reproject(arr.astype(np.uint8), out, src_transform=src.transform, src_crs=src.crs.to_wkt(),
              dst_transform=dst.transform, dst_crs=dst.crs.to_wkt(), resampling=Resampling.nearest)
    return out.astype(bool)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reservoir", default="demo")
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    maj = cfg["detection"]["majority"]
    idx_file = path(cfg, "processed", "extents_nisar", "index.json")
    index = read_json(idx_file, default={})
    rows = []
    for f in resolve_reservoirs(cfg, a.reservoir):
        rid = f["properties"]["reservoir_id"]
        files = sorted(path(cfg, "interim", "nisar_masks", rid).glob("*.npz"))
        by_month: dict = {}
        for file in files:
            by_month.setdefault(file.stem[:7], []).append(file)
        for month, fs in sorted(by_month.items()):
            loaded = [np.load(x, allow_pickle=False) for x in fs]
            grids = [geo.Grid.from_dict(ast.literal_eval(str(d["grid"][0]))) for d in loaded]
            g0 = grids[0]
            masks = [to_grid(d["water"], g, g0) for d, g in zip(loaded, grids)]
            valids = [to_grid(d["valid"], g, g0) for d, g in zip(loaded, grids)]
            comp, _ = sar.majority_composite(masks, valids, maj)
            area = float(comp.sum() * g0.res * abs(g0.transform.e) / 1e6)
            vf = float(np.mean([float(d["valid_fraction"]) for d in loaded]))
            q = sar.month_quality(vf, len(loaded), any(str(d["method"]) == "fallback" for d in loaded))
            key = f"{rid}_{month}"
            index[key] = {"bounds": sar.mask_to_png(comp, g0, path(cfg, "processed", "extents_nisar", f"{key}.png")),
                          "sensor": "NISAR"}
            rows.append({"reservoir_id": rid, "month": month, "sensor": "NISAR", "area_km2": round(area, 3),
                         "n_obs": len(loaded), "quality": q})
            step(f"{rid} {month}: {area:7.2f} km2 from {len(loaded)} scene(s), quality {q}")
    write_json(idx_file, index, indent=1)
    upsert_csv(path(cfg, "processed", "monthly_area_nisar.csv"), rows, ["reservoir_id", "month", "sensor"], COLS)
    step("Done.")


if __name__ == "__main__":
    main()
