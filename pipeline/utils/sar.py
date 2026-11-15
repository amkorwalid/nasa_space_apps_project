"""Contract 5 water-detection algorithm, sensor-agnostic.

The same functions run on NISAR (HH/HV, steps 03-05) and Sentinel-1 (VV/VH, step 06),
so both tracks implement exactly one written spec (contracts/water_detection_spec.md):

1. clip to analysis zone + 1 km land buffer (the caller builds the grid that way)
2. dB + 5x5 median filter
3. mask invalid / layover / shadow / border-noise pixels (`valid`)
4. Otsu threshold on the co-pol band, fixed fallback when the histogram is not bimodal
5. keep pixels below the threshold inside the search zone (JRC max extent + 500 m) with HAND < 15 m
6. 3x3 morphological opening, drop blobs < 10 px, keep blobs touching the reservoir
7. monthly composite: water if detected in >= 50 % of the month's valid scenes
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import binary_dilation, binary_opening, label, median_filter


@dataclass
class DetectParams:
    fallback_db: float = -18.0
    plausible_db: tuple[float, float] = (-30.0, -10.0)
    median_px: int = 5
    opening_px: int = 3
    min_blob_px: int = 10
    keep_touching_only: bool = True
    use_cross: bool = False
    cross_offset_db: float = -6.0
    min_class_frac: float = 0.01   # Otsu split leaving < 1 % in a class = not bimodal
    otsu_region: str = "clip"      # "clip" = zone + land buffer (C-band) | "search" = search zone only (L-band)
    cap_dark_mean_db: float | None = None   # see otsu_threshold

    @classmethod
    def from_cfg(cls, det: dict, sensor: str) -> "DetectParams":
        s = det[sensor]
        return cls(
            fallback_db=float(s["fallback_db"]),
            plausible_db=tuple(float(v) for v in s["plausible_db"]),
            median_px=int(det["median_filter_px"]),
            opening_px=int(det["opening_px"]),
            min_blob_px=int(det["min_blob_px"]),
            keep_touching_only=bool(det.get("keep_touching_only", True)),
            use_cross=bool(s.get("use_hv", s.get("use_vh", False))),
            cross_offset_db=float(s.get("hv_offset_db", -6.0)),
            otsu_region=str(s.get("otsu_region", "clip")),
            cap_dark_mean_db=float(s["cap_dark_mean_db"]) if s.get("cap_dark_mean_db") is not None else None,
        )


@dataclass
class Detection:
    water: np.ndarray
    threshold_db: float
    method: str                     # "otsu" | "fallback"
    valid_fraction: float           # valid share of the search zone
    co_filtered: np.ndarray = field(repr=False, default=None)
    cross_threshold_db: float | None = None

    def area_km2(self, pixel_area_m2: float) -> float:
        return float(self.water.sum() * pixel_area_m2 / 1e6)


def to_db(linear: np.ndarray) -> np.ndarray:
    lin = np.asarray(linear, dtype="float32")
    with np.errstate(divide="ignore", invalid="ignore"):
        db = 10.0 * np.log10(lin)
    db[~np.isfinite(db)] = np.nan
    return db


def speckle_filter(db: np.ndarray, valid: np.ndarray, size: int = 5) -> np.ndarray:
    """Median filter that ignores invalid pixels (they are filled with the scene median first)."""
    if size <= 1:
        return np.where(valid, db, np.nan)
    fill = float(np.nanmedian(db[valid])) if valid.any() else 0.0
    out = median_filter(np.where(valid, db, fill).astype("float32"), size=size)
    out[~valid] = np.nan
    return out


def otsu_threshold(values: np.ndarray, fallback: float, plausible: tuple[float, float],
                   min_class_frac: float = 0.01, bins: int = 256,
                   cap_dark_mean: float | None = None) -> tuple[float, str]:
    """Otsu threshold on finite values.

    * inside the plausible range -> ("otsu")
    * darker than the range, or no real split -> fallback ("fallback")
    * brighter than the range: the split falls between land classes or on wind-roughened water.
      If the dark class still looks like water (its mean <= cap_dark_mean dB; without that setting:
      a bimodal histogram, eta >= MIN_ETA) the threshold is capped at the range limit ("capped"),
      otherwise there is no water mode (e.g. an empty reservoir) -> fallback.
    """
    v = np.asarray(values, dtype="float64")
    v = v[np.isfinite(v)]
    if v.size < 50 or np.ptp(v) < 1e-6:
        return float(fallback), "fallback"
    counts, edges = np.histogram(v, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    t = otsu_from_histogram(centres, counts)
    if t is None or t < plausible[0]:
        return float(fallback), "fallback"
    if t > plausible[1]:
        dark = v[v < t]
        if dark.size < min_class_frac * v.size:
            return float(fallback), "fallback"
        water_like = float(dark.mean()) <= cap_dark_mean if cap_dark_mean is not None else             otsu_effectiveness(centres, counts) >= MIN_ETA
        return (float(plausible[1]), "capped") if water_like else (float(fallback), "fallback")
    low = (v < t).mean()
    if low < min_class_frac or low > 1 - min_class_frac:
        return float(fallback), "fallback"
    return float(t), "otsu"


MIN_ETA = 0.68


def otsu_effectiveness(centres, counts) -> float:
    """Otsu's effectiveness eta = max between-class variance / total variance (0..1)."""
    c = np.asarray(counts, dtype="float64")
    x = np.asarray(centres, dtype="float64")
    tot = c.sum()
    if tot <= 0:
        return 0.0
    mean = (c * x).sum() / tot
    var = (c * (x - mean) ** 2).sum() / tot
    if var <= 0:
        return 0.0
    w0 = np.cumsum(c) / tot
    w1 = 1 - w0
    s0 = np.cumsum(c * x) / tot
    with np.errstate(divide="ignore", invalid="ignore"):
        m0 = s0 / w0
        m1 = (mean - s0) / w1
        between = w0 * w1 * (m0 - m1) ** 2
    between[~np.isfinite(between)] = 0
    return float(between.max() / var)


