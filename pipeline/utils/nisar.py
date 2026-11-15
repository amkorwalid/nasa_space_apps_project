"""NISAR L2 GCOV search (asf_search) and windowed reads over HTTPS (earthaccess + h5py).

Ported from the Track B prototype (prototypes/water_detection/polygone.py): only the
reservoir window is read from the remote HDF5 file, never the whole scene.
"""
from __future__ import annotations

import os
import re
import time

import numpy as np
from shapely.geometry import shape

from .io import step

GRID = "/science/LSAR/GCOV/grids/frequencyA"
BLOCK = 16 * 1024 * 1024
INVENTORY_COLUMNS = ["scene_id", "date", "track", "direction", "polarizations", "reservoir_id",
                     "frame", "cycle", "coverage_pct", "url"]
POLS = {"SH": "HH", "SV": "VV", "DH": "HH+HV", "DV": "VV+VH", "QP": "HH+HV+VH+VV"}
SCENE_RE = re.compile(
    r"NISAR_L2_[A-Z]{2}_GCOV_(?P<cycle>\d{3})_(?P<track>\d{3})_(?P<dir>[AD])_(?P<frame>\d{3})_"
    r"(?P<mode>\d{4})_(?P<pol>[A-Z]{4})_[A-Z]_(?P<start>\d{8})T\d{6}_\d{8}T\d{6}_(?P<crid>[A-Z]\d{5})"
)


def search(geom, start: str, end: str):
    """GCOV .h5 URLs intersecting geom between start and end (ISO dates) + scene footprints."""
    import asf_search as asf

    results = asf.geo_search(dataset="NISAR", processingLevel="GCOV",
                             intersectsWith=geom.envelope.wkt, start=start, end=end)
    try:
        urls = results.find_urls(extension=".h5", directAccess=False)
    except Exception:
        urls = [r.properties.get("url", "") for r in results]
    urls = sorted({u for u in urls if u.endswith(".h5") and "QA_STATS" not in u})
    footprints = {}
    for r in results:
        try:
            g = shape(r.geometry)
        except Exception:
            continue
        for key in ("sceneName", "fileID", "fileName"):
            m = SCENE_RE.search(str(r.properties.get(key) or ""))
            if m:
                footprints[m.group(0)] = g
    return urls, footprints


def inventory_rows(urls, reservoir_id: str, geom=None, footprints=None) -> list[dict]:
    """One row per acquisition (latest processing version kept), newest first."""
    best: dict = {}
    for url in urls:
        name = os.path.basename(url)[:-3]
        m = SCENE_RE.search(name)
        if not m:
            continue
        d = m["start"]
        key = (m["track"], m["frame"], m["dir"], d)
        cov = None
        fp = (footprints or {}).get(m.group(0))
        if geom is not None and fp is not None and geom.area > 0:
            try:
                cov = round(100 * geom.intersection(fp.buffer(0)).area / geom.area, 1)
            except Exception:
                cov = None
        row = {"scene_id": name, "date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "track": int(m["track"]),
               "direction": "ascending" if m["dir"] == "A" else "descending",
               "polarizations": POLS.get(m["pol"][:2], m["pol"]), "reservoir_id": reservoir_id,
               "frame": int(m["frame"]), "cycle": int(m["cycle"]), "coverage_pct": cov, "url": url,
               "_crid": m["crid"]}
        if key not in best or row["_crid"] > best[key]["_crid"]:
            best[key] = row
    return sorted(best.values(), key=lambda r: r["date"], reverse=True)


def choose_track(rows: list[dict], track: int | None = None):
    """(track, frame) that covers the zone best, preferring more acquisitions."""
    groups: dict = {}
    for r in rows:
        groups.setdefault((r["track"], r["frame"]), []).append(r)
    if not groups:
        return None
    if track is not None:
        groups = {k: v for k, v in groups.items() if k[0] == track} or groups

    def score(k):
        cov = [float(r["coverage_pct"]) for r in groups[k] if r["coverage_pct"] not in (None, "")]
        c = sum(cov) / len(cov) if cov else 50.0
        return (c >= 99, c, len(groups[k]))

    return max(groups, key=score)


