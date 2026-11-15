"""Baseline, anomaly and status analytics (methodology section 5-6), pure pandas."""
from __future__ import annotations

import numpy as np
import pandas as pd

STATUS_CODES = ["above_normal", "normal", "watch", "drought", "severe", "no_data"]
STATUS_COLUMNS = ["reservoir_id", "month", "area_km2", "normal_km2", "pct_of_normal", "z_score", "status",
                  "mom_change_pct", "yoy_change_pct", "official_fill_pct",
                  # extensions (appended, Contract 3 columns above are unchanged)
                  "p10_km2", "p90_km2", "std_km2", "n_years", "sensor", "n_obs", "quality",
                  "area_s1_km2", "area_nisar_km2", "est_fill_pct"]


def classify(pct: float | None, th: dict) -> str:
    if pct is None or not np.isfinite(pct):
        return "no_data"
    if pct > th["above_normal"]:
        return "above_normal"
    if pct >= th["normal"]:
        return "normal"
    if pct >= th["watch"]:
        return "watch"
    if pct >= th["drought"]:
        return "drought"
    return "severe"


def read_monthly(files) -> pd.DataFrame:
    frames = []
    for f in files:
        try:
            frames.append(pd.read_csv(f, dtype={"reservoir_id": str, "month": str}))
        except FileNotFoundError:
            continue
    if not frames:
        return pd.DataFrame(columns=["reservoir_id", "month", "sensor", "area_km2", "n_obs", "quality"])
    df = pd.concat(frames, ignore_index=True)
    df["area_km2"] = pd.to_numeric(df["area_km2"], errors="coerce")
    df["n_obs"] = pd.to_numeric(df["n_obs"], errors="coerce").fillna(0).astype(int)
    return df.drop_duplicates(["reservoir_id", "month", "sensor"], keep="last")


