"""Step 02 (Track A/B) - NISAR GCOV scene inventory + windowed download.

For each selected reservoir: search NISAR L2 GCOV scenes over its analysis zone (asf_search),
write the scene inventory, pick the track/frame that covers the zone best, then read only the
zone window (+1 km land) of HH/HV/mask from each remote HDF5 file (earthaccess, no full download).

Outputs: data/processed/scene_inventory.csv
         data/interim/nisar/<reservoir_id>/window_<YYYY-MM-DD>.npz
         contracts/gcov_notes.md   (dataset paths, pixel size, CRS, mask values seen)

Usage:
    python pipeline/02_search_download.py --reservoir al_massira --start 2026-06-01 --end 2026-11-01
    python pipeline/02_search_download.py --reservoir priority --inventory-only
    python pipeline/02_search_download.py --reservoir demo --max-scenes 6
Needs EARTHDATA_USER / EARTHDATA_PASS (or EARTHDATA_TOKEN) in .env for the window reads.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import geo, nisar  # noqa: E402
from utils.io import ROOT, load_env, load_settings, path, read_json, rel, resolve_reservoirs, step, upsert_csv, write_json  # noqa: E402


def zones_by_id(cfg) -> dict:
    z = read_json(path(cfg, "processed", "analysis_zones.geojson"))
    return {f["properties"]["reservoir_id"]: geo.to_shape(f["geometry"]) for f in z["features"]}


def write_gcov_notes(meta: dict, scene: str) -> None:
    notes = ROOT / "contracts" / "gcov_notes.md"
    attrs = "\n".join(f"| `{k}` | {str(v)[:300]} |" for k, v in meta.get("mask_attrs", {}).items()) or "| (none) | |"
    notes.write_text(f"""# NISAR L2 GCOV notes (Track B)

Written automatically by `pipeline/02_search_download.py` from a real file
(`{scene}`), so the paths below are verified, not guessed.

| Item | Value |
|---|---|
| Grid group | `{nisar.GRID}` |
| Co-pol backscatter | `{nisar.GRID}/HHHH` (linear power, gamma0) |
| Cross-pol backscatter | `{nisar.GRID}/HVHV` |
| Coordinates | `{nisar.GRID}/xCoordinates`, `yCoordinates` (pixel centres, metres) |
| Projection | `{nisar.GRID}/projection` -> EPSG:{meta.get('epsg')} |
| Pixel spacing | {meta.get('pixel_m')} m |
| Mask layer | `{nisar.GRID}/mask` |
| Mask values seen in the window | {meta.get('mask_values')} |

## Mask layer attributes

| Attribute | Value |
|---|---|
{attrs}

Water detection treats mask values listed in `config/settings.yaml`
(`detection.nisar.invalid_mask_values`) as invalid (no data / layover / shadow).
""", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reservoir", default="demo", help="ID, name slug, comma list, 'demo', 'priority' or 'all'")
    ap.add_argument("--start", default=None, help="ISO date (default: 2025-10-01, start of NISAR science data)")
    ap.add_argument("--end", default=None, help="ISO date (default: today)")
    ap.add_argument("--inventory-only", action="store_true")
    ap.add_argument("--max-scenes", type=int, default=40, help="most recent scenes read per reservoir")
    ap.add_argument("--per-month", type=int, default=2, help="scenes kept per month (majority vote needs >= 2)")
    ap.add_argument("--track", type=int, default=None)
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    load_env()
    start = a.start or "2025-10-01"
    end = a.end or dt.date.today().isoformat()

    feats = resolve_reservoirs(cfg, a.reservoir)
    zones = zones_by_id(cfg)
    inv_file = path(cfg, "processed", "scene_inventory.csv")
    margin = cfg["detection"]["land_buffer_m"]
    plan = []
    for f in feats:
        rid, name = f["properties"]["reservoir_id"], f["properties"]["name"]
        zone = zones[rid]
        try:
            urls, fps = nisar.search(zone, start, end)
        except Exception as e:
            step(f"{rid} {name}: search failed ({e})")
            continue
        rows = nisar.inventory_rows(urls, rid, zone, fps)
        upsert_csv(inv_file, rows, ["scene_id", "reservoir_id"], nisar.INVENTORY_COLUMNS)
        pick = nisar.choose_track(rows, a.track)
        on_track = [r for r in rows if pick and (r["track"], r["frame"]) == pick]
        per_month: dict = {}
        for r in on_track:  # newest first; keep up to N per month so every month gets a composite
            per_month.setdefault(r["date"][:7], [])
            if len(per_month[r["date"][:7]]) < a.per_month:
                per_month[r["date"][:7]].append(r)
        sel = sorted([r for v in per_month.values() for r in v], key=lambda r: r["date"], reverse=True)[:a.max_scenes]
        step(f"{rid} {name}: {len(rows)} GCOV scene(s) {start}..{end}; "
             f"track/frame {pick} -> {len(sel)} to read")
        plan.append((rid, zone, sel))
    step(f"Inventory: {rel(inv_file)}")
    if a.inventory_only:
        return

    todo = [(rid, zone, r) for rid, zone, sel in plan for r in sel
            if not path(cfg, "interim", "nisar", rid, f"window_{r['date']}.npz").is_file()]
    if not todo:
        step("Nothing new to read.")
        return
    fs = nisar.login()
    notes_written = (ROOT / "contracts" / "gcov_notes.md").is_file()
    for i, (rid, zone, r) in enumerate(todo, 1):
        out = path(cfg, "interim", "nisar", rid, f"window_{r['date']}.npz")
        step(f"[{i}/{len(todo)}] {rid} {r['date']} track {r['track']} ({r['direction']})")
        try:
            meta = nisar.read_window(fs, r["url"], zone, margin, out, r["date"])
        except Exception as e:
            step(f"      failed: {e}")
            continue
        meta.update({"scene": r["scene_id"], "track": r["track"], "frame": r["frame"],
                     "direction": r["direction"], "coverage_pct": r["coverage_pct"]})
        write_json(out.with_suffix(".json"), meta, indent=1)
        if not notes_written:
            write_gcov_notes(meta, r["scene_id"])
            notes_written = True
    step("Done.")


if __name__ == "__main__":
    main()