def otsu_from_histogram(centres, counts) -> float | None:
    """Otsu on a histogram (used locally and on Earth Engine histograms)."""
    c = np.asarray(counts, dtype="float64")
    x = np.asarray(centres, dtype="float64")
    total = c.sum()
    if total <= 0 or len(x) < 2:
        return None
    w0 = np.cumsum(c)
    w1 = total - w0
    s0 = np.cumsum(c * x)
    with np.errstate(divide="ignore", invalid="ignore"):
        m0 = s0 / w0
        m1 = (s0[-1] - s0) / w1
        between = w0 * w1 * (m0 - m1) ** 2
    between[~np.isfinite(between)] = -1
    i = int(np.argmax(between))
    if i + 1 >= len(x) or between[i] <= 0:
        return None
    return float((x[i] + x[i + 1]) / 2)


def hand_ok_mask(dem: np.ndarray | None, max_extent: np.ndarray, hand_max_m: float) -> np.ndarray | None:
    """Terrain filter (HAND proxy): a pixel more than `hand_max_m` above the reservoir's
    maximum water level cannot be open water. The max level is the 90th percentile of the
    DEM inside the JRC maximum extent. Pixels with no DEM value are kept."""
    if dem is None:
        return None
    inside = max_extent & np.isfinite(dem)
    if inside.sum() < 10:
        return None
    level = float(np.nanpercentile(dem[inside], 90))
    ok = ~(dem > level + hand_max_m)
    return ok


def cleanup(water: np.ndarray, opening_px: int, min_blob_px: int,
            reservoir: np.ndarray | None = None) -> np.ndarray:
    w = water.astype(bool)
    if opening_px > 1:
        w = binary_opening(w, structure=np.ones((opening_px, opening_px), bool))
    lab, n = label(w)
    if n == 0:
        return w
    sizes = np.bincount(lab.ravel())
    keep = sizes >= min_blob_px
    keep[0] = False
    if reservoir is not None and reservoir.any():
        touching = np.unique(lab[binary_dilation(reservoir, iterations=1) & (lab > 0)])
        mask = np.zeros_like(keep)
        mask[touching] = True
        keep &= mask
    return keep[lab]


def detect_water(co_db: np.ndarray, valid: np.ndarray, search_zone: np.ndarray, p: DetectParams,
                 reservoir: np.ndarray | None = None, hand_ok: np.ndarray | None = None,
                 cross_db: np.ndarray | None = None) -> Detection:
    """Run Contract 5 steps 2-6 on one scene already clipped to zone + land buffer."""
    valid = valid & np.isfinite(co_db)
    co_f = speckle_filter(co_db, valid, p.median_px)
    region = valid & search_zone if p.otsu_region == "search" else valid
    thr, method = otsu_threshold(co_f[region], p.fallback_db, p.plausible_db, p.min_class_frac,
                                 cap_dark_mean=p.cap_dark_mean_db)
    water = (co_f < thr) & search_zone & valid
    if hand_ok is not None:
        water &= hand_ok
    cross_thr = None
    if p.use_cross and cross_db is not None and np.isfinite(cross_db).any():
        cvalid = valid & np.isfinite(cross_db)
        cross_f = speckle_filter(cross_db, cvalid, p.median_px)
        lo, hi = p.plausible_db
        cregion = cvalid & search_zone if p.otsu_region == "search" else cvalid
        cross_thr, cm = otsu_threshold(cross_f[cregion], p.fallback_db + p.cross_offset_db,
                                       (lo + p.cross_offset_db, hi + p.cross_offset_db), p.min_class_frac,
                                       cap_dark_mean=None if p.cap_dark_mean_db is None
                                       else p.cap_dark_mean_db + p.cross_offset_db)
        water &= np.where(cvalid, cross_f < cross_thr, True)
    water = cleanup(water, p.opening_px, p.min_blob_px, reservoir if p.keep_touching_only else None)
    zone_px = search_zone.sum()
    valid_frac = float((valid & search_zone).sum() / zone_px) if zone_px else 0.0
    return Detection(water, thr, method, valid_frac, co_f, cross_thr)


