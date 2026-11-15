"""Step 09 (Track C) - validation (README "Validation plan") -> docs/validation_report.md.

Tests
  1. SAR area vs official storage   Pearson r per reservoir (target r >= 0.85)   needs data/reference/official_fill.csv
  2. Water-mask accuracy            Sentinel-2 NDWI on clear days: IoU, precision, recall (target IoU >= 0.80)
  3. Sensor consistency             NISAR vs Sentinel-1 same month, mean abs difference (target <= 10 %)
  4. Temporal sanity                2025 lows -> 2026 recovery: direction of change per reservoir + national

Outputs: docs/validation_report.md, docs/images/*.png, data/processed/validation_metrics.json

Usage:  python pipeline/09_validate.py [--reservoir demo] [--s2-pairs 3] [--no-s2]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import geo, s1, sar, stac  # noqa: E402
from utils.io import ROOT, load_catalog, load_settings, path, read_json, rel, resolve_reservoirs, step, write_json  # noqa: E402

IMG = ROOT / "docs" / "images"


def official_test(cfg, st: pd.DataFrame, names: dict) -> dict:
    f = path(cfg, "reference", "official_fill.csv")
    if not f.is_file() or st["official_fill_pct"].notna().sum() == 0:
        return {"status": "not_run", "reason": f"no official fill rates in {rel(f)}"}
    rows = []
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for rid, g in st.dropna(subset=["official_fill_pct", "area_km2"]).groupby("reservoir_id"):
        if len(g) < 4:
            continue
        r = float(np.corrcoef(g["area_km2"], g["official_fill_pct"])[0, 1])
        rows.append({"reservoir_id": rid, "name": names.get(rid), "n": len(g), "r": round(r, 3), "r2": round(r * r, 3)})
        ax.scatter(g["official_fill_pct"], g["area_km2"], s=14, label=f"{names.get(rid, rid)} (r={r:.2f})")
    ax.set_xlabel("Official fill (%)")
    ax.set_ylabel("SAR water area (km²)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(IMG / "validation_official.png", dpi=130)
    plt.close(fig)
    target = cfg["validation"]["targets"]["r_official"]
    return {"status": "run", "rows": rows, "pass": all(r["r"] >= target for r in rows) if rows else None,
            "target": target}


def sensor_test(cfg, names: dict) -> dict:
    m = pd.read_csv(path(cfg, "processed", "monthly_area.csv"), dtype={"month": str})
    m = m[m["quality"] != "bad"]
    p = m.pivot_table(index=["reservoir_id", "month"], columns="sensor", values="area_km2")
    if not {"S1", "NISAR"} <= set(p.columns):
        return {"status": "not_run", "reason": "no month with both NISAR and Sentinel-1 areas"}
    p = p.dropna(subset=["S1", "NISAR"])
    p = p[p["S1"] > 0]
    if p.empty:
        return {"status": "not_run", "reason": "no overlapping months"}
    p["diff_pct"] = (p["NISAR"] - p["S1"]) / p["S1"] * 100
    rows = []
    for rid, g in p.groupby(level=0):
        rows.append({"reservoir_id": rid, "name": names.get(rid), "n": len(g),
                     "mean_diff_pct": round(float(g["diff_pct"].mean()), 1),
                     "mean_abs_diff_pct": round(float(g["diff_pct"].abs().mean()), 1)})
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(p["S1"], p["NISAR"], s=16)
    lim = float(max(p["S1"].max(), p["NISAR"].max())) * 1.05
    ax.plot([0, lim], [0, lim], "k--", lw=0.8)
    ax.set_xlabel("Sentinel-1 area (km²)")
    ax.set_ylabel("NISAR area (km²)")
    ax.set_title("Same month, two sensors")
    fig.tight_layout()
    fig.savefig(IMG / "validation_sensors.png", dpi=130)
    plt.close(fig)
    overall = float(p["diff_pct"].abs().mean())
    target = cfg["validation"]["targets"]["sensor_diff_pct"]
    return {"status": "run", "rows": rows, "overall_mean_abs_diff_pct": round(overall, 1),
            "pass": overall <= target, "target": target, "n_pairs": int(len(p))}


def temporal_test(cfg, st: pd.DataFrame, names: dict) -> dict:
    s = st[st["sensor"].notna() & st["area_km2"].notna()].copy()
    s["year"] = s["month"].str[:4]
    s["mm"] = s["month"].str[5:7]
    last = s["month"].max()
    common = sorted(set(s.loc[s["year"] == "2026", "mm"]) & set(s.loc[s["year"] == "2025", "mm"]))
    rows = []
    for rid, g in s.groupby("reservoir_id"):
        a25 = g[(g["year"] == "2025") & g["mm"].isin(common)]["area_km2"].mean()
        a26 = g[(g["year"] == "2026") & g["mm"].isin(common)]["area_km2"].mean()
        if np.isfinite(a25) and np.isfinite(a26) and a25 > 0:
            rows.append({"reservoir_id": rid, "name": names.get(rid), "area_2025": round(float(a25), 2),
                         "area_2026": round(float(a26), 2), "change_pct": round(float((a26 / a25 - 1) * 100), 1)})
    nat = s[s["status"] != "no_data"].groupby("month").agg(area=("area_km2", "sum"), normal=("normal_km2", "sum"))
    full = s.groupby("month")["area_km2"].sum()
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(pd.to_datetime(full.index), full.values, lw=1.6, label="Monitored water area")
    if len(nat):
        ax.plot(pd.to_datetime(nat.index), nat["normal"].values, "--", lw=1, label="Normal (same reservoirs)")
    ax.set_ylabel("km²")
    ax.legend(fontsize=8)
    ax.set_title("Total water area of monitored reservoirs")
    fig.tight_layout()
    fig.savefig(IMG / "validation_national.png", dpi=130)
    plt.close(fig)
    up = sum(r["change_pct"] > 0 for r in rows)
    return {"status": "run", "rows": rows, "months_compared": common, "n_up": up, "n": len(rows),
            "pass": bool(rows) and up >= len(rows) / 2, "latest": last}


def s2_test(cfg, feats, zones, pairs: int) -> dict:
    """S1 single-scene mask vs Sentinel-2 NDWI > 0 within the search zone, clear pixels only."""
    v = cfg["validation"]
    runs = read_json(path(cfg, "processed", "s1_runs.json"), default={})
    params = sar.DetectParams.from_cfg(cfg["detection"], "s1")
    vh_params = s1.vh_params_from_cfg(cfg["detection"])
    rows = []
    for f in feats:
        rid = f["properties"]["reservoir_id"]
        cache = read_json(path(cfg, "interim", "s1", rid, "items.json"), default={})
        if rid not in runs or not cache:
            continue
        orbit = runs[rid]["orbit"]
        zone = zones[rid]
        grid = geo.grid_for(zone, cfg["baseline"]["scale_m"], margin_m=cfg["detection"]["land_buffer_m"])
        ref = s1.reference_layers(cfg, rid, geo.to_shape(f["geometry"]), zone, grid,
                                  f"s1_{cfg['baseline']['scale_m']}m")
        s1_by_date: dict = {}
        for it in cache["items"]:
            if it["orbit"] == orbit and it["date"] >= "2023-01-01":
                s1_by_date.setdefault(it["date"], []).append(it)
        if not s1_by_date:
            continue
        dates = sorted(s1_by_date)
        s2 = stac.search("sentinel-2-l2a", geom=zone, datetime=f"{dates[0]}/{dates[-1]}",
                         query={"eo:cloud_cover": {"lt": v["s2_max_cloud"]}})
        cands = []
        for it in s2:
            d2 = it.properties["datetime"][:10]
            best = min(dates, key=lambda d: abs((dt.date.fromisoformat(d) - dt.date.fromisoformat(d2)).days))
            gap = abs((dt.date.fromisoformat(best) - dt.date.fromisoformat(d2)).days)
            if gap <= v["s2_max_days"]:
                cands.append((gap, -float(it.properties.get("eo:cloud_cover", 100)) * 0, d2, best, it))
        cands.sort(key=lambda c: (c[0], c[2]))
        seen, used = set(), 0
        for gap, _, d2, d1, it in sorted(cands, key=lambda c: c[2], reverse=True):
            if used >= pairs or d1 in seen:
                continue
            try:
                ndwi, clear = stac.s2_ndwi(it, grid)
                det, valid = s1.detect_scene(s1_by_date[d1], grid, ref, params, vh_params)
            except Exception as e:
                print(f"    {rid} {d2}: skipped ({str(e)[:100]})")
                continue
            area_ok = ref["search"] & clear & valid
            if area_ok.sum() < 0.8 * ref["search"].sum():
                continue
            opt = (ndwi > 0) & area_ok
            sarw = det.water & area_ok
            inter, union = float((opt & sarw).sum()), float((opt | sarw).sum())
            prec = inter / max(float(sarw.sum()), 1)
            rec = inter / max(float(opt.sum()), 1)
            rows.append({"reservoir_id": rid, "name": f["properties"]["name"], "s1_date": d1, "s2_date": d2,
                         "gap_days": gap, "iou": round(inter / union, 3) if union else None,
                         "precision": round(prec, 3), "recall": round(rec, 3),
                         "s1_km2": round(float(sarw.sum()) * grid.res ** 2 / 1e6, 2),
                         "s2_km2": round(float(opt.sum()) * grid.res ** 2 / 1e6, 2)})
            if used == 0:
                fig, axs = plt.subplots(1, 2, figsize=(10, 4))
                axs[0].imshow(np.where(area_ok, ndwi, np.nan), cmap="RdBu", vmin=-0.6, vmax=0.6)
                axs[0].set_title(f"Sentinel-2 NDWI {d2}")
                comp = np.zeros(opt.shape + (3,))
                comp[opt & sarw] = (0.1, 0.4, 0.9)
                comp[opt & ~sarw] = (0.95, 0.6, 0.1)
                comp[~opt & sarw] = (0.85, 0.2, 0.2)
                axs[1].imshow(comp)
                axs[1].set_title(f"S1 {d1} vs S2: blue agree, orange S2 only, red S1 only", fontsize=8)
                for x in axs:
                    x.axis("off")
                fig.suptitle(f"{f['properties']['name']} - IoU {rows[-1]['iou']}")
                fig.tight_layout()
                fig.savefig(IMG / f"validation_s2_{rid}.png", dpi=110)
                plt.close(fig)
            seen.add(d1)
            used += 1
            step(f"    {rid} S1 {d1} vs S2 {d2}: IoU {rows[-1]['iou']}, precision {rows[-1]['precision']}, "
                 f"recall {rows[-1]['recall']}")
    if not rows:
        return {"status": "not_run", "reason": "no clear Sentinel-2 scene within the date window"}
    target = v["targets"]["iou_s2"]
    mean_iou = float(np.mean([r["iou"] for r in rows if r["iou"] is not None]))
    return {"status": "run", "rows": rows, "mean_iou": round(mean_iou, 3), "pass": mean_iou >= target,
            "target": target}


def headlines(cfg, st: pd.DataFrame, names: dict) -> dict:
    """The three headline numbers for the pitch (README Track C, block 4)."""
    nat = read_json(ROOT / cfg["paths"]["web_data"] / "national.json", default=[])
    latest = st["month"].max()
    last = st[st["month"] == latest]
    out = {"month": latest, "status_counts": last["status"].value_counts().to_dict(),
           "n_reservoirs": int(last["reservoir_id"].nunique())}
    if nat:
        low = min(nat, key=lambda r: r["pct_of_normal"])
        now = nat[-1]
        out.update({"national_pct_now": now["pct_of_normal"], "national_area_now_km2": now["area_km2"],
                    "lowest_month": low["month"], "national_pct_lowest": low["pct_of_normal"],
                    "national_area_lowest_km2": low["area_km2"],
                    "change_since_lowest_pct": round((now["area_km2"] / low["area_km2"] - 1) * 100, 1)
                    if low["area_km2"] else None})
    return out


def md_table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "_none_\n"
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + " |\n" for r in rows)


def verdict(t: dict) -> str:
    if t.get("status") != "run":
        return f"Not run: {t.get('reason')}"
    return "PASS" if t.get("pass") else "BELOW TARGET"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reservoir", default="demo", help="reservoirs used for the Sentinel-2 test")
    ap.add_argument("--s2-pairs", type=int, default=3)
    ap.add_argument("--no-s2", action="store_true")
    ap.add_argument("--settings", default=None)
    a = ap.parse_args()
    cfg = load_settings(a.settings)
    IMG.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(cfg)
    names = {f["properties"]["reservoir_id"]: f["properties"]["name"] for f in catalog["features"]}
    st = pd.read_csv(path(cfg, "processed", "status.csv"), dtype={"month": str})
    zones = {f["properties"]["reservoir_id"]: geo.to_shape(f["geometry"])
             for f in read_json(path(cfg, "processed", "analysis_zones.geojson"))["features"]}

    step("1/4 official fill rates")
    t1 = official_test(cfg, st, names)
    step("2/4 Sentinel-2 NDWI comparison")
    t2 = {"status": "not_run", "reason": "--no-s2"} if a.no_s2 else \
        s2_test(cfg, resolve_reservoirs(cfg, a.reservoir), zones, a.s2_pairs)
    step("3/4 NISAR vs Sentinel-1")
    t3 = sensor_test(cfg, names)
    step("4/4 temporal sanity")
    t4 = temporal_test(cfg, st, names)
    head = headlines(cfg, st, names)
    metrics = {"generated": dt.date.today().isoformat(), "official": t1, "s2": t2, "sensors": t3, "temporal": t4,
               "headlines": head}
    write_json(path(cfg, "processed", "validation_metrics.json"), metrics, indent=1)

    tgt = cfg["validation"]["targets"]
    report = f"""# Validation report

