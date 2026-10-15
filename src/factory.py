"""The big factory in cell 8930e0af1a7ffff (user-approved 2026-10-15), one V-World record (gis:11195602). Called by
facilities.build for the spec whose "custom" is "factory". No company name anywhere.

Look from the street-view crops and the satellite:
- Walls: windowless pale grey metal panels with salmon pin-stripes every floor and a gold band near the top.
- Mass: a lower ring round a taller core; corner service towers carry stacked gold fins.
- Roof: a row of cooling towers in blue frames and white tanks along the west edge, plant boxes on the core.
- East front: a two-column portico with a flat canopy over a glass lobby.
"""
from __future__ import annotations

import math
from typing import Any

from shapely.affinity import rotate
from shapely.geometry import Point, Polygon
from shapely.geometry.polygon import orient

import layout_details as LD
from layout import Box, Frame, Item
from plaza import strips

RING_H, CORE_H, TOWER_H = 22.0, 30.0, 34.0
PANEL = (220, 220, 224)
PINK = (215, 140, 130)
GOLD = (205, 165, 85)


def build(frame: Frame, bid: str, poly: Polygon) -> list[Item]:
    items: list[Item] = []

    def put(kind: str, tail: str, e: float, n: float, y: float, size, rgb, yaw: float = 0.0, **extra: Any) -> None:
        extra = {"material": "SmoothPlastic", **extra}
        items.append(LD._part(frame, kind, f"{bid}#{tail}-{len(items)}", bid, len(items), e, n, y, size, yaw,
                              owner=bid, color=tuple(rgb), color_name=None, **extra))

    def on(tail: str, bx: Box, u: float, v: float, y: float, size, rgb, **extra: Any) -> None:
        e, n = LD._world(bx, u, v)
        put("facade", tail, e, n, y, size, rgb, bx.yaw_deg, **extra)

    body = orient(poly, 1.0)
    core = body.buffer(-10.0, join_style=2)
    r = list(body.minimum_rotated_rectangle.exterior.coords)
    turn = math.degrees(math.atan2(r[1][1] - r[0][1], r[1][0] - r[0][0]))  # fill in the building's own frame: no 4 m steps on its walls
    c0 = body.centroid
    for tail, p, y0, h in (("m", body, 0.0, RING_H), ("c", core, RING_H, CORE_H - RING_H)):
        for x, z, w, d in strips(rotate(p, -turn, origin=c0), 4.0):
            q = rotate(Point(x, z), turn, origin=c0)
            put("building", tail, q.x, q.y, y0, (w, h, d), PANEL, turn, material="Metal", collide=True)

    def faces(p: Polygon, y0: float, y1: float, tag: str) -> None:
        cs = list(p.exterior.coords)
        for (x0, y_0), (x1, y_1) in zip(cs, cs[1:]):
            L = math.dist((x0, y_0), (x1, y_1))
            if L < 4.0:
                continue
            bx = Box((x0 + x1) / 2, (y_0 + y_1) / 2, L, 1.0, math.degrees(math.atan2(y_1 - y_0, x1 - x0)), 1.0)
            ne, nn = LD._world(bx, 0.0, 2.0)
            s = -1.0 if p.contains(Point(ne, nn)) else 1.0  # +v points outward?
            for k in range(1, int((y1 - y0) / 4.0) + 1):  # salmon pin-stripes every floor
                on(tag + "s", bx, 0.0, s * 0.08, y0 + k * 4.0 - 0.15, (L, 0.15, 0.12), PINK)
            on(tag + "g", bx, 0.0, s * 0.12, y1 - 2.2, (L, 0.9, 0.2), GOLD)
            for j in range(1, int(L // 6.0)):  # panel joints
                on(tag + "j", bx, -L / 2 + j * 6.0, s * 0.06, y0, (0.12, y1 - y0, 0.1), (196, 196, 200))
            on(tag + "l", bx, 0.0, s * 0.1, y0 + 8.0, (L * 0.8, 2.0, 0.15), (150, 152, 156), material="Metal")  # louvre band

    faces(body, 0.0, RING_H, "r")
    faces(core, RING_H, CORE_H, "k")

    # corner service towers with stacked gold fins, on the corners of the ring
    rect = body.minimum_rotated_rectangle
    corners = list(rect.exterior.coords)[:4]
    c = body.centroid
    for i, (x, y) in enumerate(corners):
        tx, ty = x + (c.x - x) * 0.06, y + (c.y - y) * 0.06
        put("building", "t", tx, ty, 0.0, (9.0, TOWER_H, 9.0), (200, 200, 204), material="Metal", collide=True)
        for k in range(4):
            put("facade", "tf", tx, ty, 12.0 + k * 5.0, (10.2, 0.5, 10.2), GOLD)

    # roof plant: cooling towers (two rows) and white tanks along the west edge of the core
    rc = list(core.minimum_rotated_rectangle.exterior.coords)[:4]
    edges = [(rc[i], rc[(i + 1) % 4]) for i in range(4)]
    (ax, ay), (bx_, by_) = min(edges, key=lambda e: (e[0][0] + e[1][0]))
    L = math.dist((ax, ay), (bx_, by_))
    west = Box((ax + bx_) / 2, (ay + by_) / 2, L, 1.0, math.degrees(math.atan2(by_ - ay, bx_ - ax)), 1.0)
    inward = 1.0 if core.contains(Point(*LD._world(west, 0.0, 3.0))) else -1.0
    for k in range(int((L - 6.0) // 6.0)):
        u = -L / 2 + 6.0 + k * 6.0
        for row, v in enumerate((5.0, 11.0)):
            e, n = LD._world(west, u, inward * v)
            put("facade", "cf", e, n, CORE_H, (5.2, 3.2, 5.2), (70, 110, 170), west.yaw_deg, material="Metal")
            put("facade", "ct", e, n, CORE_H + 3.2, (0.6, 4.4, 4.4), (180, 184, 188), shape="Cylinder", material="Metal")
        if k % 2 == 0:
            e, n = LD._world(west, u, inward * 17.0)
            put("facade", "tk", e, n, CORE_H, (6.0, 3.4, 3.4), (240, 240, 238), shape="Cylinder")
    for i in range(6):  # plant boxes on the core
        p = core.buffer(-12.0)
        if p.is_empty:
            break
        x0, y0, x1, y1 = p.bounds
        e, n = x0 + (x1 - x0) * ((i * 37) % 100) / 100, y0 + (y1 - y0) * ((i * 61 + 20) % 100) / 100
        if p.contains(Point(e, n)):
            put("facade", "pb", e, n, CORE_H, (7.0, 3.0, 5.0), (205, 206, 208), material="Metal")

    # east portico: two square columns and a flat canopy with a gold edge over a glass lobby
    (ex, ey), (fx, fy) = max([(rect.exterior.coords[i], rect.exterior.coords[i + 1]) for i in range(4)],
                             key=lambda e: e[0][0] + e[1][0])
    L = math.dist((ex, ey), (fx, fy))
    east = Box((ex + fx) / 2, (ey + fy) / 2, L, 1.0, math.degrees(math.atan2(fy - ey, fx - ex)), 1.0)
    out = -1.0 if body.contains(Point(*LD._world(east, 0.0, 3.0))) else 1.0
    for u in (-5.0, 5.0):
        on("pc", east, u, out * 6.0, 0.0, (1.4, 8.0, 1.4), (150, 152, 156), material="Concrete", collide=True)
    on("pk", east, 0.0, out * 3.5, 8.0, (14.0, 1.2, 8.0), (205, 205, 208), material="Concrete")
    on("pe", east, 0.0, out * 7.5, 8.0, (14.2, 0.3, 0.2), GOLD)
    on("pg", east, 0.0, out * 0.2, 0.0, (10.0, 6.0, 0.3), (80, 95, 110), material="Glass", transparency=0.2)
    return items
