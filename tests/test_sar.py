"""Contract 5 algorithm on synthetic radar scenes with a known water body."""
import numpy as np
import pytest

from pipeline.utils import sar


def synthetic_scene(seed=0, water_db=-22.0, land_db=-9.0, shape=(200, 300), sigma=1.5):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    lake = ((yy - 100) / 50) ** 2 + ((xx - 150) / 90) ** 2 <= 1
    db = np.where(lake, water_db, land_db) + rng.normal(0, sigma, shape)
    return db.astype("float32"), lake


def test_otsu_splits_bimodal_histogram():
    db, lake = synthetic_scene()
    t, method = sar.otsu_threshold(db.ravel(), -18, (-30, -10))
    assert method == "otsu"
    assert -20 < t < -11


def test_otsu_falls_back_when_not_bimodal():
    v = np.random.default_rng(1).normal(-9, 0.5, 5000)
    t, method = sar.otsu_threshold(v, -18, (-30, -10))
    assert method == "fallback" and t == -18


def test_otsu_histogram_matches_known_split():
    centres = np.arange(-30, 0, 1.0)
    counts = np.where(centres < -15, 100, 300)
    t = sar.otsu_from_histogram(centres, counts)
    assert -16 <= t <= -14


def test_detect_water_recovers_lake_area():
    db, lake = synthetic_scene()
    valid = np.ones_like(lake)
    search = np.ones_like(lake)
    d = sar.detect_water(db, valid, search, sar.DetectParams(), reservoir=lake)
    iou = (d.water & lake).sum() / (d.water | lake).sum()
    assert iou > 0.95
    assert d.method == "otsu"
    assert d.valid_fraction == 1.0


def test_search_zone_and_hand_filters_remove_false_water():
    db, lake = synthetic_scene()
    db[10:30, 10:40] = -24  # dark patch far from the lake (dry sand / shadow)
    valid = np.ones_like(lake)
    search = np.zeros_like(lake)
    search[40:160, 50:250] = True
    d = sar.detect_water(db, valid, search, sar.DetectParams(), reservoir=lake)
    assert not d.water[10:30, 10:40].any()
    hand = np.ones_like(lake)
    hand[:, 150:] = False
    d2 = sar.detect_water(db, valid, search, sar.DetectParams(), reservoir=lake, hand_ok=hand)
    assert not d2.water[:, 150:].any()


def test_cleanup_drops_small_and_detached_blobs():
    w = np.zeros((50, 50), bool)
    w[10:30, 10:30] = True        # big blob touching the reservoir
    w[40:42, 40:42] = True        # 4 px blob -> dropped (< 10 px)
    w[2:8, 40:48] = True          # 48 px blob not touching the reservoir -> dropped
    res = np.zeros_like(w)
    res[15:25, 15:25] = True
    out = sar.cleanup(w, opening_px=1, min_blob_px=10, reservoir=res)
    assert out[20, 20] and not out[41, 41] and not out[5, 44]


def test_hv_check_rejects_dark_copol_bright_crosspol():
    db, lake = synthetic_scene()
    hv = db - 7
    sand = np.zeros_like(lake)
    sand[90:110, 230:245] = True   # dark in HH but bright in HV, touching the lake edge
    db[sand] = -22
    hv[sand] = -12
    p = sar.DetectParams(use_cross=True, keep_touching_only=False)
    d = sar.detect_water(db, np.ones_like(lake), np.ones_like(lake), p, reservoir=lake, cross_db=hv)
    assert d.water[sand].mean() < 0.1


def test_majority_composite_ignores_invalid_votes():
    a = np.array([[1, 1, 0, 0]], bool)
    b = np.array([[1, 0, 0, 1]], bool)
    c = np.array([[1, 1, 1, 0]], bool)
    v = np.ones_like(a)
    vb = np.array([[1, 0, 1, 1]], bool)   # pixel 2 invalid in scene b
    comp, n = sar.majority_composite([a, b, c], [v, vb, v], 0.5)
    assert comp.tolist() == [[True, True, False, False]]
    assert n.tolist() == [[3, 2, 3, 3]]


@pytest.mark.parametrize("vf,n,fb,expected", [(0.95, 3, False, "good"), (0.95, 1, False, "partial"),
                                              (0.8, 3, False, "partial"), (0.6, 3, False, "bad"),
                                              (0.95, 3, True, "partial")])
