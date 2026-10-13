# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "pillow==12.3.0", "shapely==2.2.0"]
# ///
"""V-World satellite z19: the mosaic of one cell for trees.py, and the overlay of a straight-down Studio capture (U7 B).

Usage (repo root, VWORLD_KEY in .env):
  uv run --env-file .env src/satellite.py cell <cell>        # -> data/satellite/<cell>-z19.jpg and .json (tile_x0, tile_y0), then trees.py
  uv run --env-file .env src/satellite.py compare <studio capture.jpg> <centre x stud> <centre z stud> <px per stud> [out prefix]
      # -> <out>_side_by_side.jpg, _blend.jpg, _satellite.jpg (default prefix data/compare/now)
A capture from height 650 looking straight down with the default 70 degree field of view is 0.974 px per stud (1631 x 882 window).
Tiles are cached in data/satellite/tiles/ (git ignored).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

import h3
from PIL import Image, ImageDraw

import common
import layout

SAT_DIR = "data/satellite"
ZOOM = 19
PAD_DEG = 0.0008  # the mosaic covers the cell plus this margin


def tile_xy(lat: float, lon: float, zoom: int = ZOOM) -> tuple[float, float]:
    """Web mercator tile coordinates (fractional) of a point."""
    n = 2 ** zoom
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def fetch_tile(tx: int, ty: int, key: str) -> Path:
    cache = common.resolve(SAT_DIR) / "tiles" / f"{ZOOM}_{ty}_{tx}.jpeg"
    if not cache.exists():
        url = f"https://api.vworld.kr/req/wmts/1.0.0/{key}/Satellite/{ZOOM}/{ty}/{tx}.jpeg"
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "roblox-map/0"}), timeout=30) as r:
                    data = r.read()
                break
            except OSError as e:
                if attempt == 3:
                    raise RuntimeError(common.mask(f"satellite tile {ZOOM}/{ty}/{tx} failed: {e}")) from None
                time.sleep(5)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        time.sleep(0.1)
    return cache


def mosaic(tx0: int, tx1: int, ty0: int, ty1: int, key: str) -> Image.Image:
    img = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (40, 40, 40))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            img.paste(Image.open(fetch_tile(tx, ty, key)).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    return img


def cell_tiles(cell_id: str) -> tuple[int, int, int, int]:
    """The tile range (tx0, tx1, ty0, ty1) of the cell plus PAD_DEG."""
    ring = h3.cell_to_boundary(cell_id)
    x0, y1 = tile_xy(min(p[0] for p in ring) - PAD_DEG, min(p[1] for p in ring) - PAD_DEG)
    x1, y0 = tile_xy(max(p[0] for p in ring) + PAD_DEG, max(p[1] for p in ring) + PAD_DEG)
    return int(x0), int(x1), int(y0), int(y1)


def cell_mosaic(cell_id: str, key: str) -> Path:
    tx0, tx1, ty0, ty1 = cell_tiles(cell_id)
    out = common.resolve(SAT_DIR) / f"{cell_id}-z{ZOOM}"
    out.parent.mkdir(parents=True, exist_ok=True)
    mosaic(tx0, tx1, ty0, ty1, key).save(out.with_suffix(".jpg"), quality=92)
    out.with_suffix(".json").write_text(json.dumps({"tile_x0": tx0, "tile_y0": ty0, "zoom": ZOOM}), encoding="utf-8")
    return out.with_suffix(".jpg")


def capture_to_tile(frame: layout.Frame, size: tuple[int, int], cx: float, cz: float, ppx: float) -> Callable[[float, float], tuple[float, float]]:
    """Capture pixel -> fractional tile coordinates, for a straight-down capture centred on stud (cx, cz) at ppx px per stud (north up)."""
    w, h = size
    return lambda px, py: tile_xy(*layout.from_studs(frame, cx + (px - w / 2) / ppx, cz + (py - h / 2) / ppx))


def compare(capture: Path, cx: float, cz: float, ppx: float, out: str, cfg: dict[str, Any], key: str) -> None:
    cap = Image.open(capture).convert("RGB")
    w, h = cap.size
    to_tile = capture_to_tile(layout.Frame.from_cfg(cfg), (w, h), cx, cz, ppx)
    corners = [to_tile(px, py) for px in (0, w) for py in (0, h)]
    tx0, ty0 = int(min(c[0] for c in corners)), int(min(c[1] for c in corners))
    tiles = mosaic(tx0, int(max(c[0] for c in corners)), ty0, int(max(c[1] for c in corners)), key)

    def src(px: float, py: float) -> tuple[float, float]:
        x, y = to_tile(px, py)
        return (x - tx0) * 256, (y - ty0) * 256
    # affine to well under a pixel over 1 km: fit it from three corners and let PIL resample
    (x00, y00), (x10, y10), (x01, y01) = src(0, 0), src(w, 0), src(0, h)
    sat = tiles.transform((w, h), Image.AFFINE, ((x10 - x00) / w, (x01 - x00) / h, x00, (y10 - y00) / w, (y01 - y00) / h, y00), Image.BICUBIC)
    side = Image.new("RGB", (w * 2 + 10, h), (255, 255, 255))
    side.paste(sat, (0, 0))
    side.paste(cap, (w + 10, 0))
    d = ImageDraw.Draw(side)
    d.text((10, 10), "V-World satellite z19", fill=(255, 255, 0))
    d.text((w + 20, 10), "Studio top view (same area, north up)", fill=(255, 255, 0))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    side.save(f"{out}_side_by_side.jpg", quality=88)
    Image.blend(sat, cap, 0.5).save(f"{out}_blend.jpg", quality=88)
    sat.save(f"{out}_satellite.jpg", quality=88)


def main(cfg: dict[str, Any]) -> int:
    parser = argparse.ArgumentParser(prog="satellite.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("cell")
    c.add_argument("cell")
    m = sub.add_parser("compare")
    m.add_argument("capture", type=Path)
    m.add_argument("cx", type=float)
    m.add_argument("cz", type=float)
    m.add_argument("ppx", type=float)
    m.add_argument("out", nargs="?", default="data/compare/now")
    args = parser.parse_args(sys.argv[1:])
    key = common.get_secret("VWORLD_KEY")
    if args.command == "cell":
        if not (h3.is_valid_cell(args.cell) and h3.get_resolution(args.cell) == cfg["h3_res"]):
            parser.error(f"not a resolution-{cfg['h3_res']} H3 cell id")
        common.log(logging.INFO, f"mosaic written: {cell_mosaic(args.cell, key)}", args.cell)
    else:
        compare(args.capture, args.cx, args.cz, args.ppx, args.out, cfg, key)
        common.log(logging.INFO, f"written: {args.out}_side_by_side.jpg, _blend.jpg, _satellite.jpg")
    return 0


if __name__ == "__main__":
    common.run_cli(main, "satellite")
