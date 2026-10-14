# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "numpy==2.5.4", "pillow==12.3.0", "scipy==1.18.1", "shapely==2.2.0"]
# ///
"""The colour of each building's top, read off the V-World satellite photo -> regions/<region>/cells/<cell>/roofs.json (kept in git).

Usage (repo root):
  uv run src/roofs.py --cells 8930e0af13bffff     # needs data/satellite/<cell>-z19.jpg and .json (satellite.py cell)
  uv run src/roofs.py --selftest

The flat-roof cap used the wall colour darkened, so a red-brick block got a red-brown top where the photo shows grey, white or green
waterproof paint (옥산초 gis:11201536, 2026-10-14; user decision: read it off the photo). Inside the footprint shrunk by 1.5 m (edges,
parapet shadows), without crowns, the median colour goes to the nearest of a few roof-top looks. Tall buildings lean in the photo, so
from 8 floors up the top is left to the rule or set by eye under "hand" (an outline overlay on the photo: 103's teal and brown
apartment decks, 2026-10-15). build_luau.py gives the look to the cap of a flat roof (details key roof_top).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Mapping, Sequence

import h3

import common
import db

SAT_DIR = "data/satellite"
SHRINK_M = 1.5
MIN_PX = 30
MAX_FLOORS = 7
# roof-top look -> the photo's colour of it (V-World z19, 2026-10-14 samples); Studio colours are in details_rules.PALETTE
SAT_LOOKS: dict[str, tuple[int, int, int]] = {
    "rtop_white": (215, 215, 210), "rtop_light": (175, 175, 172), "rtop_gray": (130, 130, 130), "rtop_dark": (75, 78, 82),
    "rtop_green": (110, 150, 115), "rtop_teal": (95, 165, 150), "rtop_brown": (140, 105, 85), "rtop_red": (170, 85, 70),
    "rtop_blue": (90, 120, 160),
}


def nearest_look(rgb: Sequence[float]) -> str:
    return min(SAT_LOOKS, key=lambda k: sum((float(a) - b) ** 2 for a, b in zip(rgb, SAT_LOOKS[k])))


def roof_looks(photo, geo, buildings: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """{building id: roof-top look} for the buildings whose shrunk footprint holds enough uncovered pixels."""
    import numpy as np
    from shapely.geometry import Polygon
    from trees import _fill, canopy_mask
    rgb = np.asarray(photo)
    h, w = rgb.shape[:2]
    crowns = canopy_mask(rgb)
    out: dict[str, str] = {}
    for b in buildings:
        if (b.get("floors_above") or 0) > MAX_FLOORS:
            continue
        lat0 = b["centroid"][0]
        mpp = geo.m_per_px(lat0)
        px = [geo.to_px(p[0], p[1]) for p in b["outline"]]
        if not all(0 <= x < w and 0 <= y < h for x, y in px):
            continue
        inner = Polygon(px).buffer(-SHRINK_M / mpp)
        if inner.is_empty or inner.geom_type != "Polygon":
            continue
        x0, y0, x1, y1 = (int(v) for v in inner.bounds)
        sub = (slice(max(y0, 0), min(y1 + 2, h)), slice(max(x0, 0), min(x1 + 2, w)))
        mask = _fill((sub[1].stop - sub[1].start, sub[0].stop - sub[0].start),
                     [[(x - sub[1].start, y - sub[0].start) for x, y in inner.exterior.coords]]) & ~crowns[sub]
        if mask.sum() < MIN_PX:
            continue
        out[str(b["building_id"])] = nearest_look(np.median(rgb[sub][mask], axis=0))
    return dict(sorted(out.items()))


def load_roofs(path) -> dict[str, str]:
    """A cell's roofs.json -> {building id: look}; none without the file. An unknown look refuses the build."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = {**data["roofs"], **data.get("hand", {})}  # hand: tall blocks set by eye on an outline overlay (they lean in the photo)
    bad = [k for k, v in rows.items() if v not in SAT_LOOKS]
    if bad:
        raise ValueError(f"{path.name}: unknown roof-top look for {bad[:3]}")
    return rows


def parse_args(argv: Sequence[str], res: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="roofs.py", description=__doc__.split("\n")[0])
    parser.add_argument("--cells", nargs="+", metavar="ID")
    parser.add_argument("--selftest", action="store_true")
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
        import numpy, PIL, scipy  # noqa: F401
        print("selftest ok")
        return 0
    from PIL import Image
    from trees import Georef
    conn = db.connect(common.resolve(cfg["db_path"]))
    for cell_id in args.cells:
        sat = common.resolve(SAT_DIR) / f"{cell_id}-z19"
        meta = json.loads(sat.with_suffix(".json").read_text(encoding="utf-8"))
        buildings = [b for b in db.rows_in_cells(conn, "buildings", [cell_id]) if b["status"] == "ok"]
        looks = roof_looks(Image.open(sat.with_suffix(".jpg")).convert("RGB"), Georef(int(meta["tile_x0"]), int(meta["tile_y0"])), buildings)
        path = common.cell_file(cfg, cell_id, "roofs")
        path.parent.mkdir(parents=True, exist_ok=True)
        hand = json.loads(path.read_text(encoding="utf-8")).get("hand", {}) if path.exists() else {}
        path.write_text(json.dumps({"cell_id": cell_id, "source": "V-World satellite z19", "roofs": looks, **({"hand": hand} if hand else {})},
                                   ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        counts: dict[str, int] = {}
        for v in looks.values():
            counts[v] = counts.get(v, 0) + 1
        common.log(logging.INFO, f"{len(looks)}/{len(buildings)} roof tops -> {path} {dict(sorted(counts.items()))}", cell_id)
    return 0


if __name__ == "__main__":
    common.run_cli(main, "roofs")
