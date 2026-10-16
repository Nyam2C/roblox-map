# /// script
# requires-python = ">=3.11"
# dependencies = ["shapely==2.2.0"]
# ///
"""Buildings standing on a road: the building boxes of each cell's chunks.json against its road boxes (cycle-verify 3c, 2026-10-16).

Usage:
  uv run src/road_overlaps.py --cells <cell...>     # one line per cell: buildings overlapping a road by more than 0.3 m², worst first
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from shapely.geometry import Polygon
from shapely.strtree import STRtree

LIMIT_STUD2 = 4.0  # 0.3 m² at 3.6 studs/m: less is a corner touch


def rect(item: dict) -> Polygon:
    a = math.radians(item.get("r") or 0)
    c, s = math.cos(a), math.sin(a)
    w, d = item["w"] / 2, item["d"] / 2
    return Polygon([(item["x"] + u * c + v * s, item["z"] - u * s + v * c) for u, v in ((-w, -d), (w, -d), (w, d), (-w, d))])


def overlaps(chunks: dict) -> dict[str, float]:
    """building id -> largest overlap (studs²) of its boxes with the road boxes."""
    items = [i for ch in chunks["chunks"] for i in ch["items"]]
    roads = [rect(i) for i in items if i["k"] == "road"]
    tree = STRtree(roads)
    out: dict[str, float] = {}
    for b in items:
        if b["k"] != "building":
            continue
        p = rect(b)
        area = sum(p.intersection(roads[j]).area for j in tree.query(p))
        if area > LIMIT_STUD2:
            bid = b["n"].split("#")[0]
            out[bid] = max(out.get(bid, 0.0), area)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cells", nargs="+", required=True)
    ns = ap.parse_args(argv)
    total = 0
    for cell in ns.cells:
        found = overlaps(json.loads(Path(f"data/build/{cell}/chunks.json").read_text(encoding="utf-8")))
        total += len(found)
        worst = sorted(found.items(), key=lambda kv: -kv[1])[:5]
        print(cell, len(found), " ".join(f"{k}:{v / 12.96:.1f}m2" for k, v in worst))
    print("total", total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
