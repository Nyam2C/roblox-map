# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "numpy==2.5.4", "pillow==12.3.0", "scipy==1.18.1", "shapely==2.2.0"]
# ///
"""C8: find the trees of one cell in the V-World satellite photo and write regions/<region>/cells/<cell>/trees.json (kept in git).

Usage:
  uv run src/trees.py --cells 8930e0af13bffff     # needs data/satellite/<cell>-z19.jpg and <cell>-z19.json (tile_x0, tile_y0 of its top-left)
  uv run src/trees.py --selftest                  # import check only

Green and not too bright = crown; buildings are cut out (dark roofs look green) and no trunk stands on a road. Crowns are packed
with discs from the thickest part outwards, so a wood becomes several trees and a street row becomes a row. build_luau.py reads the
file and makes the trees (streets.tree_items); without it the old rule (a tree every tree_spacing_m beside a sidewalk) stays.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import h3
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from shapely.geometry import LineString

import common
import db
import layout

SAT_DIR = "data/satellite"
ZOOM = 19
DOWN = 2                 # work at half the photo's resolution: 0.237 -> 0.474 m per pixel
R_MIN, R_MAX = 1.6, 5.0  # crown radius range in metres
SHRINK = 0.75            # a placed crown clears this fraction of its radius, so neighbours overlap a little
GCC_MIN = 0.405          # green share of the pixel's colour; gravel and roofs are below it, crowns above


def canopy_mask(rgb: np.ndarray, gcc_min: float = GCC_MIN) -> np.ndarray:
    """True where the photo shows crown: green, not bright (lawn, green roofs are brighter), cleaned of specks and holes."""
    r, g, b = (rgb[..., i].astype(float) for i in range(3))
    v = rgb.max(axis=2).astype(float)
    m = (g / np.maximum(r + g + b, 1.0) > gcc_min) & (g > r + 8) & (v < 150) & (v > 18)
    m = ndi.binary_closing(ndi.binary_opening(m, iterations=1), iterations=2)
    return ndi.binary_fill_holes(ndi.binary_opening(m, iterations=2) | (ndi.uniform_filter(m.astype(float), 9) > 0.6))


def pack_crowns(canopy: np.ndarray, allowed: np.ndarray, m_per_px: float) -> list[tuple[int, int, float]]:
    """(row, col, crown radius m): repeatedly the thickest spot where a trunk may stand, then clear a disc around it."""
    c = canopy.copy()
    yy, xx = np.indices(c.shape)
    out: list[tuple[int, int, float]] = []
    while True:
        d = ndi.distance_transform_edt(c) * m_per_px
        d[~allowed] = 0.0
        i, j = np.unravel_index(int(np.argmax(d)), d.shape)
        if d[i, j] < R_MIN:
            return out
        radius = min(max(d[i, j] * 1.15, 2.0), R_MAX)
        out.append((int(i), int(j), float(radius)))
        c[(yy - i) ** 2 + (xx - j) ** 2 <= (radius * SHRINK / m_per_px) ** 2] = False


class Georef:
    """Pixels of the big satellite image <-> lat/lon (web mercator, tile_x0/tile_y0 = the top-left tile)."""

    def __init__(self, tile_x0: int, tile_y0: int, zoom: int = ZOOM) -> None:
        self.x0, self.y0, self.n = tile_x0, tile_y0, 2 ** zoom

    def to_px(self, lat: float, lon: float) -> tuple[float, float]:
        tx = (lon + 180) / 360 * self.n
        ty = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * self.n
        return (tx - self.x0) * 256, (ty - self.y0) * 256

    def to_latlon(self, px: float, py: float) -> tuple[float, float]:
        tx, ty = self.x0 + px / 256, self.y0 + py / 256
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / self.n)))), tx / self.n * 360 - 180

    def m_per_px(self, lat: float) -> float:
        return 156543.03392 * math.cos(math.radians(lat)) / self.n


def _fill(size: tuple[int, int], polygons: Sequence[Sequence[tuple[float, float]]]) -> np.ndarray:
    img = Image.new("L", size, 0)
    d = ImageDraw.Draw(img)
    for p in polygons:
        if len(p) >= 3:
            d.polygon(list(p), fill=1)
    return np.asarray(img, dtype=bool)


def find_trees(rgb: np.ndarray, geo: Georef, cell_id: str, buildings: Sequence[Mapping[str, Any]], features: Sequence[Mapping[str, Any]],
               cfg: Mapping[str, Any]) -> list[list[float]]:
    """[[x, z, crown diameter m], ...] in Studio studs for the trees whose trunk is inside the cell."""
    h, w = rgb.shape[:2]
    frame = layout.Frame.from_cfg(cfg)
    lat0 = float(h3.cell_to_latlng(cell_id)[0])
    mpp = geo.m_per_px(lat0)
    hexagon = [geo.to_px(*p) for p in h3.cell_to_boundary(cell_id)]
    # an underground car park or station is not a roof: the plaza over it keeps its trees (미관광장, 2026-10-14)
    covered = set(under_trees(rgb, geo, cell_id, buildings))  # empty records under the trees are not roofs either (1ab, 2026-10-14)
    roofs = _fill((w, h), [[geo.to_px(*p) for p in b["outline"]] for b in buildings
                           if not layout.is_underground(b) and b.get("building_id") not in covered])
    # a closed walk is a ring: its buffer has a hole, which must stay open (153, 2026-10-15: park loops filled 91 % of the cell)
    bands = [LineString([geo.to_px(*p) for p in f["geometry"]]).buffer(layout.road_width_m(f, cfg) / 2 / mpp)
             for f in features if len(f["geometry"]) >= 2]
    bands = [g for b in bands for g in getattr(b, "geoms", [b])]
    roads = _fill((w, h), [list(b.exterior.coords) for b in bands])
    holes = [list(r.coords) for b in bands for r in b.interiors]
    if holes:
        roads &= ~_fill((w, h), holes)
    canopy = canopy_mask(rgb) & ~ndi.binary_dilation(roofs, iterations=2)
    allowed = _fill((w, h), [hexagon]) & ~roofs & ~ndi.binary_dilation(roads, iterations=2)
    small = lambda a: a[: h // DOWN * DOWN, : w // DOWN * DOWN].reshape(h // DOWN, DOWN, w // DOWN, DOWN).mean(axis=(1, 3)) > 0.5
    trees = []
    for i, j, radius in pack_crowns(small(canopy), small(allowed), mpp * DOWN):
        lat, lon = geo.to_latlon((j + 0.5) * DOWN, (i + 0.5) * DOWN)
        x, z = layout.to_studs(frame, lat, lon)
        trees.append([round(x, 2), round(z, 2), round(2 * radius, 1)])
    return sorted(trees, key=lambda t: (t[1], t[0]))


UNDER_TREES = 0.6  # share of an outline the satellite shows as crowns


def bare(b: Mapping[str, Any]) -> bool:
    """A V-World record with nothing from the register: no floors, no use code, no floor area."""
    return not b.get("floors_above") and not (b.get("usability_code") or "") and not (b.get("building_area") or 0)


def under_trees(rgb: np.ndarray, geo: Georef, cell_id: str, buildings: Sequence[Mapping[str, Any]]) -> list[str]:
    """Ids of this cell's bare records whose outline the satellite shows at least UNDER_TREES covered by crowns: an outline left in a
    park or a green strip (1ab, 2026-10-14: 24 such records stood as default boxes among the trees). A roof hidden by a tree here
    and there stays (177: the bare records were real buildings when the satellite showed a roof)."""
    h, w = rgb.shape[:2]
    canopy = canopy_mask(rgb)
    out = []
    for b in buildings:
        if b.get("cell_id") != cell_id or not bare(b):
            continue
        m = _fill((w, h), [[geo.to_px(*p) for p in b["outline"]]])
        if m.sum() and canopy[m].mean() >= UNDER_TREES:
            out.append(str(b["building_id"]))
    return sorted(out)


def write_trees(cell_id: str, trees: Sequence[Sequence[float]], path: Path, covered: Sequence[str] = ()) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cell_id": cell_id, "source": f"V-World satellite z{ZOOM}", "count": len(trees), "trees": list(trees),
                                "under_trees": list(covered)}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    return path


def parse_args(argv: Sequence[str], res: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="trees.py", description=__doc__.split("\n")[0])
    parser.add_argument("--cells", nargs="+", metavar="ID", help="H3 cell IDs")
    parser.add_argument("--selftest", action="store_true", help="check that the libraries import; touches nothing")
    ns = parser.parse_args(list(argv))
    if ns.selftest:
        return ns
    if not ns.cells:
        parser.error("--cells is required (or use --selftest)")
    bad = [c for c in ns.cells if not (h3.is_valid_cell(c) and h3.get_resolution(c) == res)]
    if bad:
        parser.error(f"not valid resolution-{res} H3 cell IDs: {bad}")
    return ns


def main(cfg: dict[str, Any]) -> int:
    args = parse_args(sys.argv[1:], cfg["h3_res"])
    if args.selftest:
        print("selftest ok: h3, numpy, pillow, scipy and shapely import")
        return 0
    conn = db.connect(common.resolve(cfg["db_path"]))
    every = [r[0] for r in conn.execute("select cell_id from cells")]
    buildings, features = db.rows_in_cells(conn, "buildings", every), [f for f in db.rows_in_cells(conn, "street_features", every) if f["kind"] in ("road", "path")]
    for cell_id in args.cells:
        sat = common.resolve(SAT_DIR) / f"{cell_id}-z{ZOOM}"
        meta = json.loads(sat.with_suffix(".json").read_text(encoding="utf-8"))
        rgb = np.asarray(Image.open(sat.with_suffix(".jpg")).convert("RGB"))
        geo = Georef(int(meta["tile_x0"]), int(meta["tile_y0"]))
        trees = find_trees(rgb, geo, cell_id, buildings, features, cfg)
        path = write_trees(cell_id, trees, common.cell_file(cfg, cell_id, "trees"), under_trees(rgb, geo, cell_id, buildings))
        common.log(logging.INFO, f"trees written: {len(trees)} in {path}", cell_id)
    return 0


if __name__ == "__main__":
    common.run_cli(main, "trees")
