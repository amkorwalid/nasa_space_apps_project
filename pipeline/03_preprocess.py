"""Step 03 (Track B) - NISAR preprocessing: dB, speckle filter, validity mask, reference masks.

For every window written by step 02 (data/interim/nisar/<id>/window_<date>.npz):
  * HH/HV already in dB (10 log10 of the GCOV linear power)
  * 5x5 median speckle filter (invalid pixels excluded)
  * validity = finite backscatter and GCOV mask value not in detection.nisar.invalid_mask_values
    (no data / layover / shadow, see contracts/gcov_notes.md)
  * search zone = (JRC max extent U reservoir polygon) + 500 m, inside the analysis zone
  * terrain filter: pixels > 15 m above the reservoir's max water level (Copernicus DEM) excluded
The window already spans the analysis zone + 1 km of land (Contract 5 step 1).

Output: data/interim/nisar_pre/<id>/<YYYY-MM-DD>.npz

Usage:  python pipeline/03_preprocess.py --reservoir al_massira
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import geo, sar, s1  # noqa: E402
from utils.io import load_settings, path, read_json, resolve_reservoirs, step  # noqa: E402


def preprocess_window(cfg, feat, zone_geom, file: Path, out: Path) -> dict:
    d = np.load(file, allow_pickle=False)
    rid = feat["properties"]["reservoir_id"]
    grid = geo.grid_from_coords(d["x"], d["y"], int(d["epsg"]))
    tag = "nisar_" + hashlib.md5(str(grid.to_dict()).encode()).hexdigest()[:10]
    ref = s1.reference_layers(cfg, rid, geo.to_shape(feat["geometry"]), zone_geom, grid, tag)
    det = cfg["detection"]
    hh = d["hh_db"].astype("float32")
    hv = d["hv_db"].astype("float32") if d["hv_db"].shape == hh.shape else None
    valid = np.isfinite(hh)
    mask = d["mask"] if d["mask"].shape == hh.shape else None
    if mask is not None:
        valid &= ~np.isin(mask, det["nisar"]["invalid_mask_values"])
    if not (valid & ref["search"]).any():
        raise RuntimeError("no valid pixel in the search zone (scene does not cover the reservoir)")
    hh_f = sar.speckle_filter(hh, valid, det["median_filter_px"])
    hv_f = sar.speckle_filter(hv, valid & np.isfinite(hv), det["median_filter_px"]) if hv is not None else None
    np.savez_compressed(out, hh_f=hh_f, hv_f=hv_f if hv_f is not None else np.array([]), valid=valid,
                        search=ref["search"], reservoir=ref["reservoir"],
                        hand_ok=ref["hand_ok"] if ref["hand_ok"] is not None else np.array([]),
                        grid=np.array([str(grid.to_dict())]), date=str(d["date"]), scene=str(d["scene"]))
    return {"valid_pct": round(100 * float((valid & ref["search"]).sum() / max(ref["search"].sum(), 1)), 1),
            "shape": hh.shape}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reservoir", default="demo")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    zones = {f["properties"]["reservoir_id"]: geo.to_shape(f["geometry"])
             for f in read_json(path(cfg, "processed", "analysis_zones.geojson"))["features"]}
    for f in resolve_reservoirs(cfg, a.reservoir):
        rid = f["properties"]["reservoir_id"]
        files = sorted(path(cfg, "interim", "nisar", rid).glob("window_*.npz"))
        if not files:
            continue
        step(f"{rid} {f['properties']['name']}: {len(files)} window(s)")
        for file in files:
            date = file.stem.replace("window_", "")
            out = path(cfg, "interim", "nisar_pre", rid, f"{date}.npz")
            if out.is_file() and not a.force:
                continue
            try:
                info = preprocess_window(cfg, f, zones[rid], file, out)
                step(f"    {date}: {info['shape'][0]}x{info['shape'][1]} px, {info['valid_pct']} % valid in search zone")
            except Exception as e:
                step(f"    {date}: skipped ({e})")
    step("Done.")


if __name__ == "__main__":
    main()
