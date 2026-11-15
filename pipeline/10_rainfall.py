"""Step 10 (stretch, Track C) - CHIRPS rainfall anomaly per basin.

Downloads monthly CHIRPS v2.0 precipitation (0.05 deg) for the catalog's bounding box from the
IRI Data Library (no account), averages it over each basin outline and compares every month with
the same calendar month over the climatology years (config baseline.climatology_years).
This separates climate drivers (rain deficit) from human ones (irrigation, dam releases).

Output: data/reference/chirps_monthly.nc (cache)
        data/processed/rainfall_basins.csv
          basin, month, precip_mm, normal_mm, anomaly_pct, precip_12m_mm, normal_12m_mm, anomaly_12m_pct

Usage:  python pipeline/10_rainfall.py [--refresh]
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import geo  # noqa: E402
from utils.io import load_settings, path, read_json, rel, step  # noqa: E402

IRI = ("https://iridl.ldeo.columbia.edu/SOURCES/.UCSB/.CHIRPS/.v2p0/.monthly/.global/.precipitation/"
       "X/{w}/{e}/RANGEEDGES/Y/{s}/{n}/RANGEEDGES/T/({t0})/({t1})/RANGEEDGES/data.nc")
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def iri_month(m: str) -> str:
    return urllib.parse.quote(f"{MON[int(m[5:]) - 1]} {m[:4]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="download again (new months)")
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    import xarray as xr
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin
    from shapely.geometry import mapping

    basins = read_json(path(cfg, "processed", "basins.geojson"))
    shapes = {f["properties"]["name"]: geo.to_shape(f["geometry"]) for f in basins["features"]}
    w, s, e, n = geo.union(list(shapes.values())).bounds
    nc = path(cfg, "reference", "chirps_monthly.nc")
    if a.refresh or not nc.is_file():
        url = IRI.format(w=round(w - 0.1, 2), e=round(e + 0.1, 2), s=round(s - 0.1, 2), n=round(n + 0.1, 2),
                         t0=iri_month(cfg["baseline"]["start"]), t1=iri_month(cfg["baseline"]["end"]))
        step(f"Downloading CHIRPS monthly ({cfg['baseline']['start']}..{cfg['baseline']['end']}) from IRI...")
        tmp = nc.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(nc)
    ds = xr.open_dataset(nc, decode_times=False)
    pr = ds["precipitation"]
    t = pr["T"].values  # months since 1960-01-01
    months = [f"{1960 + int(v) // 12}-{int(v) % 12 + 1:02d}" for v in np.floor(t)]
    lon, lat = pr["X"].values, pr["Y"].values
    res = float(abs(lon[1] - lon[0]))
    flip = lat[0] < lat[-1]
    data = pr.transpose("T", "Y", "X").values
    if flip:
        data, lat = data[:, ::-1, :], lat[::-1]
    tr = from_origin(lon[0] - res / 2, lat[0] + res / 2, res, res)
    rows = []
    for name, g in shapes.items():
        m = geometry_mask([mapping(g)], out_shape=(len(lat), len(lon)), transform=tr, invert=True, all_touched=True)
        coslat = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, len(lon)))
        wts = np.where(m, coslat, 0)
        for i, mo in enumerate(months):
            v = data[i]
            ok = np.isfinite(v) & (wts > 0)
            rows.append({"basin": name, "month": mo,
                         "precip_mm": float((v[ok] * wts[ok]).sum() / wts[ok].sum()) if ok.any() else np.nan})
    df = pd.DataFrame(rows).sort_values(["basin", "month"])
    y0, y1 = cfg["baseline"]["climatology_years"]
    df["cal"] = df["month"].str[5:7]
    df["year"] = df["month"].str[:4].astype(int)
    df["precip_12m_mm"] = df.groupby("basin")["precip_mm"].transform(lambda x: x.rolling(12, min_periods=12).sum())
    base = df[(df["year"] >= y0) & (df["year"] <= y1)]
    norm = base.groupby(["basin", "cal"]).agg(normal_mm=("precip_mm", "mean"),
                                              normal_12m_mm=("precip_12m_mm", "mean")).reset_index()
    df = df.merge(norm, on=["basin", "cal"], how="left")
    with np.errstate(divide="ignore", invalid="ignore"):
        df["anomaly_pct"] = np.where(df["normal_mm"] > 1, (df["precip_mm"] / df["normal_mm"] - 1) * 100, np.nan)
        df["anomaly_12m_pct"] = (df["precip_12m_mm"] / df["normal_12m_mm"] - 1) * 100
    out = path(cfg, "processed", "rainfall_basins.csv")
    cols = ["basin", "month", "precip_mm", "normal_mm", "anomaly_pct", "precip_12m_mm", "normal_12m_mm", "anomaly_12m_pct"]
    df[cols].round(1).to_csv(out, index=False)
    last = df[df["month"] == df["month"].max()]
    step(f"{rel(out)}: {df['basin'].nunique()} basins x {df['month'].nunique()} months; latest 12-month anomaly: " +
         ", ".join(f"{r.basin} {r.anomaly_12m_pct:+.0f} %" for r in last.itertuples() if np.isfinite(r.anomaly_12m_pct)))


if __name__ == "__main__":
    main()
