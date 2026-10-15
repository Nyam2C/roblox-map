"""세이브존 상동점 in cell 8930e0af0b3ffff (user-approved 2026-10-16, "세이브존은 좀 더 신경써서"), one V-World record
(gis:11177019). Called by facilities.build for the spec whose "custom" is "savezone". No brand lettering or logo anywhere.

Look from the three street-view crops and the satellite:
- Walls: light blue-grey square panels (grout grid) with a salmon line every second floor, a pale parapet band.
- SW corner (길주로 x 상동로): a full-height blue-green glass cylinder with metal rings and mullions, a dark drum over the roof
  with a white open ring on top; flag poles and pines on the corner plaza.
- South (길주로): a dark charcoal full-height strip with two yellow lines; east of it the floors show dark window bands; two
  narrow banner boards and a big one near the rotunda (no text).
- North: glass shop floors 1-2, a black stone portal three floors tall with a louvre grille and an orange band over the doors,
  an olive awning shop west of it, two dark louvre strips up the wall, three banner boards (no text).
- Roof: dark olive west part, lighter grey east part with plant units.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from shapely.affinity import rotate
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient

import layout_details as LD
from layout import Box, Frame, Item

FLOORS, H = 10, 46.0
FH = H / FLOORS
PANEL = (196, 204, 212)
JOINT = (176, 184, 192)
SALMON = (214, 122, 92)
GLASS = (78, 107, 123)
CHAR = (58, 58, 60)
YELLOW = (222, 178, 40)
DARK = (40, 40, 42)


def corner_circle(poly: Polygon) -> tuple[float, float, float]:
    """The rounded corner of the outline: a circle fitted (Kasa) to the run of short edges (< 4 m)."""
    cs = list(poly.exterior.coords)[:-1]
    n = len(cs)
    short = [i for i in range(n) if math.dist(cs[i], cs[(i + 1) % n]) < 4.0]
    pts = sorted({cs[i] for i in short} | {cs[(i + 1) % n] for i in short})
    a = np.array(pts)
    A = np.c_[a, np.ones(len(a))]
    (d, e, f), *_ = np.linalg.lstsq(A, -(a ** 2).sum(1), rcond=None)
    cx, cy = -d / 2, -e / 2
    return float(cx), float(cy), float(math.sqrt(max(cx * cx + cy * cy - f, 1.0)))


def fill(poly, step: float) -> list[tuple[float, float, float, float]]:
    """Boxes (cx, cz, w, d) filling the polygon in bands of `step` along z, each clipped to the polygon's own extent in the band
    (plaza.strips keeps the full band depth, which overhangs a wall along x by up to `step` and buries its details)."""
    out = []
    if poly.is_empty:
        return out
    x0, z0, x1, z1 = poly.bounds
    z = z0
    while z < z1 - 1e-6:
        band = poly.intersection(Polygon([(x0 - 1, z), (x1 + 1, z), (x1 + 1, z + step), (x0 - 1, z + step)]))
        for g in getattr(band, "geoms", [band]):
            if g.geom_type != "Polygon" or g.area < 0.05:
                continue
            mid = g.intersection(LineString([(x0 - 1, (g.bounds[1] + g.bounds[3]) / 2), (x1 + 1, (g.bounds[1] + g.bounds[3]) / 2)]))
            a, b = (mid.bounds[0], mid.bounds[2]) if not mid.is_empty else (g.bounds[0], g.bounds[2])
            out.append(((a + b) / 2, (g.bounds[1] + g.bounds[3]) / 2, b - a, g.bounds[3] - g.bounds[1]))
        z += step
    return out


def build(frame: Frame, bid: str, poly: Polygon) -> list[Item]:
    items: list[Item] = []

    def put(kind: str, tail: str, e: float, n: float, y: float, size, rgb, yaw: float = 0.0, **extra: Any) -> None:
        extra = {"material": "SmoothPlastic", **extra}
        items.append(LD._part(frame, kind, f"{bid}#{tail}-{len(items)}", bid, len(items), e, n, y, size, yaw,
                              owner=bid, color=tuple(rgb), color_name=None, **extra))

    def on(tail: str, bx: Box, u: float, v: float, y: float, size, rgb, **extra: Any) -> None:
        v += math.copysign(0.12, v) if v else 0.0  # clear of the mass strips' 1 m steps on the faces off the fill frame
        e, n = LD._world(bx, u, v)
        put("facade", tail, e, n, y, size, rgb, bx.yaw_deg, **extra)

    body = orient(poly, 1.0)
    cx, cy, R = corner_circle(body)
    R = max(R, 8.0)
    rot = Point(cx, cy).buffer(R, 32)
    mass = body.difference(rot)

    # the mass, filled in the building's own frame (straight walls)
    r = list(body.minimum_rotated_rectangle.exterior.coords)
    turn = math.degrees(math.atan2(r[1][1] - r[0][1], r[1][0] - r[0][0]))
    c0 = body.centroid
    for x, z, w, d in fill(rotate(mass, -turn, origin=c0), 1.0):  # 1 m: the bay by the rotunda runs 9 degrees off this frame
        q = rotate(Point(x, z), turn, origin=c0)                      # and 4 m strips buried its face details
        put("building", "m", q.x, q.y, 0.0, (w, H, d), PANEL, turn, collide=True)

    # the faces: every outline edge of 4 m or more outside the rotunda, with its compass side
    faces = []
    cs = list(body.exterior.coords)
    for (x0, y0), (x1, y1) in zip(cs, cs[1:]):
        L = math.dist((x0, y0), (x1, y1))
        if L < 4.0 or rot.buffer(0.5).contains(Point((x0 + x1) / 2, (y0 + y1) / 2)):
            continue
        bx = Box((x0 + x1) / 2, (y0 + y1) / 2, L, 1.0, math.degrees(math.atan2(y1 - y0, x1 - x0)), 1.0)
        ne, nn = LD._world(bx, 0.0, 2.0)
        s = -1.0 if body.contains(Point(ne, nn)) else 1.0  # +v outward?
        nx, ny = (ne - bx.cx_m) / 2 * s, (nn - bx.cy_m) / 2 * s
        side = "N" if ny > 0.7 else "S" if ny < -0.7 else "E" if nx > 0.7 else "W"
        faces.append((side, bx, s, L, (x0, y0), (x1, y1)))

    def at(face, frac: float) -> float:
        """u along the face for a fraction from its west end (north end on E/W faces)."""
        side, bx, _, L, a, b = face
        first = a if (a[0] < b[0] if side in "NS" else a[1] > b[1]) else b
        e = first[0] + (b[0] + a[0] - 2 * first[0]) * frac
        n = first[1] + (b[1] + a[1] - 2 * first[1]) * frac
        t = (math.cos(math.radians(bx.yaw_deg)), math.sin(math.radians(bx.yaw_deg)))
        return (e - bx.cx_m) * t[0] + (n - bx.cy_m) * t[1]

    for side, bx, s, L, _, _ in faces:
        for j in range(1, int(L // 2.4)):  # panel grid: vertical joints
            on("jv", bx, -L / 2 + j * 2.4, s * 0.06, 2 * FH, (0.08, H - 2 * FH - 1.2, 0.1), JOINT)
        for k in range(4, 2 * FLOORS):  # horizontal joints every half floor above the shop floors
            if k % 4:
                on("jh", bx, 0.0, s * 0.06, k * FH / 2, (L, 0.08, 0.1), JOINT)
        for f in (3, 5, 7, 9):  # salmon line every second floor
            on("sl", bx, 0.0, s * 0.1, f * FH, (L + 0.1, 0.25, 0.14), SALMON)
        on("pb", bx, 0.0, s * 0.1, H - 1.2, (L + 0.2, 1.2, 0.3), (226, 230, 232))  # parapet band

    def longest(side):
        fs = [f for f in faces if f[0] == side]
        return max(fs, key=lambda f: f[3]) if fs else None

    south, north = longest("S"), longest("N")
    if south:
        _, bx, s, L, _, _ = south
        u = at(south, 0.55)
        on("ds", bx, u, s * 0.2, 0.0, (6.0, H + 0.5, 0.4), CHAR)  # the charcoal strip with two yellow lines
        for du in (-1.0, 1.0):
            on("dy", bx, u + du, s * 0.42, 2 * FH, (0.5, H - 2 * FH, 0.1), YELLOW)
        u2 = at(south, 1.0)
        u1 = u + math.copysign(3.5, u2 - u)
        for f in range(2, FLOORS):  # the east part: dark window bands
            on("wb", bx, (u1 + u2) / 2, s * 0.1, f * FH + 1.3, (abs(u2 - u1) - 1.0, 1.6, 0.12), (52, 64, 76), material="Glass")
        on("sg", bx, 0.0, s * 0.15, 0.0, (L - 1.0, 2 * FH - 0.4, 0.2), GLASS, material="Glass")  # glass shop floors
        on("sf", bx, 0.0, s * 0.3, 2 * FH - 0.6, (L, 0.6, 0.3), (226, 230, 232))
        for f, w, rgb in ((0.18, 2.6, (38, 52, 140)), (0.30, 2.6, (38, 52, 140))):  # narrow banner boards (no text)
            on("bn", bx, at(south, f), s * 0.25, 4 * FH, (w, 4 * FH, 0.15), rgb)
    for fs in [f for f in faces if f[0] == "S" and f is not south][:1]:  # the bay by the rotunda: a big banner board
        _, bx, s, L, _, _ = fs
        on("bb", bx, 0.0, s * 0.25, 3 * FH + 1.0, (min(10.0, L - 4.0), 3 * FH, 0.2), (40, 56, 150))
        on("sg", bx, 0.0, s * 0.15, 0.0, (L - 1.0, 2 * FH - 0.4, 0.2), GLASS, material="Glass")
    if north:
        _, bx, s, L, _, _ = north
        on("ng", bx, at(north, 0.35), s * 0.15, 0.0, (L * 0.5, 2 * FH - 0.4, 0.2), GLASS, material="Glass")
        for j in range(int(L * 0.5 // 3.0) + 1):  # its mullions, by fraction: +u may run either way along the face
            on("nm", bx, at(north, 0.10 + j * 3.0 / L), s * 0.3, 0.0, (0.2, 2 * FH - 0.4, 0.2), (226, 230, 232))
        on("aw", bx, at(north, 0.22), s * 1.2, FH - 0.8, (12.0, 0.4, 2.4), (96, 104, 60), material="Fabric")  # olive awning
        u = at(north, 0.6)
        on("pt", bx, u, s * 0.4, 0.0, (9.0, 3 * FH, 0.8), DARK, material="Marble", reflectance=0.15)  # the black portal
        on("pd", bx, u, s * 0.85, 0.0, (5.0, 3.2, 0.1), (70, 80, 90), material="Glass", transparency=0.3)  # doors
        on("po", bx, u, s * 0.85, 3.4, (7.0, 2.2, 0.15), (235, 95, 45))  # the orange band (colour only)
        for k in range(8):  # the louvre grille above it
            on("pl", bx, u, s * 0.86, 5.8 + k * 0.85, (7.0, 0.18, 0.3), (120, 124, 128), material="Metal")
        for f in (0.10, 0.22):  # two dark louvre strips up the wall
            on("ls", bx, at(north, f), s * 0.12, 2 * FH, (2.4, H - 2 * FH - 1.5, 0.15), (92, 94, 96), material="Metal")
        for f, w, h, rgb in ((0.40, 2.8, 4, (38, 52, 140)), (0.52, 7.0, 3, (230, 110, 70)), (0.68, 2.8, 4, (38, 52, 140))):
            on("bn", bx, at(north, f), s * 0.25, 4 * FH, (w, h * FH, 0.15), rgb)

    # the rotunda: glass drum, rings, mullions, the drum over the roof and its open white ring
    put("building", "rg", cx, cy, 0.0, (H, 2 * R, 2 * R), GLASS, shape="Cylinder", material="Glass", reflectance=0.2, collide=True)
    for k in range(1, int(H / 4.0)):
        put("facade", "rr", cx, cy, k * 4.0 - 0.15, (0.3, 2 * R + 0.8, 2 * R + 0.8), (200, 206, 212), shape="Cylinder", material="Metal")
    m = int(2 * math.pi * R / 2.0)
    for j in range(m):
        a = 2 * math.pi * j / m
        put("facade", "rm", cx + math.cos(a) * (R + 0.05), cy + math.sin(a) * (R + 0.05), 0.0, (0.15, H, 0.25), (190, 196, 202),
            -math.degrees(a), material="Metal")
    put("facade", "rd", cx, cy, H, (4.0, 2 * R, 2 * R), (106, 107, 108), shape="Cylinder", material="Metal")
    put("facade", "rt", cx, cy, H + 4.0, (0.25, 2 * R, 2 * R), (235, 236, 236), shape="Cylinder")
    put("facade", "rw", cx, cy, H + 4.1, (0.25, 2 * R - 5.4, 2 * R - 5.4), (40, 42, 44), shape="Cylinder")
    for a in (0.0, 90.0):  # two crossing beams over the open ring
        put("facade", "rx", cx, cy, H + 4.3, (2 * R - 4.0, 0.4, 0.5), (235, 236, 236), a)

    # flag poles on the corner plaza, outward from the rotunda
    ox, oy = cx - c0.x, cy - c0.y
    k = math.hypot(ox, oy) or 1.0
    ox, oy = ox / k, oy / k
    for j, rgb in enumerate(((235, 235, 235), (200, 40, 50), (40, 70, 160))):
        a = math.atan2(oy, ox) + (j - 1) * 0.35
        e, n = cx + math.cos(a) * (R + 7.0), cy + math.sin(a) * (R + 7.0)
        put("facade", "fp", e, n, 0.0, (12.0, 0.2, 0.2), (210, 212, 214), shape="Cylinder", material="Metal")
        put("facade", "ff", e + 0.9, n, 9.6, (1.6, 1.1, 0.05), rgb, math.degrees(a), material="Fabric")

    # roof: dark olive west part, light grey east part with plant units, over the mass top
    x0, _, x1, _ = mass.bounds
    split = x0 + (x1 - x0) * 0.6
    for tail, part, rgb in (("rw", mass.intersection(Polygon([(x0 - 1, -1e6), (split, -1e6), (split, 1e6), (x0 - 1, 1e6)])), (83, 90, 74)),
                            ("re", mass.intersection(Polygon([(split, -1e6), (x1 + 1, -1e6), (x1 + 1, 1e6), (split, 1e6)])), (150, 152, 140))):
        for x, z, w, d in fill(rotate(part.buffer(-0.3), -turn, origin=c0), 2.0):
            q = rotate(Point(x, z), turn, origin=c0)
            put("facade", tail + "t", q.x, q.y, H - 0.05, (w, 0.15, d), rgb, turn)
    east = mass.intersection(Polygon([(split, -1e6), (x1 + 1, -1e6), (x1 + 1, 1e6), (split, 1e6)])).buffer(-4.0)
    if not east.is_empty:
        bx0, by0, bx1, by1 = east.bounds
        for i in range(10):
            e = bx0 + (bx1 - bx0) * ((i * 37 + 11) % 100) / 100
            n = by0 + (by1 - by0) * ((i * 61 + 23) % 100) / 100
            if east.contains(Point(e, n)):
                put("facade", "ac", e, n, H, (2.4, 1.6, 1.6), (205, 206, 208), turn, material="Metal")
    return items