Generated by `pipeline/09_validate.py` on {metrics['generated']} from the outputs in `data/processed/`.
Latest month in the data: **{t4.get('latest')}**. Re-run the step after each data drop.

## Summary

| Test | Reference | Metric | Target | Result |
|---|---|---|---|---|
| SAR area vs official storage | Al Maa Dialna fill rates | Pearson r | r >= {tgt['r_official']} | {verdict(t1)} |
| Water mask accuracy | Sentinel-2 NDWI (clear days) | IoU, precision, recall | IoU >= {tgt['iou_s2']} | {verdict(t2)}{f" (mean IoU {t2['mean_iou']})" if t2.get('status') == 'run' else ''} |
| Sensor consistency | NISAR vs Sentinel-1, same month | mean abs. area difference | <= {tgt['sensor_diff_pct']} % | {verdict(t3)}{f" ({t3['overall_mean_abs_diff_pct']} % over {t3['n_pairs']} months)" if t3.get('status') == 'run' else ''} |
| Temporal sanity | 2025 lows -> 2026 recovery | direction of change | rising | {verdict(t4)}{f" ({t4['n_up']}/{t4['n']} reservoirs up)" if t4.get('status') == 'run' else ''} |

## Headline numbers (for the pitch)

{f"- National water area of the {head['n_reservoirs']} monitored reservoirs in {head['month']}: **{head.get('national_area_now_km2')} km², {head.get('national_pct_now')} % of the 2015-2024 normal**." if head.get('national_pct_now') is not None else ''}
{f"- Lowest month since {cfg['web']['start_month']}: {head['lowest_month']} at {head['national_area_lowest_km2']} km² ({head['national_pct_lowest']} % of normal); water area has changed by **{head['change_since_lowest_pct']:+} %** since." if head.get('lowest_month') else ''}
- Status in {head['month']}: {', '.join(f"{v} {k.replace('_', ' ')}" for k, v in head['status_counts'].items())}.
{f"- Radar water maps agree with cloud-free Sentinel-2 at a mean IoU of **{t2['mean_iou']}** ({len(t2['rows'])} comparisons)." if t2.get('status') == 'run' else ''}