def login():
    import earthaccess

    if os.environ.get("EARTHDATA_TOKEN"):
        earthaccess.login(strategy="environment")
    elif os.environ.get("EARTHDATA_USER") and os.environ.get("EARTHDATA_PASS"):
        os.environ.setdefault("EARTHDATA_USERNAME", os.environ["EARTHDATA_USER"])
        os.environ.setdefault("EARTHDATA_PASSWORD", os.environ["EARTHDATA_PASS"])
        earthaccess.login(strategy="environment")
    else:
        earthaccess.login()
    return earthaccess.get_fsspec_https_session()


def _read_rows(ds, r0, r1, c0, c1, chunk=256):
    out = np.empty((r1 - r0, c1 - c0), dtype=ds.dtype)
    for a in range(r0, r1, chunk):
        b = min(a + chunk, r1)
        out[a - r0:b - r0] = ds[a:b, c0:c1]
    return out


def read_window(fs, url: str, geom_wgs84, margin_m: float, out_file, date: str = "") -> dict:
    """Read HH/HV/mask for geom (+margin) from a remote GCOV file into an .npz.
    Returns a small metadata dict (shape, epsg, mask attributes)."""
    import h5py
    from pyproj import Transformer

    t0 = time.time()
    with fs.open(url, "rb", cache_type="background", block_size=BLOCK) as f, h5py.File(f, "r") as h5:
        if GRID not in h5:
            raise RuntimeError(f"{GRID} not in {os.path.basename(url)}")
        x = h5[f"{GRID}/xCoordinates"][:]
        y = h5[f"{GRID}/yCoordinates"][:]
        epsg = int(h5[f"{GRID}/projection"][()])
        to_scene = Transformer.from_crs(4326, epsg, always_xy=True)
        minx, miny, maxx, maxy = to_scene.transform_bounds(*geom_wgs84.bounds)
        cols = np.where((x >= minx - margin_m) & (x <= maxx + margin_m))[0]
        rows = np.where((y >= miny - margin_m) & (y <= maxy + margin_m))[0]
        if len(cols) < 3 or len(rows) < 3:
            raise RuntimeError("zone outside this scene")
        r0, r1, c0, c1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
        hh = _read_rows(h5[f"{GRID}/HHHH"], r0, r1, c0, c1)
        hv = _read_rows(h5[f"{GRID}/HVHV"], r0, r1, c0, c1) if f"{GRID}/HVHV" in h5 else None
        mask, mask_attrs = np.array([]), {}
        if f"{GRID}/mask" in h5:
            mds = h5[f"{GRID}/mask"]
            mask = mds[r0:r1, c0:c1]
            mask_attrs = {k: (v.decode() if isinstance(v, bytes) else str(v)) for k, v in mds.attrs.items()}
    with np.errstate(divide="ignore", invalid="ignore"):
        hh_db = (10 * np.log10(hh)).astype("float32")
        hv_db = (10 * np.log10(hv)).astype("float32") if hv is not None else np.array([])
    xs, ys = x[c0:c1], y[r0:r1]
    if ys[0] < ys[-1]:  # north up
        ys, hh_db = ys[::-1], hh_db[::-1]
        hv_db = hv_db[::-1] if hv_db.size else hv_db
        mask = mask[::-1] if mask.size else mask
    np.savez_compressed(out_file, hh_db=hh_db, hv_db=hv_db, mask=mask, x=xs, y=ys, epsg=epsg,
                        scene=os.path.basename(url), date=date)
    step(f"      window {hh_db.shape[0]}x{hh_db.shape[1]} px read in {time.time() - t0:.0f} s")
    return {"shape": list(hh_db.shape), "epsg": epsg, "pixel_m": float(abs(x[1] - x[0])),
            "mask_attrs": mask_attrs, "mask_values": [int(v) for v in np.unique(mask)[:50]] if mask.size else []}
