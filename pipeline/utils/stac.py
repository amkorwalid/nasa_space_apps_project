"""Microsoft Planetary Computer access (no account needed): Sentinel-1 RTC, JRC Global
Surface Water, Copernicus DEM GLO-30 and Sentinel-2 L2A, each read straight onto a Grid.

Items are searched once (unsigned) and every asset URL is signed just before it is read,
so long runs never hit an expired SAS token.
"""
from __future__ import annotations

import os
import threading
import time
from functools import lru_cache

import numpy as np

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff,.TIF",
    GDAL_HTTP_MAX_RETRY="5",
    GDAL_HTTP_RETRY_DELAY="2",
    GDAL_HTTP_MULTIPLEX="YES",
    GDAL_HTTP_VERSION="2",
    VSI_CACHE="TRUE",
    GDAL_CACHEMAX=512,
)
_lock = threading.Lock()


@lru_cache(maxsize=1)
def client():
    import pystac_client

    return pystac_client.Client.open(STAC_URL)


def search(collection: str, geom=None, bbox=None, datetime: str | None = None, query: dict | None = None,
           retries: int = 4) -> list:
    """All items of a collection intersecting geom/bbox (paged, retried)."""
    from shapely.geometry import mapping

    kw = {"collections": [collection]}
    if geom is not None:
        kw["intersects"] = mapping(geom)
    elif bbox is not None:
        kw["bbox"] = list(bbox)
    if datetime:
        kw["datetime"] = datetime
    if query:
        kw["query"] = query
    for i in range(retries):
        try:
            with _lock:
                return list(client().search(**kw).items())
        except Exception as e:  # network hiccup
            if i == retries - 1:
                raise
            time.sleep(3 * (i + 1))
            last = e  # noqa: F841
    return []


def sign(href: str) -> str:
    import planetary_computer as pc

    return pc.sign(href)