## 1. SAR area vs official storage

{md_table(t1.get('rows', []), ['reservoir_id', 'name', 'n', 'r', 'r2']) if t1.get('status') == 'run' else t1['reason'] + '. Add monthly values as `reservoir_id,month,official_fill_pct` (or `name,month,official_fill_pct`) and re-run steps 07-09.'}
{'![Official vs SAR](images/validation_official.png)' if t1.get('status') == 'run' else ''}

## 2. Water mask accuracy (Sentinel-2 NDWI)

Sentinel-1 single-scene water mask (same algorithm as the monthly product) against Sentinel-2 L2A
NDWI > 0 (McFeeters, B03/B08) on scenes with < {cfg['validation']['s2_max_cloud']} % cloud, at most
{cfg['validation']['s2_max_days']} days apart, inside the search zone and on clear pixels (SCL) only.

{md_table(t2.get('rows', []), ['reservoir_id', 'name', 's1_date', 's2_date', 'gap_days', 'iou', 'precision', 'recall', 's1_km2', 's2_km2']) if t2.get('status') == 'run' else t2['reason']}
{chr(10).join(f'![{r}](images/validation_s2_{r}.png)' for r in sorted({x['reservoir_id'] for x in t2.get('rows', [])}) if (IMG / f'validation_s2_{r}.png').is_file())}

## 3. Sensor consistency (NISAR vs Sentinel-1)

{md_table(t3.get('rows', []), ['reservoir_id', 'name', 'n', 'mean_diff_pct', 'mean_abs_diff_pct']) if t3.get('status') == 'run' else t3['reason']}
{'![Sensors](images/validation_sensors.png)' if t3.get('status') == 'run' else ''}

Step 07 removes the remaining bias by scaling NISAR onto the Sentinel-1 baseline
(`data/processed/harmonization.csv`).

## 4. Temporal sanity (2025 -> 2026)

Mean water area over the calendar months present in both years ({', '.join(t4.get('months_compared', [])) or 'none'}).

{md_table(t4.get('rows', []), ['reservoir_id', 'name', 'area_2025', 'area_2026', 'change_pct'])}

![National](images/validation_national.png)
"""
    (ROOT / "docs" / "validation_report.md").write_text(report, encoding="utf-8")
    step(f"Wrote docs/validation_report.md ({verdict(t1)} | {verdict(t2)} | {verdict(t3)} | {verdict(t4)})")


if __name__ == "__main__":
    main()
