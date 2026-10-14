# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""The department store with the round corner (gis:11740143, cell 8930e0af10fffff) -> studio/manual/bucheon-dodang/DeptStore.luau.

The Auto box split stairs the north-east corner, which is a quarter-circle drum (9 of the 15 outline points, satellite and street
view 2026-10-14). This builds the store from its own outline instead: the arc points are fitted with a circle and walked every
few studs, so the drum is smooth. Look from street view (crops toward the drum, 25-110 m): light stone panels with a joint every
floor, a tall blue glass curtain over the east end of the drum and a glass bay on the long faces, a dark two-floor glass base with
stone piers under a canopy on the drum and the plaza (south) face, a flat roof with plant boxes. Height and floors come from the
anchors (anchors.json, the Auto values), so a new box split or a height fix moves nothing by hand. The Manual model carries
BuildingId, so the Auto building and everything it owns step aside.

Usage (repo root): uv run src/deptstore.py   (then anchors.py script --name DeptStore and execute_luau, as for the other Manual scripts)
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from shapely.geometry import Polygon

import common
import layout
from plaza import lua_rows, strips

BID = "gis:11740143"
FLOORS = 11
OUT = Path("studio/manual/bucheon-dodang/DeptStore.luau")
TEMPLATE = Path(__file__).with_name("deptstore_template.luau")
ARC_FIRST, ARC_LAST = 6, 15  # outline indexes of the drum (index 15 wraps to 0)
STEP = 6.0                   # studs between points on the drum
GLASS_ARC = (0.0, 0.42)      # share of the drum, from its east end, under the tall glass curtain
BAY_ARC = (0.55, 0.68)       # a narrower glass block in the middle of the drum (floors 5-9)


def circle_fit(pts):
    """Least-squares circle (cx, cz, r) through the points (Kasa)."""
    n = len(pts)
    sx = sum(p[0] for p in pts); sz = sum(p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts); szz = sum(p[1] ** 2 for p in pts); sxz = sum(p[0] * p[1] for p in pts)
    sr = [p[0] ** 2 + p[1] ** 2 for p in pts]
    a = [[sxx, sxz, sx], [sxz, szz, sz], [sx, sz, n]]
    b = [sum(r * p[0] for r, p in zip(sr, pts)), sum(r * p[1] for r, p in zip(sr, pts)), sum(sr)]
    # Cramer's rule on the 3 x 3 system
    det = lambda m: (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                     + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    d = det(a)
    sol = []
    for k in range(3):
        m = [row[:] for row in a]
        for i in range(3):
            m[i][k] = b[i]
        sol.append(det(m) / d)
    cx, cz = sol[0] / 2, sol[1] / 2
    return cx, cz, math.sqrt(sol[2] + cx ** 2 + cz ** 2)


def outline_studs():
    cfg = common.load_config()
    frame = layout.Frame.from_cfg(cfg)
    conn = sqlite3.connect(cfg["db_path"])
    pts = [layout.to_studs(frame, *p) for p in json.loads(conn.execute("select outline from buildings where building_id=?", (BID,)).fetchone()[0])]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def footprint():
    """The outline with the drum walked on its fitted circle; returns (points, arc flags per edge, share along the drum per edge)."""
    pts = outline_studs()
    arc = [pts[i % len(pts)] for i in range(ARC_FIRST, ARC_LAST + 1)]
    cx, cz, r = circle_fit(arc)
    a0 = math.atan2(arc[0][1] - cz, arc[0][0] - cx)
    a1 = math.atan2(arc[-1][1] - cz, arc[-1][0] - cx)
    if a1 < a0:
        a1 += 2 * math.pi
    n = max(2, int(r * (a1 - a0) / STEP))
    walked = [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cz + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]
    straight = [pts[i] for i in range(1, ARC_FIRST)]  # from after the drum's end (index 0) to before its start
    poly = straight + walked
    # edges: poly[i] -> poly[i+1]; the drum's edges are those between walked points
    flags, share = [], []
    m = len(straight)
    for i in range(len(poly)):
        on_arc = m <= i < len(poly) - 1
        flags.append(on_arc)
        share.append(1 - (i - m + 0.5) / n if on_arc else -1)  # 0 at the drum's east end
    return poly, flags, share, (cx, cz, r)


def build() -> dict[str, list]:
    poly, flags, share, _ = footprint()
    anchors = json.loads(Path("studio/manual/bucheon-dodang/anchors.json").read_text())
    a = anchors.get(BID) or anchors["buildings"][BID]
    top = round(a["top"], 2)
    shape = Polygon(poly)
    assert shape.is_valid
    sign = 1 if shape.exterior.is_ccw else -1
    walls = []
    for i, (p, q) in enumerate(zip(poly, poly[1:] + poly[:1])):
        dx, dz = q[0] - p[0], q[1] - p[1]
        length = math.hypot(dx, dz)
        if length < 0.3:
            continue
        nx, nz = sign * dz / length, -sign * dx / length  # outward normal
        s = share[i]
        if flags[i]:
            kind = 1 if GLASS_ARC[0] <= s <= GLASS_ARC[1] else 2 if BAY_ARC[0] <= s <= BAY_ARC[1] else 0
            base = 1  # shop base on the drum
        else:
            kind = 3 if length > 120 else 0  # a glass bay in the middle of a long face
            base = 1 if nz > 0.7 else 0  # the plaza (south) face
        piers = (1 if i % 4 == 0 else 0) if flags[i] else max(1, int(length // 24))  # a pier every ~24 studs on the base
        walls.append((round((p[0] + q[0]) / 2, 3), round((p[1] + q[1]) / 2, 3), round(length + 0.35, 3),
                      round(math.degrees(math.atan2(-dz, dx)), 3), round(nx, 4), round(nz, 4), kind, base, piers))
    out = {"HEAD": [(top, FLOORS)], "WALLS": walls, "BODY": strips(shape.buffer(-4.0), 4.0), "ROOF": strips(shape.buffer(-0.8), 2.0)}  # well inside: band corners must not poke through the shop glass
    roof = shape.buffer(-14)
    cx, cz = roof.centroid.x, roof.centroid.y
    out["ROOFTOP"] = [(round(cx + dx, 2), round(cz + dz, 2), w, d, h) for dx, dz, w, d, h in
                      ((-60, -10, 34, 22, 10), (10, 15, 26, 18, 8), (70, -5, 40, 16, 6)) if roof.contains(Polygon([(cx + dx, cz + dz), (cx + dx + 1, cz + dz), (cx + dx, cz + dz + 1)]))]
    return out


def render(data: dict[str, list]) -> str:
    head = "\n".join(f"local {k} = {{\n{lua_rows(v)}\n}}" for k, v in data.items())
    return TEMPLATE.read_text().replace("--[[DATA]]", head).replace("--[[BID]]", BID)


if __name__ == "__main__":
    data = build()
    assert data["WALLS"] and data["BODY"]
    OUT.write_text(render(data))
    print(OUT, {k: len(v) for k, v in data.items()}, "drum edges", sum(1 for w in data["WALLS"] if w[7] and w[6] != 3))