def read_to_grid(href: str, grid, resampling: str = "average", band: int = 1,
                 src_nodata: float | None = None, retries: int = 3) -> np.ndarray:
    """Read one COG asset onto `grid` (float32, NaN outside data). Uses COG overviews when the
    grid is coarser than the source, so only the needed bytes are fetched."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject, transform_bounds
    from rasterio.windows import Window, from_bounds

    rs = getattr(Resampling, resampling)
    for attempt in range(retries):
        try:
            with rasterio.Env(**GDAL_ENV), rasterio.open(sign(href)) as src:
                nod = src_nodata if src_nodata is not None else src.nodata
                b = transform_bounds(grid.crs.to_wkt(), src.crs, *grid.bounds, densify_pts=21)
                win = from_bounds(*b, transform=src.transform)
                c0, r0 = int(np.floor(win.col_off)) - 2, int(np.floor(win.row_off)) - 2
                win = Window(c0, r0, int(np.ceil(win.col_off + win.width)) + 2 - c0,
                             int(np.ceil(win.row_off + win.height)) + 2 - r0)
                full = Window(0, 0, src.width, src.height)
                try:
                    win = win.intersection(full)
                except Exception:
                    return np.full((grid.height, grid.width), np.nan, "float32")
                if win.width < 1 or win.height < 1:
                    return np.full((grid.height, grid.width), np.nan, "float32")
                src_res = abs(src.transform.a)
                factor = max(1, int(grid.res // src_res)) if src.crs.is_projected else 1
                out_h, out_w = max(1, int(win.height // factor)), max(1, int(win.width // factor))
                read_rs = rs if resampling in ("nearest", "bilinear", "cubic", "average", "mode")                     else Resampling.nearest
                arr = src.read(band, window=win, out_shape=(out_h, out_w), resampling=read_rs,
                               masked=False).astype("float32")
                from affine import Affine

                wt = src.window_transform(win) * Affine.scale(win.width / out_w, win.height / out_h)
                if nod is not None:
                    arr[arr == nod] = np.nan
                dst = np.full((grid.height, grid.width), np.nan, "float32")
                reproject(arr, dst, src_transform=wt, src_crs=src.crs, src_nodata=np.nan,
                          dst_transform=grid.transform, dst_crs=grid.crs.to_wkt(), dst_nodata=np.nan,
                          resampling=rs)
                return dst
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def mosaic(arrays: list[np.ndarray], how: str = "first") -> np.ndarray:
    """Combine reads of several tiles/slices on the same grid."""
    arrays = [a for a in arrays if a is not None]
    if not arrays:
        return None
    out = arrays[0].copy()
    for a in arrays[1:]:
        if how == "max":
            out = np.fmax(out, a)
        else:
            gap = ~np.isfinite(out)
            out[gap] = a[gap]
    return out


# ---------------------------------------------------------------------------
# Reference layers
# ---------------------------------------------------------------------------
def jrc_max_extent(grid, geom_wgs84) -> np.ndarray:
    """JRC GSW 'extent' (water ever seen 1984-2021) on the grid, as bool."""
    items = search("jrc-gsw", geom=geom_wgs84)
    arrs = [read_to_grid(it.assets["extent"].href, grid, "max", src_nodata=255) for it in items]
    m = mosaic(arrs, "max")
    return np.nan_to_num(m, nan=0) > 0 if m is not None else np.zeros((grid.height, grid.width), bool)


def jrc_occurrence(grid, geom_wgs84) -> np.ndarray:
    items = search("jrc-gsw", geom=geom_wgs84)
    arrs = [read_to_grid(it.assets["occurrence"].href, grid, "average", src_nodata=255) for it in items]
    return mosaic(arrs, "max")


def copernicus_dem(grid, geom_wgs84) -> np.ndarray | None:
    items = search("cop-dem-glo-30", geom=geom_wgs84)
    arrs = [read_to_grid(it.assets["data"].href, grid, "bilinear") for it in items]
    return mosaic(arrs, "first")


# ---------------------------------------------------------------------------
# Sentinel-1 RTC
# ---------------------------------------------------------------------------
def s1_items(geom_wgs84, start: str, end: str) -> list[dict]:
    """Light records of Sentinel-1 RTC items (IW, VV) over geom; dates are ISO."""
    items = search("sentinel-1-rtc", geom=geom_wgs84, datetime=f"{start}/{end}")
    from shapely.geometry import shape

    out = []
    for it in items:
        p = it.properties
        if p.get("sar:instrument_mode") != "IW" or "vv" not in it.assets:
            continue
        out.append({"id": it.id, "datetime": p["datetime"], "date": p["datetime"][:10],
                    "orbit": int(p["sat:relative_orbit"]), "direction": p.get("sat:orbit_state", ""),
                    "platform": p.get("platform", ""), "vv": it.assets["vv"].href,
                    "vh": it.assets["vh"].href if "vh" in it.assets else None,
                    "coverage": float(shape(it.geometry).intersection(geom_wgs84).area / geom_wgs84.area)
                    if geom_wgs84.area else 0.0})
    return out


def choose_orbit(items: list[dict], forced: int | None = None) -> int | None:
    """Relative orbit with full coverage of the zone and the most acquisition dates."""
    if forced is not None:
        return forced
    by: dict = {}
    for it in items:
        by.setdefault(it["orbit"], {}).setdefault(it["date"], 0.0)
        by[it["orbit"]][it["date"]] += it["coverage"]
    if not by:
        return None

    def score(o):
        covs = list(by[o].values())
        full = sum(c >= 0.98 for c in covs)
        return (full, np.mean(covs), len(covs))

    return max(by, key=score)


def s2_ndwi(item, grid) -> tuple[np.ndarray, np.ndarray]:
    """McFeeters NDWI (B03 - B08)/(B03 + B08) on the grid, and a clear-pixel mask from SCL."""
    g = read_to_grid(item.assets["B03"].href, grid, "average", src_nodata=0)
    n = read_to_grid(item.assets["B08"].href, grid, "average", src_nodata=0)
    scl = read_to_grid(item.assets["SCL"].href, grid, "nearest", src_nodata=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = (g - n) / (g + n)
    clear = np.isin(np.nan_to_num(scl, nan=0).astype(int), [4, 5, 6, 7, 11]) & np.isfinite(ndwi)
    return ndwi, clear


def cpu_workers(default: int = 8) -> int:
    return max(1, min(default, (os.cpu_count() or 4) * 2))
