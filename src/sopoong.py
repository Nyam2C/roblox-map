"""부천종합터미널 소풍 (cell 8930e0af0a3ffff, user-approved 2026-10-15): the bus terminal and shopping centre, one V-World record
(gis:12062576, 9 floors, 52 m). Called by facilities.build for the spec whose "custom" is "sopoong".

Look from the namu.wiki photos (viewed only, 2026-10-15) and the satellite (regions/bucheon-dodang/sopoong.json):
- North front, on 길주로: a glass rotunda with floor rings, a disc crown, a ring of columns and a red ring canopy over the door.
- A curved wing sweeps from the rotunda down the east side, with beige terraces stepping round it.
- East face, on the big road: a two-tone beige checkerboard of stone panels around a glass curtain atrium.
- Top of the east face: a grey metal upper floor, and the tall hall box at the south end, white on top with the name.
- Roof: a green glass skylight in the north half, solar glass in the middle, the hall's dark roof in the south.
- West side (street view): pale tiled walls with small square windows, silver panelled parking floors with open slots, and the
  bus bays under long teal glass canopies on green posts.
- A glass-tube footbridge on Y pylons crosses the big road east to 안중근공원.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from shapely.geometry import LineString, Point, Polygon, box as rect
from shapely.affinity import translate
from shapely.geometry.polygon import orient

import layout
import layout_details as LD
from anjunggeun import to_latlon
from layout import Box, Frame, Item
from plaza import strips

LAYOUT = Path("regions/bucheon-dodang/sopoong.json")
MASS_H = 34.0       # the mall floors (photos: the checker block and the rotunda reach the same height)
UPPER_H = 42.0      # the grey metal upper floor over the middle
STONE = (214, 198, 172)
STONE_DARK = (184, 160, 128)
GLASS = dict(material="Glass", transparency=0.25, reflectance=0.25)
SKY = (120, 160, 175)
METAL = (205, 208, 210)
GREY = (118, 120, 124)
WHITE = (232, 232, 228)


def build(frame: Frame, bid: str, poly: Polygon) -> list[Item]:
    data = json.loads(LAYOUT.read_text(encoding="utf-8"))
    tx, ty = int(data["tile_x0"]), int(data["tile_y0"])
    ox, oy = data["offset"]
    items: list[Item] = []

    def m(p) -> tuple[float, float]:
        return layout.to_meters(frame, *to_latlon(tx, ty, ox + p[0], oy + p[1]))

    def rect_m(r) -> Polygon:
        (x0, y0), (x1, y1) = m(r[0]), m(r[1])
        return rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def put(group: str, kind: str, tail: str, e: float, n: float, y: float, size, rgb, yaw: float = 0.0, **extra: Any) -> None:
        extra = {"material": "SmoothPlastic", **extra}
        items.append(LD._part(frame, kind, f"{group}#{tail}-{len(items)}", group, len(items), e, n, y, size, yaw,
                              owner=group, color=tuple(rgb), color_name=None, **extra))

    def on(group: str, kind: str, tail: str, bx: Box, u: float, v: float, y: float, size, rgb, yaw_add: float = 0.0, **extra: Any) -> None:
        e, n = LD._world(bx, u, v)
        put(group, kind, tail, e, n, y, size, rgb, bx.yaw_deg + yaw_add, **extra)

    rot = data["rotunda"]
    rc = Point(m(rot["px"]))
    R, RH = float(rot["r_m"]), float(rot["height_m"])
    arc = LineString([m(p) for p in data["arc"]["px"]])
    hall = rect_m(data["hall"]["px"]).intersection(poly)
    sky = rect_m(data["skylight"]["px"]).intersection(poly)
    solar = rect_m(data["solar"]["px"]).intersection(poly)
    body = orient(poly.difference(rc.buffer(R + 2.5)), 1.0)  # the outline traces the ring (about 11 m): no mass in front of the glass
    if body.geom_type != "Polygon":
        body = max(body.geoms, key=lambda g: g.area)

    # mass: the mall floors, then the grey upper floor over the middle and the tall hall box
    for x, z, w, d in strips(body, 4.0):
        put(bid, "building", "m", x, z, 0.0, (w, MASS_H, d), STONE, collide=True)
    upper = body.buffer(-9.0).intersection(rect(*solar.bounds).union(rect(*hall.bounds)).envelope).difference(hall)
    for x, z, w, d in strips(upper, 4.0):
        put(bid, "facade", "up", x, z, MASS_H, (w, UPPER_H - MASS_H, d), GREY, material="Metal")
    for x, z, w, d in strips(hall, 4.0):
        put(bid, "building", "hl", x, z, MASS_H, (w, 52.0 - MASS_H, d), WHITE, material="Concrete", collide=True)
    for x, z, w, d in strips(sky, 4.0):  # the green glass skylight
        put(bid, "facade", "sk", x, z, MASS_H, (w, 6.0, d), (95, 140, 120), **GLASS)
    for x, z, w, d in strips(solar.buffer(-1.0), 4.0):
        put(bid, "facade", "so", x, z, UPPER_H, (w, 0.3, d), (40, 60, 90), material="Glass", reflectance=0.3)
    for x, z, w, d in strips(rect_m(data["white_roof"]["px"]).intersection(body).buffer(-0.5), 4.0):
        put(bid, "facade", "wr", x, z, MASS_H, (w, 0.15, d), WHITE)
    for x, z, w, d in strips(hall.buffer(-0.8), 4.0):
        put(bid, "facade", "hr", x, z, 52.0, (w, 0.2, d), (64, 74, 70))

    # faces of the mass, edge by edge: the compass side picks the look
    coords = list(body.exterior.coords)
    for i in range(len(coords) - 1):
        (x0, y0), (x1, y1) = coords[i], coords[i + 1]
        L = math.dist((x0, y0), (x1, y1))
        if L < 4.0:
            continue
        bx = Box((x0 + x1) / 2, (y0 + y1) / 2, L, 1.0, math.degrees(math.atan2(y1 - y0, x1 - x0)), 1.0)
        nx, ny = LD._world(bx, 0.0, 1.0)
        s = 1.0 if body.contains(Point(bx.cx_m + (nx - bx.cx_m) * -2.0, bx.cy_m + (ny - bx.cy_m) * -2.0)) else -1.0  # +v outward?
        oe, on_ = (nx - bx.cx_m) * s, (ny - bx.cy_m) * s
        comp = ("E" if oe > 0 else "W") if abs(oe) > abs(on_) else ("N" if on_ > 0 else "S")
        near_arc = arc.distance(Point(bx.cx_m, bx.cy_m)) < 9.0
        face = lambda tail, u, y, size, rgb, **ex: on(bid, "facade", tail, bx, u, s * (0.5 + size[2] / 2 - 0.5), y, size, rgb, **ex)
        # ground floor: dark shop glass between stone piers, a canopy band
        face("gf", 0.0, 0.0, (L, 5.6, 0.25), (52, 62, 70), material="Glass", reflectance=0.2)
        for k in range(int(L // 8.0) + 1):
            face("gp", -L / 2 + min(L, k * 8.0), 0.0, (0.9, 5.6, 0.6), STONE_DARK)
        face("gc", 0.0, 5.6, (L, 0.6, 1.4), WHITE)
        face("cp", 0.0, MASS_H - 0.4, (L + 0.3, 1.0, 0.7), WHITE)  # parapet cap
        if near_arc or comp == "N":  # the curved wing and the north front: glass behind beige terraces
            face("cg", 0.0, 6.2, (L, MASS_H - 7.0, 0.2), SKY, **GLASS)
            for k in range(1, 6):
                face("tr", 0.0, 6.2 + k * 4.8, (L + 0.2, 0.5, 2.4 if k % 2 else 1.4), STONE)
                face("tg", 0.0, 6.7 + k * 4.8, (L, 1.0, 2.3 if k % 2 else 1.3), METAL, material="Glass", transparency=0.5)
        elif comp in ("E", "S"):  # two-tone checker panels (4 x 3.4 m), the long east face gets a glass curtain atrium
            curtain = comp == "E" and L > 60.0
            for c in range(int(L // 4.0)):
                u = -L / 2 + 4.0 * (c + 0.5) + (L - int(L // 4.0) * 4.0) / 2
                if curtain and abs(u) < 14.0:
                    continue
                for r in range(8):
                    if (c + r) % 2:
                        face("ck", u, 6.2 + r * 3.4, (4.0, 3.4, 0.15), STONE_DARK, material="Sandstone")
            for r in range(1, 9):
                face("cj", 0.0, 6.2 + r * 3.4, (L, 0.12, 0.2), (236, 230, 216))
            if curtain:
                face("ag", 0.0, 6.2, (28.0, 20.4, 0.25), SKY, **GLASS)
                for k in range(12):
                    face("am", -14.0 + k * 28.0 / 11, 6.2, (0.18, 20.4, 0.35), METAL, material="Metal")
                for r in range(1, 6):
                    face("ah", 0.0, 6.2 + r * 3.4, (28.0, 0.25, 0.4), METAL, material="Metal")
        elif bx.cy_m > body.centroid.y:  # the bus side, north half: silver panelled parking floors with open dark slots
            face("pk", 0.0, 6.2, (L, MASS_H - 7.0, 0.2), (196, 202, 208), material="Metal")
            for r in range(4):
                face("ps", 0.0, 9.0 + r * 6.0, (L * 0.92, 1.8, 0.3), (40, 44, 48))
        else:  # the bus side, south half: pale tiled wall with small square windows
            for c in range(int(L // 7.0)):
                for r in range(4):
                    face("sw", -L / 2 + 7.0 * (c + 0.5) + (L - int(L // 7.0) * 7.0) / 2 + (r % 2) * 1.5, 9.0 + r * 6.0, (0.8, 0.8, 0.15),
                         (90, 130, 140), material="Glass")
    # the grey upper floor's ribbon window and the hall's name on its east face
    hx0, hy0, hx1, hy1 = hall.bounds
    for k, (e, n0, n1) in enumerate(((hx1, hy0, hy1),)):
        hb = Box(e + 0.2, (n0 + n1) / 2, n1 - n0, 1.0, 90.0, 1.0)  # local X runs north along the east face, +v is east
        on(bid, "facade", "hg", hb, 0.0, 0.0, 37.0, (n1 - n0 - 2.0, 3.0, 0.3), (60, 80, 95), material="Glass")
        on(bid, "facade", "hm", hb, 0.0, 0.0, MASS_H, (n1 - n0, 2.6, 0.35), GREY, material="Metal")
        name = LD._part(frame, "sign", f"{bid}#nm-{len(items)}", bid, len(items), *LD._world(hb, 0.0, 0.5), 45.0, (26.0, 4.5, 0.3),
                        hb.yaw_deg + 180.0, owner=bid, color=WHITE, color_name=None, material="SmoothPlastic", text="부천터미널",
                        faces="F", attrs={"MaxDistance": 600, "Ink": [40, 70, 60]})
        items.append(name)

    # the rotunda: glass drum, floor rings, column ring and red canopy at the door, a disc crown
    g = bid
    put(g, "building", "rd", rc.x, rc.y, 0.0, (RH, 2 * R, 2 * R), SKY, shape="Cylinder", collide=True, **GLASS)
    for k in range(1, int(RH / 4.8) + 1):
        put(g, "facade", "rr", rc.x, rc.y, 6.0 + (k - 1) * 4.8, (0.5, 2 * R + 0.6, 2 * R + 0.6), METAL, shape="Cylinder", material="Metal")
    for k in range(10):
        a = 2 * math.pi * k / 10
        put(g, "facade", "rp", rc.x + math.cos(a) * (R + 1.6), rc.y + math.sin(a) * (R + 1.6), 0.0, (6.0, 0.9, 0.9), STONE, shape="Cylinder")
    put(g, "facade", "rc", rc.x, rc.y, 6.0, (0.7, 2 * R + 6.0, 2 * R + 6.0), (190, 50, 45), shape="Cylinder")
    put(g, "facade", "rk", rc.x, rc.y, RH, (1.3, 2 * R + 5.0, 2 * R + 5.0), WHITE, shape="Cylinder")
    put(g, "facade", "rt", rc.x, rc.y, RH + 1.3, (1.6, 2 * R + 2.0, 2 * R + 2.0), METAL, shape="Cylinder", material="Metal")
    put(g, "facade", "ru", rc.x, rc.y, RH + 2.9, (0.4, 2 * R + 3.0, 2 * R + 3.0), WHITE, shape="Cylinder")
    # the curved wing's white roof edge, segment by segment
    wing = list(arc.coords)
    for (x0, y0), (x1, y1) in zip(wing, wing[1:]):
        L = math.dist((x0, y0), (x1, y1))
        bx = Box((x0 + x1) / 2, (y0 + y1) / 2, L, 1.0, math.degrees(math.atan2(y1 - y0, x1 - x0)), 1.0)
        on(bid, "facade", "aw", bx, 0.0, 0.0, MASS_H, (L + 1.5, 2.2, float(data["arc"]["width_m"])), WHITE)

    # the bus bays west of the building: glass barrel canopies on posts
    for b in data["bays"]:
        r = rect_m(b["px"])
        for _ in range(30):  # the satellite leans the roof over the canopies: slide them west off the outline
            if not r.intersects(poly.buffer(1.5)):
                break
            r = translate(r, -1.0, 0.0)
        x0, y0, x1, y1 = r.bounds
        bx = Box((x0 + x1) / 2, (y0 + y1) / 2, y1 - y0, x1 - x0, 90.0, 1.0)
        w = x1 - x0
        half = w / 2 + 0.3
        for side, yaw in ((-1, 0.0), (1, 180.0)):
            on("sopoong-bays", "prop", "bw", bx, 0.0, side * half / 2, 5.0, (bx.width_m, 1.4, half), (80, 140, 125), yaw, **GLASS)
        for k in range(int(bx.width_m // 6.0) + 1):
            u = -bx.width_m / 2 + min(bx.width_m, k * 6.0)
            for sv in (-1, 1):
                on("sopoong-bays", "prop", "bp", bx, u, sv * (w / 2), 0.0, (0.35, 5.0, 0.35), (50, 90, 75), material="Metal", collide=True)
            on("sopoong-bays", "prop", "bb", bx, u, 0.0, 4.8, (0.3, 0.3, w + 0.6), (50, 90, 75), material="Metal")

    # the footbridge: deck, glass sides, a glass pitched roof on white ribs, Y pylons
    br = data["bridge"]
    path = [m(p) for p in br["px"]]
    W, D = float(br["width_m"]), float(br["deck_m"])
    line = LineString(path)
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        L = math.dist((x0, y0), (x1, y1))
        bx = Box((x0 + x1) / 2, (y0 + y1) / 2, L, W, math.degrees(math.atan2(y1 - y0, x1 - x0)), 1.0)
        on("sopoong-bridge", "prop", "dk", bx, 0.0, 0.0, D, (L + 0.2, 0.7, W), (170, 168, 162), material="Concrete", collide=True)
        for sv in (-1, 1):
            on("sopoong-bridge", "prop", "sd", bx, 0.0, sv * (W / 2 - 0.1), D + 0.7, (L, 2.6, 0.15), (200, 222, 228), **GLASS)
        for side, yaw in ((-1, 0.0), (1, 180.0)):
            on("sopoong-bridge", "prop", "rf", bx, 0.0, side * W / 4, D + 3.3, (L, 1.3, W / 2), (200, 222, 228), yaw, **GLASS)
        for k in range(int(L // 3.5) + 1):
            u = -L / 2 + min(L, k * 3.5)
            for sv in (-1, 1):
                on("sopoong-bridge", "prop", "ib", bx, u, sv * W / 2, D + 0.7, (0.2, 2.6, 0.2), WHITE, material="Metal")
            on("sopoong-bridge", "prop", "it", bx, u, 0.0, D + 3.3, (0.2, 0.2, W + 0.2), WHITE, material="Metal")
    for f in br["pylons"]:
        p = line.interpolate(float(f), normalized=True)
        q = line.interpolate(min(1.0, float(f) + 0.02), normalized=True)
        bx = Box(p.x, p.y, 1.0, 1.0, math.degrees(math.atan2(q.y - p.y, q.x - p.x)), 1.0)
        on("sopoong-bridge", "prop", "py", bx, 0.0, 0.0, 0.0, (1.4, D - 2.5, 1.4), (226, 196, 120), collide=True)
        for side, yaw in ((-1, 180.0), (1, 0.0)):  # the fork: high at the deck edges, down to the column
            on("sopoong-bridge", "prop", "pf", bx, 0.0, side * W / 4, D - 2.5, (1.2, 2.5, W / 2), (226, 196, 120), yaw)
    return items
