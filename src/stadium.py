"""부천종합운동장 주경기장 (cell 8930e0ac0d3ffff, user request 2026-10-16 "부천종합운동장 가려면" → "ㄱㄱ"): one V-World record
(gis:15389663, an oval about 271 x 220 m, long axis N-S). Called by facilities.build for the spec whose "custom" is "stadium".

Look from the Wikimedia Commons photos (viewed only, 2026-10-16: Bucheon_Stadium.JPG from 원미산, Bucheon_Stadium_Paranoma.jpg from the
stands) and namu.wiki: a 400 m 8-lane red track round a natural-grass pitch (110 x 70 m); one continuous bowl of blue seats all
round; an oval roof ring over the stands only, grey metal with solar panels (962 kW, 2018); white concrete buttress columns round
the outside; floodlight masts standing behind the stands.
"""
from __future__ import annotations

import math
from typing import Any

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon

import layout_details as LD
from layout import Frame, Item
from plaza import ring, strips

STRAIGHT = 84.39    # m, the track's straights (IAAF 400 m)
R_TRACK_IN = 36.5   # m, the inner kerb radius
R_TRACK_OUT = 46.3  # m, 8 lanes of 1.22 m
FIELD_GAP = 6.0     # m from the track to the first row
STEP = 4.0          # m, depth of one band of seats
RISE = 1.4          # m, rise of one band
ROOF_Y = 24.0       # m, the roof ring's height at its outer edge
ROOF_IN = 26.0      # m, how far the roof reaches in from the outer wall
WHITE = (232, 232, 226)
SEAT = (44, 86, 168)
SEAT_LIGHT = (96, 150, 206)
TRACK = (186, 74, 58)
GRASS = (70, 138, 62)
PITCH = (84, 156, 70)
ROOF = (160, 164, 168)
SOLAR = (40, 46, 58)
APRON = (62, 112, 172)  # the blue apron round the track and the blue jogging ring outside (satellite)
CONCOURSE = (176, 150, 122)
RED_SEAT = (178, 52, 58)  # the east straight's red seats with BUCHEON in white (satellite)


def capsule(c: Point, yaw: float, straight: float, r: float) -> Polygon:
    """A running-track shape: a straight of `straight` along the long axis (yaw degrees from east), round ends of radius r."""
    line = LineString([(c.x - straight / 2, c.y), (c.x + straight / 2, c.y)])
    return affinity.rotate(line.buffer(r, quad_segs=24), yaw, origin=c)


def axis(poly: Polygon) -> float:
    """Direction (degrees from east) of the outline's long side."""
    pts = list(poly.minimum_rotated_rectangle.exterior.coords)
    sides = [(math.dist(pts[i], pts[i + 1]), pts[i], pts[i + 1]) for i in range(2)]
    _, a, b = max(sides)
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def ring_m(poly) -> list[tuple[float, float, float, float]]:
    """plaza.ring for a polygon in metres (north up): the item yaw is then the maths angle, plaza's is for Studio x, z (south up)."""
    return [(x, n, length, -wyaw) for x, n, length, wyaw in ring(poly)]


