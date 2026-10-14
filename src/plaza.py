# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""미관광장 (the plaza south of the department store, cell 8930e0af10fffff) -> studio/manual/bucheon-dodang/Plaza.luau.

The shapes are read off the V-World z19 satellite photo on a stud grid (2026-10-14); the look follows street-view crops and the
user's photos: light granite pavers with brown accent tiles, raised planters of dark split-face block holding grasses, small
conifers and white stone balls, a stepped oval of dark stone, tree beds behind a low granite curb, a diagonal row of white
columns with tall brown poles, glass escalator pavilions to the underground mall and car park. The trees are not here: they come
from the satellite crowns of the cell (trees.json). The plaza is the underground car park's outline (V-World gis:16759296, not
built) less the roads and sidewalks the cell already has.

Usage (repo root): uv run src/plaza.py   (then anchors.py script --name Plaza and execute_luau, as for the other Manual scripts)
"""
from __future__ import annotations

import json
import math
import sqlite3
import zlib
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

import common
import layout
import minimap

OUT = Path("studio/manual/bucheon-dodang/Plaza.luau")
CAR_PARK = "gis:16759296"
CELLS = ("8930e0af10fffff", "8930e0af173ffff", "8930e0af177ffff")
PAVE = 0.38  # paving top: just under the sidewalks (top 0.4)

# outlines in studs (x, z), traced on the satellite grid; smoothed with Chaikin
BEDS = {  # raised planters (dark block wall, planted)
    "west": [(-1593, 838), (-1586, 826), (-1572, 821), (-1558, 823), (-1548, 832), (-1556, 846), (-1562, 864), (-1585, 850)],
    "middle": [(-1470, 845), (-1460, 836), (-1440, 835), (-1420, 838), (-1402, 850), (-1390, 866), (-1384, 880), (-1392, 891),
               (-1410, 893), (-1440, 890), (-1462, 880), (-1475, 862)],
    "north_east": [(-1405, 812), (-1396, 801), (-1376, 797), (-1354, 801), (-1342, 812), (-1347, 830), (-1370, 840), (-1395, 831)],
}
TERRACE = [(-1555, 858), (-1548, 845), (-1535, 840), (-1490, 840), (-1481, 850), (-1481, 872), (-1487, 880), (-1500, 882),
           (-1530, 876), (-1550, 866)]  # the dark stepped oval
GROVES = {  # tree beds (lawn behind a low curb)
    "north_west": [(-1605, 782), (-1448, 782), (-1445, 805), (-1452, 825), (-1466, 833), (-1490, 837), (-1530, 836), (-1546, 829),
                   (-1556, 818), (-1575, 812), (-1595, 805), (-1606, 797)],
    "south": [(-1588, 898), (-1560, 886), (-1520, 895), (-1490, 902), (-1470, 897), (-1440, 896), (-1412, 899), (-1400, 912),
              (-1405, 935), (-1655, 940), (-1655, 900)],
    "east": [(-1336, 788), (-1270, 788), (-1268, 905), (-1300, 912), (-1340, 905), (-1357, 890), (-1362, 862), (-1350, 846),
             (-1338, 836), (-1333, 812)],
}
COLUMNS = [(-1427, 816), (-1415, 825), (-1405, 832), (-1395, 840), (-1385, 850), (-1375, 857), (-1367, 867), (-1360, 882)]
POLES = [(-1452, 791, 26), (-1446, 798, 31), (-1438, 792, 23)]  # tall brown sculpture posts by the store side
# pavilions: centre x, z, width (x), depth (z), height, door side ("E" +x, "N" -z ...), sign text, roof colour key
PAVILIONS = [
    (-1621.5, 823.5, 19, 27, 12, "E", "지하주차장", "teal"),
    (-1616, 881, 52, 32, 15, "N", "미관광장 지하상가", "brown"),
    (-1335, 824, 8, 20, 10, "W", "", "teal"),
]
KIOSK = (-1491, 809.5, 18, 7, 9)  # the red-roofed shelter in the north-west trees


def chaikin(pts: list[tuple[float, float]], n: int = 2) -> list[tuple[float, float]]:
    for _ in range(n):
        out = []
        for i, a in enumerate(pts):
            b = pts[(i + 1) % len(pts)]
            out += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        pts = out
    return pts


def strips(poly, step: float) -> list[tuple[float, float, float, float]]:
    """Axis-aligned boxes (cx, cz, w, d) filling the polygon in bands of `step` along z, cut at each band's middle line."""
    out = []
    if poly.is_empty:
        return out
    x0, z0, x1, z1 = poly.bounds
    z = z0
    while z < z1:
        mid = min(z + step / 2, z1 - 1e-6)
        cut = poly.intersection(LineString([(x0 - 1, mid), (x1 + 1, mid)]))
        for seg in getattr(cut, "geoms", [cut]):
            if seg.is_empty or seg.length < 0.5:
                continue
            a, b = seg.bounds[0], seg.bounds[2]
            out.append((round((a + b) / 2, 2), round(z + step / 2, 2), round(b - a, 2), step))
        z += step
    return out


