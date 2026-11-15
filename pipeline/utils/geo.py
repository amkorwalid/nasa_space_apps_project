"""Geometry and raster-grid helpers (pure shapely / pyproj / rasterio)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union


def depth(coords) -> int:
    n = 0
    while isinstance(coords, (list, tuple)) and coords:
        n += 1
        coords = coords[0]
    return n


def to_shape(geom: dict):
    """GeoJSON geometry -> valid shapely geometry, fixing a mis-declared Polygon/MultiPolygon."""
    if geom.get("type") in ("Polygon", "MultiPolygon"):
        real = {3: "Polygon", 4: "MultiPolygon"}.get(depth(geom["coordinates"]))
        if real and real != geom["type"]:
            geom = {"type": real, "coordinates": geom["coordinates"]}
    g = shape(geom)
    return g if g.is_valid else g.buffer(0)


def utm_crs(lon: float, lat: float) -> CRS:
    zone = int((lon + 180) // 6) + 1
    return CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def to_crs(geom, src, dst):
    t = Transformer.from_crs(src, dst, always_xy=True)
    return shp_transform(t.transform, geom)


def local_crs(geom) -> CRS:
    c = geom.centroid
    return utm_crs(c.x, c.y)


def area_km2(geom_wgs84) -> float:
    crs = local_crs(geom_wgs84)
    return to_crs(geom_wgs84, 4326, crs).area / 1e6


def buffer_m(geom_wgs84, metres: float):
    """Buffer a WGS84 geometry by metres (computed in its UTM zone)."""
    crs = local_crs(geom_wgs84)
    g = to_crs(geom_wgs84, 4326, crs).buffer(metres)
    return to_crs(g, crs, 4326)


def union(geoms):
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    return unary_union(geoms) if len(geoms) > 1 else (geoms[0] if geoms else None)


def round_coords(geom_json: dict, decimals: int) -> dict:
    def r(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            return [round(float(v), decimals) for v in c]
        return [r(x) for x in c]

    return {"type": geom_json["type"], "coordinates": r(geom_json["coordinates"])}


def web_geometry(geom, tolerance_deg: float, decimals: int) -> dict:
    g = geom.simplify(tolerance_deg, preserve_topology=True)
    if g.is_empty:
        g = geom
    return round_coords(mapping(g), decimals)


@dataclass
class Grid:
    """A north-up raster grid in a projected CRS."""

    crs: CRS
    transform: "object"  # rasterio Affine
    width: int
    height: int

    @property
    def res(self) -> float:
        return float(self.transform.a)

    @property
    def bounds(self):
        from rasterio.transform import array_bounds

        return array_bounds(self.height, self.width, self.transform)  # (west, south, east, north)

    def bounds_wgs84(self):
        """[[minLon, minLat], [maxLon, maxLat]] of the grid footprint."""
        t = Transformer.from_crs(self.crs, 4326, always_xy=True)
        w, s, e, n = t.transform_bounds(*self.bounds, densify_pts=21)
        return [[round(w, 6), round(s, 6)], [round(e, 6), round(n, 6)]]

    def rasterize(self, geom_wgs84, all_touched: bool = False) -> np.ndarray:
        from rasterio.features import geometry_mask

        g = to_crs(geom_wgs84, 4326, self.crs)
        return geometry_mask([mapping(g)], out_shape=(self.height, self.width), transform=self.transform,
                             invert=True, all_touched=all_touched)

    def to_dict(self) -> dict:
        t = self.transform
        return {"epsg": self.crs.to_epsg(), "transform": [t.a, t.b, t.c, t.d, t.e, t.f],
                "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, d: dict) -> "Grid":
        from affine import Affine

        return cls(CRS.from_epsg(int(d["epsg"])), Affine(*d["transform"]), int(d["width"]), int(d["height"]))


def grid_for(geom_wgs84, res_m: float, margin_m: float = 0.0, crs: CRS | None = None) -> Grid:
    """North-up grid covering a geometry (+ margin) at res_m in its UTM zone, snapped to res."""
    from rasterio.transform import from_origin

    crs = crs or local_crs(geom_wgs84)
    g = to_crs(geom_wgs84, 4326, crs)
    minx, miny, maxx, maxy = g.bounds
    minx = np.floor((minx - margin_m) / res_m) * res_m
    miny = np.floor((miny - margin_m) / res_m) * res_m
    maxx = np.ceil((maxx + margin_m) / res_m) * res_m
    maxy = np.ceil((maxy + margin_m) / res_m) * res_m
    width, height = int(round((maxx - minx) / res_m)), int(round((maxy - miny) / res_m))
    return Grid(crs, from_origin(minx, maxy, res_m, res_m), width, height)


def grid_from_coords(x: np.ndarray, y: np.ndarray, epsg: int) -> Grid:
    """Grid from pixel-centre coordinate vectors (NISAR GCOV x/yCoordinates), north up."""
    from rasterio.transform import from_origin

    dx, dy = abs(float(x[1] - x[0])), abs(float(y[1] - y[0]))
    return Grid(CRS.from_epsg(int(epsg)), from_origin(float(x[0]) - dx / 2, float(y[0]) + dy / 2, dx, dy),
                len(x), len(y))
