"""Step 07 (Track C) - long-term normal, anomaly, status class and trends (Contract 3).

1. Merge NISAR (monthly_area_nisar.csv) and Sentinel-1 (monthly_area_s1.csv) rows -> monthly_area.csv
2. Harmonize sensors: NISAR areas scaled by k = median(S1 / NISAR) over overlapping months
3. Climatology per reservoir and calendar month from Sentinel-1 over the baseline years:
   mean (normal), std, p10, p90
4. percent_of_normal = area / normal x 100, z = (area - normal) / std
5. Status: above_normal > 110 % >= normal >= 90 % > watch >= 75 % > drought >= 50 % > severe;
   no_data when the month is bad, the reservoir is low confidence, or < 3 baseline years
6. Change vs previous month and vs the same month last year
7. Official fill rates (data/reference/official_fill.csv, if present) joined; area-storage
   curves V = a A^b fitted where >= 6 official values exist -> est_fill_pct (stretch goal)

Outputs: data/processed/monthly_area.csv, status.csv, climatology.csv, harmonization.csv,
         area_storage_fits.csv

Usage:  python pipeline/07_status_anomaly.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import analytics  # noqa: E402
from utils.io import ROOT, load_catalog, load_settings, path, rel, step  # noqa: E402


def load_official(cfg, catalog) -> pd.DataFrame | None:
    """official_fill.csv columns: reservoir_id (or name), month (YYYY-MM), official_fill_pct."""
    f = path(cfg, "reference", "official_fill.csv")
    if not f.is_file():
        return None
    df = pd.read_csv(f, dtype=str)
    if "reservoir_id" not in df or df["reservoir_id"].isna().all():
        from utils.io import slugify

        by_slug = {ft["properties"]["slug"]: ft["properties"]["reservoir_id"] for ft in catalog["features"]}
        df["reservoir_id"] = df["name"].map(lambda n: by_slug.get(slugify(n)))
    df["official_fill_pct"] = pd.to_numeric(df["official_fill_pct"], errors="coerce")
    df = df.dropna(subset=["reservoir_id", "month", "official_fill_pct"])
    return df[["reservoir_id", "month", "official_fill_pct"]] if len(df) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    catalog = load_catalog(cfg)
    base = cfg["baseline"]

    files = [path(cfg, "processed", "monthly_area_s1.csv"), path(cfg, "processed", "monthly_area_nisar.csv")]
    monthly = analytics.read_monthly(files)
    monthly = monthly[monthly["month"] <= base["end"]]  # complete months only
    before = (monthly["quality"] == "bad").sum()
    monthly = analytics.flag_implausible_drops(monthly)
    step(f"Temporal QA: {(monthly['quality'] == 'bad').sum() - before} implausible one-month drops flagged bad")
    if monthly.empty:
        raise SystemExit("No monthly areas yet: run step 06 (Sentinel-1) and/or steps 02-05 (NISAR).")
    merged_cols = ["reservoir_id", "month", "sensor", "area_km2", "n_obs", "quality"]
    monthly.sort_values(["reservoir_id", "month", "sensor"])[merged_cols].to_csv(
        path(cfg, "processed", "monthly_area.csv"), index=False)
    step(f"{len(monthly)} monthly rows ({(monthly.sensor == 'S1').sum()} S1, {(monthly.sensor == 'NISAR').sum()} NISAR)")

    monthly, harm = analytics.harmonize(monthly)
    harm.to_csv(path(cfg, "processed", "harmonization.csv"), index=False)
    if len(harm):
        step("NISAR -> S1 harmonization factors: " +
             ", ".join(f"{r.reservoir_id} x{r.factor:.3f} ({r.method}, n={r.n_overlap})" for r in harm.itertuples()))

    y0, y1 = base["climatology_years"]
    clim = analytics.climatology(monthly[monthly["sensor"] == "S1"], (int(y0), int(y1)))
    clim.round(3).to_csv(path(cfg, "processed", "climatology.csv"), index=False)

    low = {f["properties"]["reservoir_id"] for f in catalog["features"] if f["properties"]["confidence"] == "low"}
    # New reservoirs (filled during or after the baseline years, e.g. M'Dez 2025) have a near-zero
    # "normal", so % of normal is meaningless: status no_data, area still reported.
    area_max = {f["properties"]["reservoir_id"]: f["properties"]["polygon_area_km2"] for f in catalog["features"]}
    base_mean = clim.groupby("reservoir_id")["normal_km2"].mean()
    new_res = {rid for rid, v in base_mean.items() if area_max.get(rid) and v < 0.10 * area_max[rid]}
    if new_res:
        step("No representative 2015-2024 baseline (new reservoir), status no_data: " + ", ".join(sorted(new_res)))
    low |= new_res
    official = load_official(cfg, catalog)
    status = analytics.build_status(monthly, clim, cfg["status"], int(base["min_years"]), low, official)

    caps = {f["properties"]["reservoir_id"]: f["properties"].get("capacity_mcm") for f in catalog["features"]}
    status, fits = analytics.apply_area_storage(status, caps)
    pd.DataFrame(fits, columns=["reservoir_id", "a", "b", "r2", "n"]).to_csv(
        path(cfg, "processed", "area_storage_fits.csv"), index=False)
    out = path(cfg, "processed", "status.csv")
    status.to_csv(out, index=False)

    latest = status.groupby("reservoir_id")["month"].max()
    last = status.merge(latest.rename("m"), left_on="reservoir_id", right_index=True)
    last = last[last["month"] == last["m"]]
    step(f"status.csv: {len(status)} rows, {status['reservoir_id'].nunique()} reservoirs -> {rel(out)}")
    step("Latest status: " + ", ".join(f"{k}={v}" for k, v in last["status"].value_counts().items()))
    if official is None:
        step(f"No official fill rates yet ({rel(ROOT / cfg['paths']['reference'] / 'official_fill.csv')}); "
             "official_fill_pct left empty.")


if __name__ == "__main__":
    main()