def ring(poly) -> list[tuple[float, float, float, float]]:
    """Wall pieces (cx, cz, length, yaw) along the outline; yaw as the item rule (local X along the piece)."""
    pts = list(poly.exterior.coords)
    out = []
    for a, b in zip(pts, pts[1:]):
        dx, dz = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dz)
        if length < 0.2:
            continue
        out.append((round((a[0] + b[0]) / 2, 2), round((a[1] + b[1]) / 2, 2), round(length + 0.5, 2), round(math.degrees(math.atan2(-dz, dx)), 2)))
    return out


def rnd(*key) -> float:
    return zlib.crc32("|".join(map(str, key)).encode()) / 2**32


def scatter(poly, step: float, name: str) -> list[tuple[float, float, int, float]]:
    """Jittered grid points inside the polygon: (x, z, kind 0..4, size 0..1). Kinds: 0 grass, 1 white ball, 2 conifer, 3 flower, 4 none."""
    x0, z0, x1, z1 = poly.bounds
    out = []
    i = 0
    z = z0 + step / 2
    while z < z1:
        x = x0 + step / 2
        while x < x1:
            jx, jz = x + (rnd(name, i, "x") - 0.5) * step * 0.8, z + (rnd(name, i, "z") - 0.5) * step * 0.8
            if poly.buffer(-1.2).contains(Point(jx, jz)):
                r = rnd(name, i, "k")
                kind = 0 if r < 0.5 else 1 if r < 0.54 else 2 if r < 0.66 else 3 if r < 0.8 else 4
                if kind != 4:
                    out.append((round(jx, 2), round(jz, 2), kind, round(rnd(name, i, "s"), 2)))
            i += 1
            x += step
        z += step
    return out


def plaza_area(conn, cfg) -> Polygon:
    frame = layout.Frame.from_cfg(cfg)
    outline = json.loads(conn.execute("select outline from buildings where building_id=?", (CAR_PARK,)).fetchone()[0])
    # the car park sits a few metres inside the block: grow it to the sidewalks, then cut the roads and sidewalks out
    area = Polygon([layout.to_studs(frame, *p) for p in outline]).buffer(30, join_style=2)
    taken = []
    for cell in CELLS:
        data = json.loads(Path(f"data/build/{cell}/chunks.json").read_text())
        for ch in data["chunks"]:
            for it in ch["items"]:
                if it["k"] in ("road", "sidewalk"):
                    taken.append(Polygon(minimap.corners([0, it["x"], it["z"], it["w"], it["d"], it.get("r", 0)])))
    rest = area.difference(unary_union(taken)).buffer(-0.05)
    parts = sorted(getattr(rest, "geoms", [rest]), key=lambda g: -g.area)
    return parts[0]  # the block itself; slivers beyond the sidewalks are dropped


def lua_rows(rows) -> str:
    return ",\n".join("\t{" + ", ".join(f'"{v}"' if isinstance(v, str) else f"{v:g}" for v in r) + "}" for r in rows)