def majority_composite(masks: list[np.ndarray], valids: list[np.ndarray], majority: float = 0.5):
    """Per-pixel vote over the month's scenes (only scenes where the pixel is valid vote).
    Returns (water, n_valid_votes)."""
    if not masks:
        raise ValueError("no scenes to composite")
    w = np.zeros(masks[0].shape, dtype="float32")
    n = np.zeros(masks[0].shape, dtype="int16")
    for m, v in zip(masks, valids):
        w += (m & v)
        n += v
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(n > 0, w / np.maximum(n, 1), 0)
    return (frac >= majority) & (n > 0), n


def month_quality(valid_fraction: float, n_obs: int, any_fallback: bool) -> str:
    """Contract 2 quality: good | partial | bad."""
    if n_obs == 0 or valid_fraction < 0.7:
        return "bad"
    if n_obs < 2 or valid_fraction < 0.9 or any_fallback:
        return "partial"
    return "good"


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
WATER_RGBA = (30, 120, 220, 210)


def mask_to_png(mask: np.ndarray, grid, file, rgba=WATER_RGBA, max_px: int = 1600):
    """Water mask -> transparent PNG in EPSG:4326. Returns [[minLon, minLat], [maxLon, maxLat]]."""
    from PIL import Image
    from rasterio.crs import CRS as RCRS
    from rasterio.transform import array_bounds
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    src_crs, dst_crs = RCRS.from_user_input(grid.crs.to_wkt()), RCRS.from_epsg(4326)
    w, s, e, n = array_bounds(grid.height, grid.width, grid.transform)
    dst_tr, dw, dh = calculate_default_transform(src_crs, dst_crs, grid.width, grid.height, w, s, e, n)
    scale = max(dw, dh) / max_px
    if scale > 1:
        dw, dh = int(np.ceil(dw / scale)), int(np.ceil(dh / scale))
        dst_tr, dw, dh = calculate_default_transform(src_crs, dst_crs, grid.width, grid.height, w, s, e, n,
                                                     dst_width=dw, dst_height=dh)
    dst = np.zeros((dh, dw), np.uint8)
    reproject(mask.astype(np.uint8), dst, src_transform=grid.transform, src_crs=src_crs,
              dst_transform=dst_tr, dst_crs=dst_crs, resampling=Resampling.max if scale > 1 else Resampling.nearest)
    img = np.zeros((dh, dw, 4), np.uint8)
    img[dst == 1] = rgba
    Image.fromarray(img, "RGBA").save(file, optimize=True)
    ow, os_, oe, on = array_bounds(dh, dw, dst_tr)
    return [[round(ow, 6), round(os_, 6)], [round(oe, 6), round(on, 6)]]


def quicklook(db: np.ndarray, water: np.ndarray, zone: np.ndarray, file, title: str,
              vmin: float = -28, vmax: float = 0) -> None:
    """Radar image + detected water + search zone. Uses the object-oriented Matplotlib API
    (no pyplot state), so it is safe to call from worker threads."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    h, w = db.shape
    fig = Figure(figsize=(8, 8 * h / max(w, 1) + 0.6))
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.imshow(db, cmap="gray", vmin=vmin, vmax=vmax, interpolation="nearest")
    over = np.zeros((h, w, 4))
    over[water] = (0.12, 0.47, 0.86, 0.6)
    ax.imshow(over, interpolation="nearest")
    if zone.any() and not zone.all():
        ax.contour(zone.astype(float), levels=[0.5], colors="red", linewidths=0.6, linestyles="dashed")
    ax.set_title(title, fontsize=9)
    ax.axis("off")
    fig.savefig(file, dpi=110, bbox_inches="tight")