def harmonize(df: pd.DataFrame, min_overlap: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scale NISAR areas onto the Sentinel-1 baseline: k = median(S1 / NISAR) over months where
    both are usable (per reservoir; pooled over all reservoirs when a reservoir has < min_overlap).
    Returns (df with area_adj_km2, table of factors)."""
    df = df.copy()
    df["area_adj_km2"] = df["area_km2"]
    usable = df[df["quality"] != "bad"]
    piv = usable.pivot_table(index=["reservoir_id", "month"], columns="sensor", values="area_km2")
    rows = []
    if {"S1", "NISAR"} <= set(piv.columns):
        both = piv.dropna(subset=["S1", "NISAR"])
        both = both[both["NISAR"] > 0]
        pooled = float(np.median(both["S1"] / both["NISAR"])) if len(both) else 1.0
        for rid in sorted(df.loc[df["sensor"] == "NISAR", "reservoir_id"].unique()):
            sub = both.loc[both.index.get_level_values(0) == rid] if len(both) else both
            n = len(sub)
            k = float(np.median(sub["S1"] / sub["NISAR"])) if n >= min_overlap else pooled if len(both) else 1.0
            diff = float(np.mean(np.abs(sub["NISAR"] - sub["S1"]) / sub["S1"]) * 100) if n else np.nan
            rows.append({"reservoir_id": rid, "n_overlap": n, "factor": round(k, 4),
                         "method": "reservoir" if n >= min_overlap else ("pooled" if len(both) else "none"),
                         "mean_abs_diff_pct": round(diff, 2) if np.isfinite(diff) else None})
            sel = (df["sensor"] == "NISAR") & (df["reservoir_id"] == rid)
            df.loc[sel, "area_adj_km2"] = df.loc[sel, "area_km2"] * k
    return df, pd.DataFrame(rows, columns=["reservoir_id", "n_overlap", "factor", "method", "mean_abs_diff_pct"])


def climatology(s1: pd.DataFrame, years: tuple[int, int]) -> pd.DataFrame:
    """Per reservoir and calendar month: mean, std, p10, p90, n_years over the baseline years
    (Sentinel-1 only, quality good/partial)."""
    d = s1[(s1["quality"] != "bad") & s1["area_km2"].notna()].copy()
    d["year"] = d["month"].str[:4].astype(int)
    d["cal"] = d["month"].str[5:7].astype(int)
    d = d[(d["year"] >= years[0]) & (d["year"] <= years[1])]
    g = d.groupby(["reservoir_id", "cal"])["area_km2"]
    clim = pd.DataFrame({
        "normal_km2": g.mean(), "std_km2": g.std(ddof=1),
        "p10_km2": g.quantile(0.10), "p90_km2": g.quantile(0.90), "n_years": g.count(),
    }).reset_index()
    return clim


def build_status(monthly: pd.DataFrame, clim: pd.DataFrame, thresholds: dict, min_years: int,
                 low_conf_ids: set | None = None, official: pd.DataFrame | None = None) -> pd.DataFrame:
    """Merged series (NISAR preferred when usable, else S1) + anomaly + status + trends."""
    low_conf_ids = low_conf_ids or set()
    m = monthly.copy()
    m["rank"] = m["sensor"].map({"NISAR": 0, "S1": 1}).fillna(2)
    m.loc[m["quality"] == "bad", "rank"] += 10
    s1_area = m[m["sensor"] == "S1"].set_index(["reservoir_id", "month"])["area_km2"]
    ni_area = m[m["sensor"] == "NISAR"].set_index(["reservoir_id", "month"])["area_km2"]
    best = m.sort_values("rank").drop_duplicates(["reservoir_id", "month"], keep="first")
    best = best.rename(columns={"area_adj_km2": "area_sel"})
    if "area_sel" not in best:
        best["area_sel"] = best["area_km2"]
    best["cal"] = best["month"].str[5:7].astype(int)
    out = best.merge(clim, on=["reservoir_id", "cal"], how="left")
    out["area"] = out["area_sel"]
    with np.errstate(divide="ignore", invalid="ignore"):
        out["pct_of_normal"] = out["area"] / out["normal_km2"] * 100
        out["z_score"] = (out["area"] - out["normal_km2"]) / out["std_km2"]
    insufficient = (out["n_years"].fillna(0) < min_years) | (out["quality"] == "bad") | \
        out["reservoir_id"].isin(low_conf_ids)
    out["status"] = [("no_data" if bad else classify(p, thresholds))
                     for p, bad in zip(out["pct_of_normal"], insufficient)]

    out = out.sort_values(["reservoir_id", "month"])
    key = out.set_index(["reservoir_id", "month"])["area"]

    def change(months_back: int):
        vals = []
        for rid, mo, a in zip(out["reservoir_id"], out["month"], out["area"]):
            y, mm = int(mo[:4]), int(mo[5:])
            k = y * 12 + mm - 1 - months_back
            prev = key.get((rid, f"{k // 12}-{k % 12 + 1:02d}"))
            vals.append((a / prev - 1) * 100 if prev and prev > 0 and np.isfinite(a) else np.nan)
        return vals

    out["mom_change_pct"] = change(1)
    out["yoy_change_pct"] = change(12)
    out["area_s1_km2"] = [s1_area.get((r, mo)) for r, mo in zip(out["reservoir_id"], out["month"])]
    out["area_nisar_km2"] = [ni_area.get((r, mo)) for r, mo in zip(out["reservoir_id"], out["month"])]

    if official is not None and len(official):
        off = official.set_index(["reservoir_id", "month"])["official_fill_pct"]
        out["official_fill_pct"] = [off.get((r, mo)) for r, mo in zip(out["reservoir_id"], out["month"])]
    else:
        out["official_fill_pct"] = np.nan
    out["est_fill_pct"] = np.nan
    out = out.rename(columns={"area": "area_km2_final"})
    out["area_km2"] = out["area_km2_final"]
    res = out[[c for c in STATUS_COLUMNS if c in out.columns]].copy()
    for c in ["area_km2", "normal_km2", "p10_km2", "p90_km2", "std_km2", "area_s1_km2", "area_nisar_km2"]:
        res[c] = pd.to_numeric(res[c], errors="coerce").round(3)
    for c in ["pct_of_normal", "mom_change_pct", "yoy_change_pct", "official_fill_pct"]:
        res[c] = pd.to_numeric(res[c], errors="coerce").round(1)
    res["z_score"] = pd.to_numeric(res["z_score"], errors="coerce").round(2)
    res["n_years"] = res["n_years"].fillna(0).astype(int)
    return res.reindex(columns=STATUS_COLUMNS)


def fit_area_storage(area: np.ndarray, volume: np.ndarray):
    """Power law V = a * A^b by least squares in log space. Returns (a, b, r2) or None."""
    a_ = np.asarray(area, float)
    v_ = np.asarray(volume, float)
    ok = (a_ > 0) & (v_ > 0) & np.isfinite(a_) & np.isfinite(v_)
    if ok.sum() < 6:
        return None
    x, y = np.log(a_[ok]), np.log(v_[ok])
    b, loga = np.polyfit(x, y, 1)
    pred = loga + b * x
    r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
    return float(np.exp(loga)), float(b), float(r2)


def apply_area_storage(status: pd.DataFrame, catalog_caps: dict) -> tuple[pd.DataFrame, list[dict]]:
    """For reservoirs with >= 6 official fill values: fit V = a A^b on (SAR area, official volume)
    and estimate % full for every month (est_fill_pct)."""
    fits = []
    st = status.copy()
    for rid, g in st.groupby("reservoir_id"):
        cap = catalog_caps.get(rid)
        if not cap:
            continue
        g2 = g.dropna(subset=["official_fill_pct", "area_km2"])
        fit = fit_area_storage(g2["area_km2"].values, g2["official_fill_pct"].values / 100 * cap)
        if not fit:
            continue
        a, b, r2 = fit
        est = np.clip(a * np.power(g["area_km2"].clip(lower=0), b) / cap * 100, 0, 100)
        st.loc[g.index, "est_fill_pct"] = est.round(1)
        fits.append({"reservoir_id": rid, "a": a, "b": b, "r2": r2, "n": len(g2)})
    return st, fits