def build(frame: Frame, bid: str, poly: Polygon) -> list[Item]:
    items: list[Item] = []
    c = poly.centroid
    yaw = axis(poly)

    def put(kind: str, tail: str, e: float, n: float, y: float, size, rgb, yaw_deg: float = 0.0, **extra: Any) -> None:
        extra = {"material": "SmoothPlastic", **extra}
        items.append(LD._part(frame, kind, f"{bid}#{tail}-{len(items)}", bid, len(items), e, n, y, size, yaw_deg,
                              owner=bid, color=tuple(rgb), color_name=None, **extra))

    def fill(kind: str, tail: str, shape, y: float, h: float, rgb, step: float = STEP, **extra: Any) -> None:
        for x, z, w, d in strips(shape, step):
            put(kind, tail, x, z, y, (w, h, d), rgb, **extra)

    def loop(kind: str, tail: str, line_shape, depth: float, y: float, h: float, rgb, **extra: Any) -> None:
        """Pieces along a closed curve (plaza.ring), `depth` across it: smooth round ends where strips step out (Studio 2026-10-16)."""
        for x, z, length, wyaw in ring_m(line_shape):
            put(kind, tail, x, z, y, (length, h, depth), rgb, wyaw, **extra)

    # the field: blue apron under all, grass a little past the kerb, the red track ring on top, the pitch with its lines
    track_in = capsule(c, yaw, STRAIGHT, R_TRACK_IN)
    edge = capsule(c, yaw, STRAIGHT, R_TRACK_OUT + FIELD_GAP)
    fill("facade", "ap", edge.buffer(STEP).intersection(poly), 0.0, 0.16, APRON, material="Plaster", collide=True)
    fill("facade", "gr", track_in.buffer(2.0), 0.0, 0.18, GRASS, collide=True)
    loop("facade", "tk", capsule(c, yaw, STRAIGHT, (R_TRACK_IN + R_TRACK_OUT) / 2), R_TRACK_OUT - R_TRACK_IN, 0.0, 0.2, TRACK,
         material="Plaster", collide=True)
    ry = yaw  # in metres the item yaw is the maths angle (ring_m)
    put("facade", "pt", c.x, c.y, 0.18, (105.0, 0.04, 68.0), PITCH, ry)
    for su in (-1, 1):
        e, n = c.x + math.cos(math.radians(yaw)) * su * 52.5, c.y + math.sin(math.radians(yaw)) * su * 52.5
        put("prop", "tl", e, n, 0.22, (0.15, 0.02, 68.0), WHITE, ry)
        e, n = c.x - math.sin(math.radians(yaw)) * su * 34.0, c.y + math.cos(math.radians(yaw)) * su * 34.0
        put("prop", "sl", e, n, 0.22, (105.0, 0.02, 0.15), WHITE, ry)
    put("prop", "hw", c.x, c.y, 0.22, (0.15, 0.02, 68.0), WHITE, ry)
    put("prop", "cc", c.x, c.y, 0.22, (0.02, 18.3, 18.3), WHITE, 0.0, shape="Cylinder")  # a flat white disc for the centre circle
    put("prop", "cg", c.x, c.y, 0.23, (0.02, 17.9, 17.9), PITCH, 0.0, shape="Cylinder")

    # the bowl: rings of seats rising outward from the track to the white back wall, blue with a lighter ring every third row
    stands = poly.buffer(-1.2)  # pieces stay inside the back wall
    a = math.radians(yaw)
    east = (math.cos(a - math.pi / 2), math.sin(a - math.pi / 2))  # the side to the right of the long axis
    if east[0] < 0:
        east = (-east[0], -east[1])
    straight = LineString([(c.x - math.cos(a) * STRAIGHT / 2, c.y - math.sin(a) * STRAIGHT / 2),
                           (c.x + math.cos(a) * STRAIGHT / 2, c.y + math.sin(a) * STRAIGHT / 2)])
    red_zone = affinity.translate(straight, east[0] * 80.0, east[1] * 80.0).buffer(80.0, cap_style=2)
    k = 0
    while True:
        mid = capsule(c, yaw, STRAIGHT, R_TRACK_OUT + FIELD_GAP + (k + 0.5) * STEP)
        top = 1.2 + k * RISE
        rgb = SEAT_LIGHT if k % 3 == 2 else SEAT
        made = 0
        for x, z, length, wyaw in ring_m(mid):
            red = k < 12 and red_zone.contains(Point(x, z))
            t = math.radians(wyaw)  # the piece's footprint must sit inside the wall
            u, v = (math.cos(t) * length / 2, math.sin(t) * length / 2), (-math.sin(t) * STEP / 2, math.cos(t) * STEP / 2)
            box = Polygon([(x + su * u[0] + sv * v[0], z + su * u[1] + sv * v[1]) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            if not stands.covers(box):
                continue
            put("building", "sr" if red else "st", x, z, 0.0, (length, top, STEP), RED_SEAT if red else rgb, wyaw, material="Concrete",
                collide=True)
            made += 1
        if not made:
            break
        k += 1
    bowl_top = 1.2 + (k - 1) * RISE

    # the outside: a white back wall to the top row and white buttress columns every other piece of the outline
    for n_, (x, z, length, wyaw) in enumerate(ring_m(poly)):
        put("facade", "bw", x, z, 0.0, (length, bowl_top + 1.0, 1.0), WHITE, wyaw, material="Concrete")
        if n_ % 2 == 0:
            put("facade", "co", x, z, 0.0, (1.2, ROOF_Y, 1.6), WHITE, wyaw, material="Concrete")

    # the roof ring over the outer stands: dark solar panels on a grey frame, light radial ribs, a grey inner edge
    for depth_in in (ROOF_IN * 0.25, ROOF_IN * 0.75):  # two rings of pieces so the fanning gaps stay small
        loop("facade", "rf", poly.buffer(-depth_in), ROOF_IN / 2 + 0.5, ROOF_Y, 0.8, ROOF, material="Metal")
        loop("facade", "rs", poly.buffer(-depth_in), ROOF_IN / 2 - 1.0, ROOF_Y + 0.8, 0.15, SOLAR,
             material="Metal")  # Glass mirrored the sky and read as the blue seats (Studio 2026-10-16)
    for n_, (x, z, length, wyaw) in enumerate(ring_m(poly)):
        if n_ % 3:
            continue
        ang = math.atan2(c.y - z, c.x - x)  # inward
        e, n = x + math.cos(ang) * ROOF_IN / 2, z + math.sin(ang) * ROOF_IN / 2
        put("facade", "rb", e, n, ROOF_Y + 0.8, (ROOF_IN, 0.35, 0.5), (214, 216, 218), math.degrees(ang), material="Metal")

    # outside the wall: a beige concourse, then the blue jogging ring
    loop("facade", "cn", poly.buffer(3.0), 6.5, 0.0, 0.15, CONCOURSE, material="Concrete", collide=True)
    loop("facade", "jg", poly.buffer(8.0), 4.5, 0.0, 0.16, APRON, material="Plaster", collide=True)

    # floodlight masts behind the stands at the four diagonals, a lamp bank on top facing the pitch
    for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        a = math.radians(yaw)
        dx, dy = sx * 0.62, sy * 0.62
        ray = LineString([(c.x, c.y), (c.x + (math.cos(a) * dx - math.sin(a) * dy) * 400, c.y + (math.sin(a) * dx + math.cos(a) * dy) * 400)])
        hit = ray.intersection(poly.exterior)
        if hit.is_empty:
            continue
        p = hit if hit.geom_type == "Point" else list(getattr(hit, "geoms", [hit]))[0]
        out = math.atan2(p.y - c.y, p.x - c.x)
        e, n = p.x + math.cos(out) * 5.0, p.y + math.sin(out) * 5.0
        put("prop", "fm", e, n, 0.0, (48.0, 1.6, 1.6), (150, 152, 156), 0.0, shape="Cylinder", material="Metal", collide=True)
        put("prop", "fl", e, n, 46.0, (6.0, 4.0, 1.0), (236, 236, 228), math.degrees(out) + 90.0, material="Neon")
    return items
