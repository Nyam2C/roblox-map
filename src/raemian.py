# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""래미안 부천중동 (cells 8930e0af133ffff and 8930e0af1abffff) -> studio/manual/bucheon-dodang/Raemian.luau.

V-World cuts this complex into many pieces: one record per tower roof (named 래미안 부천 중동 / 10x동, with floors) plus tens of bare
fragments around them, and OSM adds three big outlines of its own. Judged one by one, the fragments became a crowd of 25-floor boxes
(user, 2026-10-15: "레미안 아파트는 너무 달라"). This builds the 7 towers of the site plan (KB부동산 complex photos: 7 dongs, 19-27
floors, 2015) from the tower records only and claims every other record on the site, so Auto builds none of them.
Look (street view crops of the tower records and the KB photos): slim white towers, a glass balcony band and a white slab per
floor on the long faces, gray striped narrow ends with the dong number, one coloured vertical strip per tower, a darker crown,
the one-storey shop rows with roof gardens along 신흥로276번길 stay Auto buildings.

Usage (repo root): uv run src/raemian.py   (then anchors.py script --name Raemian and execute_luau, as for the other Manual scripts)
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from shapely.geometry import Point, Polygon

import common
import layout
from plaza import lua_rows, strips

OUT = Path("studio/manual/bucheon-dodang/Raemian.luau")
TEMPLATE = Path(__file__).with_name("raemian_template.luau")
CELLS = ("8930e0af133ffff", "8930e0af1abffff")
# dong -> (tower record, accent colour key, shop podium); read off the site plan turned to north and the satellite roofs
TOWERS = {
    "101": ("gis:17106938", "yellow", False),
    "102": ("gis:15387193", "blue", False),
    "103": ("gis:17433421", "gray", False),
    "104": ("gis:17038144", "orange", False),
    "105": ("gis:17425176", "blue", False),
    "106": ("gis:15727778", "yellow", False),
    "107": ("gis:16118582", "pink", False),
}
# the site: north path, 정주로41번길 on the east, 신흥로276번길 on the south-west (studs)
SITE = Polygon([(-1345, -1800), (-695, -1800), (-695, -1170), (-1000, -1170), (-1345, -1450)])
FLOOR_M = 2.9
LONG = 30.0  # studs: a face at least this long is a balcony face, shorter ones are the striped ends


def claimed(rows, frame, seen) -> list[str]:
    """Every record on the site except the small houses with their own register data (the villas in the south-east corner) and the
    low shop podiums along the road that the photos counted (1-3 floors: real one-storey shop rows with roof gardens, kept in Auto)."""
    out = []
    for r in rows:
        if 1 <= (seen.get(r["building_id"]) or 0) <= 3:
            continue
        pts = [layout.to_studs(frame, *p) for p in json.loads(r["outline"])]
        if len(pts) < 3 or not SITE.contains(Polygon(pts).centroid):
            continue
        small_house = (r["usability_code"] or "") == "01000" and (r["floors_above"] or 0) <= 4
        if not small_house:
            out.append(str(r["building_id"]))
    return sorted(out)


def build() -> dict[str, list]:
    cfg = common.load_config()
    frame = layout.Frame.from_cfg(cfg)
    conn = sqlite3.connect(cfg["db_path"])
    conn.row_factory = sqlite3.Row
    rows = conn.execute("select * from buildings where cell_id in (?, ?)", CELLS).fetchall()
    by_id = {r["building_id"]: r for r in rows}
    seen = {k: v for k, v in conn.execute("select building_id, floors_seen from estimates where cell_id in (?, ?)", CELLS)}
    s = frame.studs_per_m
    towers, walls, body, roof = [], [], [], []
    for n, (dong, (bid, accent, podium)) in enumerate(TOWERS.items(), 1):
        r = by_id[bid]
        pts = [layout.to_studs(frame, *p) for p in json.loads(r["outline"])]
        shape = Polygon(pts).buffer(0).simplify(0.8)
        floors = int(r["floors_above"])
        top = round(floors * FLOOR_M * s, 2)
        towers.append((n, dong, floors, top, accent, 1 if podium else 0))
        ring = list(shape.exterior.coords)
        sign = 1 if shape.exterior.is_ccw else -1
        edges = []
        for p, q in zip(ring, ring[1:]):
            dx, dz = q[0] - p[0], q[1] - p[1]
            length = math.hypot(dx, dz)
            if length >= 0.5:
                edges.append((p, q, dx, dz, length))
        longest = max(e[4] for e in edges)
        for k, (p, q, dx, dz, length) in enumerate(edges):
            nx, nz = sign * dz / length, -sign * dx / length
            kind = 1 if length >= LONG else 2  # 1 balcony face, 2 striped end
            strip = 1 if length == longest else 0  # the coloured strip on the longest face
            walls.append((n, round((p[0] + q[0]) / 2, 2), round((p[1] + q[1]) / 2, 2), round(length + 0.4, 2),
                          round(math.degrees(math.atan2(-dz, dx)), 2), round(nx, 4), round(nz, 4), kind, strip))
        body += [(n,) + b for b in strips(shape.buffer(-2.5), 4.0)]
        roof += [(n,) + b for b in strips(shape.buffer(-0.6), 2.0)]
    return {"TOWERS": towers, "WALLS": walls, "BODY": body, "ROOF": roof,
            "CLAIMS": [(c,) for c in claimed(rows, frame, seen)]}


def render(data: dict[str, list]) -> str:
    head = "\n".join(f"local {k} = {{\n{lua_rows(v)}\n}}" for k, v in data.items())
    return TEMPLATE.read_text().replace("--[[DATA]]", head)


if __name__ == "__main__":
    data = build()
    assert len(data["TOWERS"]) == 7 and data["WALLS"]
    assert all(TOWERS[d][0] in {c[0] for c in data["CLAIMS"]} for d in TOWERS)  # every tower record steps aside in Auto
    OUT.write_text(render(data))
    print(OUT, {k: len(v) for k, v in data.items()})
