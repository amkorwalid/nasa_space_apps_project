"""Step 08 (Track A) - export the static web dataset (Contract 4) into web/public/data/.

Reads the catalog, status.csv and the extent PNGs from steps 05 (NISAR) and 06 (Sentinel-1):

web/public/data/
  reservoirs.geojson         Contract 1 + latest status fields (+ monitored flag, metadata)
  basins.geojson             basin outlines + aggregated status of the latest month
  months.json                ["2023-01", ..., latest]
  timeseries/<id>.json       monthly series per monitored reservoir
  extents/<id>_<month>.png   water extent overlays (NISAR preferred, else Sentinel-1) + index.json
  national.json              monitored total area vs normal per month
  alerts.json                reservoirs whose status changed in the latest month
  rainfall.json              basin rainfall anomalies (if step 10 ran)
  downloads/                 status.csv, monthly_area.csv, reservoirs.csv (data export / public API)
  api/latest.json            latest national + per-reservoir summary (simple static API)

Usage:  python pipeline/08_export_web.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import geo  # noqa: E402
from utils.analytics import classify  # noqa: E402
from utils.io import ROOT, load_catalog, load_settings, month_range, path, read_json, rel, step, write_json  # noqa: E402

SERIES_FIELDS = ["month", "area_km2", "normal_km2", "p10_km2", "p90_km2", "pct_of_normal", "z_score", "status",
                 "sensor", "n_obs", "quality", "official_fill_pct", "mom_change_pct", "yoy_change_pct",
                 "area_s1_km2", "area_nisar_km2", "est_fill_pct"]
LATEST_FIELDS = ["month", "area_km2", "normal_km2", "pct_of_normal", "status", "mom_change_pct",
                 "yoy_change_pct", "official_fill_pct"]


def clean(v):
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    web = cfg["web"]
    out = ROOT / cfg["paths"]["web_data"]
    catalog = load_catalog(cfg)
    status_file = path(cfg, "processed", "status.csv")
    if not status_file.is_file():
        raise SystemExit("status.csv missing: run pipeline/07_status_anomaly.py first.")
    st = pd.read_csv(status_file, dtype={"reservoir_id": str, "month": str})
    latest = st["month"].max()
    months = month_range(web["start_month"], latest)
    st_web = st[st["month"].isin(months)]
    monitored = set(st_web["reservoir_id"].unique())
    step(f"Exporting {len(monitored)} monitored reservoirs, {months[0]}..{latest} ({len(months)} months)")

    # ---- fresh output folders ------------------------------------------------------
    for sub in ("timeseries", "extents", "downloads", "api"):
        shutil.rmtree(out / sub, ignore_errors=True)
        (out / sub).mkdir(parents=True, exist_ok=True)

    # ---- time series -----------------------------------------------------------------
    by_id = {rid: g.sort_values("month") for rid, g in st_web.groupby("reservoir_id")}
    for rid, g in by_id.items():
        series = [{k: clean(r.get(k)) for k in SERIES_FIELDS} for r in g.to_dict("records")]
        write_json(out / "timeseries" / f"{rid}.json", {"reservoir_id": rid, "series": series})

    # ---- extents: NISAR preferred, else S1 ----------------------------------------------
    idx_n = read_json(path(cfg, "processed", "extents_nisar", "index.json"), default={})
    idx_s = read_json(path(cfg, "processed", "extents_s1", "index.json"), default={})
    quality = {(r.reservoir_id, r.month, r.sensor): r.quality
               for r in pd.read_csv(path(cfg, "processed", "monthly_area.csv"), dtype=str).itertuples()}
    index = {}
    for rid in monitored:
        for m in months:
            key = f"{rid}_{m}"
            for sensor, idx, folder in (("NISAR", idx_n, "extents_nisar"), ("S1", idx_s, "extents_s1")):
                png = path(cfg, "processed", folder, f"{key}.png")
                if key in idx and png.is_file() and quality.get((rid, m, sensor)) not in (None, "bad"):
                    shutil.copyfile(png, out / "extents" / f"{key}.png")
                    index[key] = {"bounds": idx[key]["bounds"], "sensor": sensor}
                    break
    write_json(out / "extents" / "index.json", index)

    # ---- reservoirs ---------------------------------------------------------------------
    last = st_web.sort_values("month").groupby("reservoir_id").tail(1).set_index("reservoir_id")
    feats = []
    for f in catalog["features"]:
        p = dict(f["properties"])
        rid = p["reservoir_id"]
        p["monitored"] = rid in monitored
        if rid in last.index:
            r = last.loc[rid]
            p.update({k: clean(r.get(k)) for k in LATEST_FIELDS})
        for k in ("slug", "main_bas", "area_max_km2_source", "geometry_source"):
            p.pop(k, None)
        g = geo.web_geometry(geo.to_shape(f["geometry"]), web["simplify_deg"], web["coord_decimals"])
        feats.append({"type": "Feature", "properties": p, "geometry": g})
    meta = {"mock": False, "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "latest_month": latest, "first_month": months[0], "n_reservoirs": len(feats),
            "n_monitored": len(monitored),
            "sources": ["NISAR L2 GCOV (ASF DAAC)", "Sentinel-1 RTC (Microsoft Planetary Computer)",
                        "JRC Global Surface Water", "Copernicus DEM GLO-30", "HydroBASINS", "OpenStreetMap"]}
    write_json(out / "reservoirs.geojson", {"type": "FeatureCollection", "metadata": meta, "features": feats})

    # ---- national series + basins ------------------------------------------------------------
    usable = st_web[(st_web["status"] != "no_data") & st_web["normal_km2"].notna()]
    nat = []
    for m in months:
        u = usable[usable["month"] == m]
        if len(u):
            area, normal = float(u["area_km2"].sum()), float(u["normal_km2"].sum())
            nat.append({"month": m, "area_km2": round(area, 2), "normal_km2": round(normal, 2),
                        "pct_of_normal": round(area / normal * 100, 1), "n": int(len(u)),
                        "status": classify(area / normal * 100, cfg["status"])})
    write_json(out / "national.json", nat)

    basins = read_json(path(cfg, "processed", "basins.geojson"))
    basin_of = {f["properties"]["reservoir_id"]: f["properties"].get("basin") for f in catalog["features"]}
    rain = None
    rain_file = path(cfg, "processed", "rainfall_basins.csv")
    if rain_file.is_file():
        rain = pd.read_csv(rain_file, dtype={"month": str})
        rain = rain[rain["month"].isin(months)]
        cols = ["month", "precip_mm", "normal_mm", "anomaly_pct", "precip_12m_mm", "anomaly_12m_pct"]
        write_json(out / "rainfall.json", {b: [{k: clean(v) for k, v in r.items()}
                                               for r in g[cols].round(1).to_dict("records")]
                                           for b, g in rain.groupby("basin")})
    ul = usable[usable["month"] == latest].copy()
    ul["basin"] = ul["reservoir_id"].map(basin_of)
    for bf in basins["features"]:
        p = bf["properties"]
        u = ul[ul["basin"] == p["name"]]
        area, normal = float(u["area_km2"].sum()), float(u["normal_km2"].sum())
        pct = area / normal * 100 if normal else None
        p.update({"month": latest, "n_monitored": int(len(u)), "area_km2": round(area, 2) if len(u) else None,
                  "normal_km2": round(normal, 2) if len(u) else None,
                  "pct_of_normal": round(pct, 1) if pct else None, "status": classify(pct, cfg["status"])})
        if rain is not None:
            r = rain[(rain["basin"] == p["name"]) & (rain["month"] == latest)]
            p["rain_anomaly_pct"] = clean(float(r["anomaly_pct"].iloc[0])) if len(r) else None
    write_json(out / "basins.geojson", basins)
    write_json(out / "months.json", months, indent=1)

    # ---- alerts (status changes in the latest month) ------------------------------------------------
    prev_m = months[-2] if len(months) > 1 else None
    alerts = []
    if prev_m:
        a_ = st_web[st_web["month"] == prev_m].set_index("reservoir_id")["status"]
        b_ = st_web[st_web["month"] == latest].set_index("reservoir_id")["status"]
        names = {f["properties"]["reservoir_id"]: f["properties"]["name"] for f in catalog["features"]}
        for rid in sorted(set(a_.index) & set(b_.index)):
            if a_[rid] != b_[rid] and "no_data" not in (a_[rid], b_[rid]):
                alerts.append({"reservoir_id": rid, "name": names.get(rid), "from": a_[rid], "to": b_[rid],
                               "month": latest})
    write_json(out / "alerts.json", alerts, indent=1)

    # ---- downloads + static API ------------------------------------------------------------------
    st.to_csv(out / "downloads" / "status.csv", index=False)
    shutil.copyfile(path(cfg, "processed", "monthly_area.csv"), out / "downloads" / "monthly_area.csv")
    pd.DataFrame([{k: v for k, v in f["properties"].items() if not isinstance(v, (dict, list))} for f in feats]) \
        .to_csv(out / "downloads" / "reservoirs.csv", index=False)
    write_json(out / "api" / "latest.json", {
        "generated": meta["generated"], "month": latest,
        "national": nat[-1] if nat else None,
        "reservoirs": [{"reservoir_id": rid, "name": next(f["properties"]["name"] for f in feats
                                                          if f["properties"]["reservoir_id"] == rid),
                        **{k: clean(last.loc[rid].get(k)) for k in LATEST_FIELDS}} for rid in sorted(last.index)],
    }, indent=1)
    step(f"Wrote {len(by_id)} time series, {len(index)} extent overlays, {len(alerts)} alert(s) -> {rel(out)}")


if __name__ == "__main__":
    main()
