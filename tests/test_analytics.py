"""Baseline, anomaly, status classes, harmonization and area-storage fits."""
import numpy as np
import pandas as pd
import pytest

from pipeline.utils import analytics
from pipeline.utils.io import month_range, shift_month

TH = {"above_normal": 110, "normal": 90, "watch": 75, "drought": 50}


@pytest.mark.parametrize("pct,expected", [(150, "above_normal"), (110.01, "above_normal"), (110, "normal"),
                                          (90, "normal"), (89.9, "watch"), (75, "watch"), (74.9, "drought"),
                                          (50, "drought"), (49.9, "severe"), (None, "no_data"),
                                          (float("nan"), "no_data")])
def test_classify_matches_readme_thresholds(pct, expected):
    assert analytics.classify(pct, TH) == expected


def synthetic_monthly(rid="MAR_0001", years=range(2015, 2027), seasonal=20, mean=50, last_factor=0.6):
    rows = []
    for y in years:
        for m in range(1, 13):
            if y == 2026 and m > 10:
                continue
            a = mean + seasonal * np.sin((m - 3) / 12 * 2 * np.pi)
            if y >= 2025:
                a *= last_factor
            rows.append({"reservoir_id": rid, "month": f"{y}-{m:02d}", "sensor": "S1", "area_km2": round(a, 3),
                         "n_obs": 3, "quality": "good"})
    return pd.DataFrame(rows)


def test_climatology_and_status_pipeline():
    m = synthetic_monthly()
    m, harm = analytics.harmonize(m)
    clim = analytics.climatology(m[m.sensor == "S1"], (2015, 2024))
    assert set(clim.columns) >= {"normal_km2", "std_km2", "p10_km2", "p90_km2", "n_years"}
    assert (clim["n_years"] == 10).all()
    st = analytics.build_status(m, clim, TH, 3)
    last = st[st.month == "2026-10"].iloc[0]
    assert last["pct_of_normal"] == pytest.approx(60, abs=0.5)
    assert last["status"] == "drought"
    jan25 = st[st.month == "2025-01"].iloc[0]
    assert jan25["yoy_change_pct"] == pytest.approx(-40, abs=0.5)
    assert list(st.columns[:10]) == ["reservoir_id", "month", "area_km2", "normal_km2", "pct_of_normal", "z_score",
                                     "status", "mom_change_pct", "yoy_change_pct", "official_fill_pct"]


def test_low_confidence_and_bad_quality_are_no_data():
    m = synthetic_monthly()
    m.loc[m.month == "2026-10", "quality"] = "bad"
    m, _ = analytics.harmonize(m)
    clim = analytics.climatology(m, (2015, 2024))
    st = analytics.build_status(m, clim, TH, 3)
    assert st.loc[st.month == "2026-10", "status"].iloc[0] == "no_data"
    st2 = analytics.build_status(m, clim, TH, 3, low_conf_ids={"MAR_0001"})
    assert (st2["status"] == "no_data").all()


def test_harmonize_scales_nisar_and_prefers_it():
    s1 = synthetic_monthly(years=range(2025, 2027), last_factor=1)
    ni = s1[s1.month >= "2026-01"].copy()
    ni["sensor"] = "NISAR"
    ni["area_km2"] = ni["area_km2"] / 1.1   # NISAR 10 % smaller
    df, harm = analytics.harmonize(pd.concat([s1, ni], ignore_index=True))
    assert harm.iloc[0]["factor"] == pytest.approx(1.1, rel=1e-3)
    clim = analytics.climatology(df[df.sensor == "S1"], (2025, 2026))
    st = analytics.build_status(df, clim, TH, 1)
    row = st[st.month == "2026-05"].iloc[0]
    assert row["sensor"] == "NISAR"
    assert row["area_km2"] == pytest.approx(row["area_s1_km2"], rel=1e-3)


def test_area_storage_power_law():
    area = np.linspace(10, 100, 20)
    vol = 3.0 * area ** 1.4
    a, b, r2 = analytics.fit_area_storage(area, vol)
    assert a == pytest.approx(3.0, rel=1e-6) and b == pytest.approx(1.4, rel=1e-6) and r2 > 0.999
    assert analytics.fit_area_storage(area[:4], vol[:4]) is None


def test_month_helpers():
    assert month_range("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert shift_month("2026-01", -1) == "2025-12"
    assert shift_month("2025-12", 13) == "2027-01"


def test_flag_implausible_drops_marks_isolated_collapse_only():
    rows = [("2026-0%d" % m, a) for m, a in [(1, 100), (2, 0.4), (3, 101), (4, 98), (5, 1.0), (6, 0.8), (7, 0.9)]]
    df = pd.DataFrame([{"reservoir_id": "R", "month": m, "sensor": "S1", "area_km2": a, "n_obs": 3, "quality": "good"}
                       for m, a in rows])
    out = analytics.flag_implausible_drops(df).set_index("month")["quality"]
    assert out["2026-02"] == "bad"            # 100 -> 0.4 -> 101: wind, not drought
    assert out["2026-05"] == "good"           # 98 -> 1.0 -> 0.8: sustained low (next month also low)
    assert (out.drop("2026-02") == "good").all()