def build() -> dict[str, list]:
    cfg = common.load_config()
    conn = sqlite3.connect(cfg["db_path"])
    area = plaza_area(conn, cfg)
    beds = {k: Polygon(chaikin(v)).buffer(0) for k, v in BEDS.items()}
    terrace = Polygon(chaikin(TERRACE)).buffer(0)
    groves = {k: Polygon(chaikin(v)).intersection(area) for k, v in GROVES.items()}
    pav = [Polygon([(x - w / 2, z - d / 2), (x + w / 2, z - d / 2), (x + w / 2, z + d / 2), (x - w / 2, z + d / 2)])
           for x, z, w, d, *_ in PAVILIONS]
    solid = unary_union(list(beds.values()) + [terrace] + list(groves.values()) + pav)
    paved = area.difference(solid)
    out: dict[str, list] = {"PAVERS": strips(area, 0.8)}  # thin bands: a coarse band shows a saw edge on the diagonal side
    out["PAVE_EDGE"] = [w for part in getattr(area, "geoms", [area]) for w in ring(part)]  # a straight border hides the band ends
    out["BED_FILL"] = [s for k in beds for s in strips(beds[k].buffer(-0.3), 0.6)]  # thin bands so the soil meets the curved wall
    out["BED_WALL"] = [w for k in beds for w in ring(beds[k])]
    tiers = [terrace, terrace.buffer(-5), terrace.buffer(-10)]
    out["TERRACE"] = [s + (n,) for n, t in enumerate(tiers) if not t.is_empty for s in strips(t.buffer(-0.8), 1.5)]
    out["TERRACE_EDGE"] = [w + (n,) for n, t in enumerate(tiers) if not t.is_empty for w in ring(t)]  # smooth curved step fronts
    out["GROVE_FILL"] = [s for g in groves.values() for s in strips(g.buffer(-0.6), 2.0)]
    out["GROVE_CURB"] = [w for g in groves.values() for part in getattr(g, "geoms", [g]) for w in ring(part)]
    out["PLANTS"] = [p for k in ("west", "middle") for p in scatter(beds[k], 3.2, k)] + \
                    [(x, z, 0 if kind != 1 else 1, s) for x, z, kind, s in scatter(beds["north_east"], 3.6, "north_east")]
    tiles, i = [], 0
    x0, z0, x1, z1 = paved.bounds
    inner = paved.buffer(-1.5)
    while len(tiles) < 220 and i < 30000:  # brown accent tiles scattered in the pavers
        x, z = x0 + rnd("t", i, "x") * (x1 - x0), z0 + rnd("t", i, "z") * (z1 - z0)
        if inner.contains(Point(x, z)):
            tiles.append((round(x / 1.8) * 1.8, round(z / 1.8) * 1.8))
        i += 1
    out["ACCENT"] = sorted(set(tiles))
    lamps = []
    for gx in range(-1640, -1270, 26):
        for gz in range(790, 935, 26):
            if paved.buffer(-4).contains(Point(gx, gz)) and all(math.dist((gx, gz), c) > 8 for c in COLUMNS):
                lamps.append((gx, gz))
    out["LAMPS"] = lamps
    out["COLUMNS"] = COLUMNS
    out["POLES"] = POLES
    out["PAVILIONS"] = PAVILIONS
    out["KIOSK"] = [KIOSK]
    return out


TEMPLATE = Path(__file__).with_name("plaza_template.luau")


def render(data: dict[str, list]) -> str:
    head = "\n".join(f"local {k} = {{\n{lua_rows(v)}\n}}" for k, v in data.items())
    return TEMPLATE.read_text().replace("--[[DATA]]", head)


if __name__ == "__main__":
    data = build()
    assert data["PAVERS"] and data["BED_WALL"] and len(data["COLUMNS"]) == 8
    OUT.write_text(render(data))
    print(OUT, {k: len(v) for k, v in data.items()}, "parts ~", sum(len(v) for v in data.values()))