def test_month_quality(vf, n, fb, expected):
    assert sar.month_quality(vf, n, fb) == expected


def test_hand_ok_uses_reservoir_level():
    dem = np.full((10, 10), 100.0)
    dem[:, 5:] = 140.0
    ext = np.zeros((10, 10), bool)
    ext[:, :3] = True
    ok = sar.hand_ok_mask(dem, ext, 15)
    assert ok[:, :5].all() and not ok[:, 5:].any()


def test_mask_to_png_bounds(tmp_path):
    from pipeline.utils import geo
    from shapely.geometry import box

    g = geo.grid_for(box(-7.6, 32.4, -7.5, 32.5), 40)
    m = np.zeros((g.height, g.width), bool)
    m[10:20, 10:20] = True
    b = sar.mask_to_png(m, g, tmp_path / "x.png")
    assert b[0][0] < -7.59 and b[1][0] > -7.51 and b[0][1] < 32.41 and b[1][1] > 32.49
    assert (tmp_path / "x.png").stat().st_size > 0


def test_threshold_is_capped_only_for_bimodal_histograms():
    rng = np.random.default_rng(3)
    # L-band-like: water at -20 dB, dry lake bed / soil at -14 dB -> Otsu ~ -17, above the -18 limit
    v = np.r_[rng.normal(-20, 1.0, 4000), rng.normal(-14, 1.5, 6000)]
    t, m = sar.otsu_threshold(v, -18, (-30, -18))
    assert m == "capped" and t == -18
    # unimodal land only: no water mode -> fallback, never capped
    t2, m2 = sar.otsu_threshold(rng.normal(-12, 1.0, 8000), -18, (-30, -14))
    assert m2 == "fallback"


def test_otsu_effectiveness_separates_unimodal_from_bimodal():
    rng = np.random.default_rng(4)
    uni = rng.normal(0, 1, 20000)
    bi = np.r_[rng.normal(-5, 1, 10000), rng.normal(5, 1, 10000)]
    for v, lo, hi in [(uni, 0.55, 0.68), (bi, 0.85, 1.0)]:
        c, e = np.histogram(v, 256)
        eta = sar.otsu_effectiveness((e[:-1] + e[1:]) / 2, c)
        assert lo <= eta <= hi


def test_cap_uses_dark_class_mean_windy_lake_vs_empty_bed():
    rng = np.random.default_rng(5)
    # windy lake: water ~ -16.7 dB (dark mean below -15.5) + land -9 -> Otsu above -13 -> capped
    windy = np.r_[rng.normal(-16.7, 1.2, 1500), rng.normal(-9, 2.0, 8500)]
    t, m = sar.otsu_threshold(windy, -18, (-24, -13), cap_dark_mean=-15.5)
    assert (t, m) == (-13, "capped")
    # empty lake bed: dark class ~ -11.7 dB is not water -> fallback
    empty = np.r_[rng.normal(-11.7, 1.0, 3300), rng.normal(-7, 1.5, 6700)]
    t, m = sar.otsu_threshold(empty, -18, (-24, -13), cap_dark_mean=-15.5)
    assert (t, m) == (-18, "fallback")


def test_vh_rescue_parameters_recover_windy_lake_but_not_empty_bed():
    """Search-zone VH: windy full lake (water ~ -24 dB) is detected; dry bed (~ -19 dB) is not."""
    rng = np.random.default_rng(6)
    p = sar.DetectParams(plausible_db=(-30, -19), fallback_db=-19, cap_dark_mean_db=-22,
                         otsu_region="search", keep_touching_only=False)
    yy, xx = np.mgrid[:120, :160]
    lake = ((yy - 60) / 40) ** 2 + ((xx - 80) / 60) ** 2 <= 1
    windy = np.where(lake, -24.0, -16.5) + rng.normal(0, 1.2, lake.shape)
    full = np.ones_like(lake)
    d = sar.detect_water(windy.astype("float32"), full, full, p, reservoir=lake)
    assert d.method in ("otsu", "capped") and (d.water & lake).sum() / lake.sum() > 0.9
    empty = np.where(lake, -19.3, -16.5) + rng.normal(0, 1.2, lake.shape)
    d2 = sar.detect_water(empty.astype("float32"), full, full, p, reservoir=lake)
    assert d2.method == "fallback"
