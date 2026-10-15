"""The department store on 길주로 (user 2026-10-15: "현백 디테일하게 진짜로"): two V-World blocks, east gis:11181260 (cell 1db) and
west gis:11011115 (cell 0a7), joined by a round glass atrium (gis:11206250). Called by facilities.build for the spec whose
"custom" is "hyundai".

Look from street-view crops of both blocks and a night photo of the east block (토요경제 article, viewed only, 2026-10-15): warm beige stone with a fine tile
grid, a two-floor rusticated base with a cornice band, rows of tall teal glass windows with round heads between full-height
pilaster strips, teal glass curtain strips wrapping every corner, a frieze and a heavy cornice under a stepped attic, louvres
and a few shop windows in the base. The east block's north face (길주로) is blank stone with framed panels; the west block's
west face has the entrance under one tall arched window. Satellite: a glass drum with a dome between the blocks, plant on the
east roof, a garden on the west roof. No brand lettering (sign bands stay blank).
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from shapely.geometry import Point, Polygon

import layout_details as LD
from facilities import Maker, look
from layout import Frame, Item

TOP = 46.0                    # main cornice, m (photos: both blocks the same height; the register's 51.5/59 m holds roof plant)
BASE = 11.0                   # rusticated base, two tall shop floors
FLOOR = 5.75                  # department-store floor
STONE = look("Limestone", (222, 210, 190), collide=True)
BASE_STONE = look("Sandstone", (205, 190, 168), collide=True)
TRIM = look("Limestone", (234, 226, 210))
JOINT = look("SmoothPlastic", (150, 140, 124))
TEAL = look("Glass", (70, 150, 160), transparency=0.15, reflectance=0.25)
MULLION = look("Metal", (190, 196, 196))
DARK = look("SmoothPlastic", (40, 46, 52), reflectance=0.1)
LOUVRE = look("Metal", (70, 72, 74))
CORNER_W = 6.0                # teal strip on each side of a corner
BAY = 9.0                     # window bay pitch
ARCH_W = 4.6


def _compass(bx: Any, side: str) -> str:
    f = LD.face_of(bx, side)
    e0, n0 = LD._world(bx, 0.0, 0.0)
    e1, n1 = LD._world(bx, f.n[0], f.n[1])
    de, dn = e1 - e0, n1 - n0
    return ("E" if de > 0 else "W") if abs(de) > abs(dn) else ("N" if dn > 0 else "S")


class Store(Maker):
    """One block of the store. spec: {"plain": [compass sides with no windows], "entrance": compass side or None, "roof": "plant"|"garden"}."""

    def __init__(self, frame: Frame, body: LD.Body, spec: Mapping[str, Any], others: Sequence[Polygon]):
        super().__init__(frame, body, spec, main=True)
        self.others = others

    def open_faces(self) -> list[tuple[int, str, str]]:
        """Faces that are seen: long enough, not occluded inside the body, not facing into the other block or the atrium."""
        b = self.body
        out = []
        for bi, bx in enumerate(b.boxes):
            for s in LD.SIDES:
                if s in (b.occluded[bi] if bi < len(b.occluded) else ()):
                    continue
                f = LD.face_of(bx, s)
                if f.length < 3.0:
                    continue
                e, n = LD._world(bx, f.c[0] + f.n[0] * 2.5, f.c[1] + f.n[1] * 2.5)
                if any(p.contains(Point(e, n)) for p in self.others):
                    continue
                out.append((bi, s, _compass(bx, s)))
        return out

    def make(self) -> list[Item]:
        b = self.body
        for bi, bx in enumerate(b.boxes):
            self.box(bi, "m", 0.0, 0.0, 0.0, (bx.width_m, TOP, bx.depth_m), STONE, kind="building")
        for bi, side, comp in self.open_faces():
            self.face(bi, side, comp)
        self.top()
        return self.items

    def face(self, bi: int, side: str, comp: str) -> None:
        L = LD.face_of(self.body.boxes[bi], side).length
        # base: rusticated stone, joints every 0.9 m, a cornice band on top
        self.wall(bi, side, "bs", 0.0, 0.0, 0.35, (L + 0.7, BASE, 0.35), BASE_STONE)
        for k in range(1, int(BASE / 0.9)):
            self.wall(bi, side, "bj", 0.0, k * 0.9, 0.38, (L + 0.7, 0.06, 0.05), JOINT)
        self.wall(bi, side, "bc", 0.0, BASE, 0.7, (L + 1.4, 0.7, 0.7), TRIM)
        # corners: teal curtain strips from the base to the frieze, a mullion grid
        cw = min(CORNER_W, L * 0.18)
        for end in (-1, 1):
            at = end * (L / 2 - cw / 2 - 1.5)  # a 1.5 m stone pier stays at the corner (night photo)
            self.wall(bi, side, "cg", at, BASE + 0.7, 0.45, (cw, TOP - 4.5 - BASE - 0.7, 0.3), TEAL)
            for j in range(1, max(2, int(cw / 1.5))):
                self.wall(bi, side, "cv", at - cw / 2 + j * cw / max(2, int(cw / 1.5)), BASE + 0.7, 0.5, (0.1, TOP - 4.5 - BASE - 0.7, 0.08), MULLION)
            for k in range(1, int((TOP - 4.5 - BASE) / FLOOR) + 1):
                self.wall(bi, side, "ch", at, BASE + k * FLOOR, 0.5, (cw, 0.12, 0.08), MULLION)
        inner = L - 2 * cw - 5.0
        n = max(0, int(inner // BAY))
        plain = comp in (self.spec.get("plain") or ())
        entrance = comp == self.spec.get("entrance")
        for j in range(n):
            at = -inner / 2 + BAY * (j + 0.5) + (inner - n * BAY) / 2
            # pilaster strip between bays
            self.wall(bi, side, "pl", at - BAY / 2, BASE + 0.7, 0.25, (1.0, TOP - 4.5 - BASE - 0.7, 0.25), TRIM)
            if plain:  # the 길주로 face: a pair of slender recessed windows per bay, a framed panel in the middle bay
                if j == n // 2:
                    self.wall(bi, side, "fp", at, BASE + 9.0, 0.2, (5.2, 9.0, 0.12), TRIM)
                    self.wall(bi, side, "fi", at, BASE + 9.4, 0.22, (4.4, 8.2, 0.08), STONE)
                else:
                    for dx in (-1.1, 1.1):
                        self.wall(bi, side, "sl", at + dx, BASE + 3.0, 0.08, (0.9, TOP - 13.0 - BASE - 3.0, 0.1), DARK)
                continue
            if entrance and j == n // 2:
                self.arch(bi, side, at, BASE + 1.5, TOP - 7.0, ARCH_W + 1.6)
            elif j % 2 == 0 or n <= 2:
                self.arch(bi, side, at, BASE + 3.0, TOP - 9.0, ARCH_W)
            else:  # dark louvre panel between arched windows
                self.wall(bi, side, "gr", at, BASE + 3.0, 0.1, (2.6, TOP - 12.0 - BASE - 3.0, 0.12), DARK)
                for k in range(int((TOP - 15.0 - BASE) / 1.2)):
                    self.wall(bi, side, "gl", at, BASE + 3.4 + k * 1.2, 0.15, (2.4, 0.08, 0.06), LOUVRE)
        # shop windows and louvres in the base (none under the entrance)
        for j in range(n):
            at = -inner / 2 + BAY * (j + 0.5) + (inner - n * BAY) / 2
            if entrance and j == n // 2:
                self.wall(bi, side, "dr", at, 0.0, 0.42, (6.0, 4.2, 0.12), DARK)
                self.wall(bi, side, "dc", at, 4.4, 3.0, (8.0, 0.4, 3.0), look("Metal", (60, 64, 70), collide=True))
            elif (j + (1 if plain else 0)) % 3 == 1:
                self.wall(bi, side, "lv", at, 4.5, 0.42, (3.6, 2.4, 0.1), LOUVRE)
            elif j % 3 == 0:
                self.wall(bi, side, "sw", at, 0.6, 0.42, (4.8, 3.6, 0.1), DARK)
                self.wall(bi, side, "sf", at, 4.2, 0.45, (5.2, 0.3, 0.12), TRIM)
        # a teal glass band on the top floor between the corner strips (night photo), frieze, cornice, an attic of square blind panels
        self.wall(bi, side, "tb", 0.0, TOP - 8.2, 0.32, (max(1.0, inner), 2.6, 0.1), TEAL)
        self.wall(bi, side, "fz", 0.0, TOP - 4.5, 0.3, (L + 0.6, 2.8, 0.3), TRIM)
        self.wall(bi, side, "cr", 0.0, TOP - 1.7, 1.0, (L + 2.0, 0.9, 1.0), TRIM)
        self.wall(bi, side, "cs", 0.0, TOP - 0.8, 1.3, (L + 2.6, 0.5, 1.3), TRIM)
        self.wall(bi, side, "at", 0.0, TOP, -0.6, (L - 1.2, 3.0, 0.4), STONE)
        for j in range(int((L - 2.0) // 4.0)):
            self.wall(bi, side, "ap", -(L - 2.0) / 2 + 4.0 * (j + 0.5), TOP + 0.6, -0.5, (2.6, 1.8, 0.08), TRIM)

    def arch(self, bi: int, side: str, at: float, y0: float, y1: float, w: float) -> None:
        """A tall teal window with a round head in a stone frame, mullions every 1.5 m across and a transom every floor."""
        rect = max(2.0, y1 - y0 - w / 2)
        self.wall(bi, side, "af", at, y0 - 0.4, 0.3, (w + 1.0, rect + 0.4, 0.2), TRIM)
        self.wall(bi, side, "ad", at, y0 + rect - w / 2 - 0.5, 0.3, (w + 1.0, w + 1.0, 0.2), dict(TRIM, shape="Disc"))
        self.wall(bi, side, "ag", at, y0, 0.36, (w, rect, 0.1), TEAL)
        self.wall(bi, side, "ae", at, y0 + rect - w / 2, 0.36, (w, w, 0.1), dict(TEAL, shape="Disc"))
        for j in (-1, 0, 1):
            self.wall(bi, side, "am", at + j * w / 3, y0, 0.42, (0.1, rect + w / 2 * 0.9, 0.06), MULLION)
        for k in range(1, int(rect / 2.4) + 1):
            self.wall(bi, side, "at", at, y0 + k * 2.4, 0.42, (w, 0.1, 0.06), MULLION)

    def top(self) -> None:
        b = self.body
        for bi, bx in enumerate(b.boxes):
            self.box(bi, "rt", 0.0, 0.0, TOP - 0.05, (bx.width_m - 0.6, 0.2, bx.depth_m - 0.6), look("Concrete", (150, 150, 146)))
        bx = b.boxes[b.front]
        w, d = bx.width_m, bx.depth_m
        if self.spec.get("roof") == "plant":  # cooling towers and a plant deck on the east third
            self.box(b.front, "pd", w / 3, 0.0, TOP, (w / 3, 0.4, d * 0.7), look("SmoothPlastic", (70, 72, 76)))
            for i in range(3):
                self.box(b.front, "ct", w / 3 - 6 + i * 6, -d / 5, TOP + 0.4, (4.5, 3.2, 4.5), look("Metal", (200, 202, 204)))
            self.box(b.front, "pb", w / 4, d / 5, TOP + 0.4, (8.0, 4.0, 6.0), STONE)
        else:  # a roof garden: lawn, low hedges, a pergola
            self.box(b.front, "gd", -w / 6, 0.0, TOP, (w / 2.2, 0.35, d * 0.6), look("SmoothPlastic", (96, 132, 80)))
            for i in range(4):
                self.box(b.front, "hg", -w / 6 - w / 5 + i * w / 15, d * 0.25, TOP + 0.35, (2.2, 1.0, 1.2), look("SmoothPlastic", (60, 100, 60)))
            self.box(b.front, "pg", w / 5, 0.0, TOP + 0.35, (6.0, 2.8, 6.0), look("Wood", (150, 110, 80)))


def atrium(frame: Frame, bid: str, poly: Polygon, blocks: Sequence[Polygon] = ()) -> list[Item]:
    """The glass drum between the blocks: a glass cylinder ringed by mullions, floor bands and a stepped glass dome."""
    c = poly.centroid
    r = max(5.0, min(12.0, math.sqrt(poly.area / math.pi)))
    glass = dict(material="Glass", color=(110, 165, 175), color_name=None, transparency=0.35, reflectance=0.3)
    metal = dict(material="Metal", color=(200, 204, 206), color_name=None)
    items: list[Item] = []

    def put(tail: str, east: float, north: float, y: float, size: tuple[float, float, float], shape: str, lk: Mapping[str, Any]) -> None:
        items.append(LD._part(frame, "facade", f"{bid}#{tail}-{len(items)}", bid, len(items), east, north, y, size, 0.0,
                              owner=bid, shape=shape, **lk))

    h = TOP - 3.0
    from plaza import strips
    fill = poly.buffer(0.6)
    if len(blocks) == 2:  # and the strip where the two blocks face each other (15 m apart; the street-view gap is glass too)
        a, b = blocks
        between = a.union(b).convex_hull.difference(a.union(b))
        fill = fill.union(between.intersection(a.buffer(a.distance(b) + 1.0)).intersection(b.buffer(a.distance(b) + 1.0)))
    for x, z, w, d in strips(fill, 2.0):  # glass walls: the blocks are joined (no gap)
        put("gw", x, z, 0.0, (w, h - 1.0, d), "Block", dict(glass, transparency=0.55))
    put("dr", c.x, c.y, 0.0, (h, 2 * r, 2 * r), "Cylinder", glass)
    for k in range(24):
        a = 2 * math.pi * k / 24
        put("rb", c.x + math.cos(a) * r, c.y + math.sin(a) * r, 0.0, (0.25, h, 0.25), "Block", metal)
    for k in range(1, int(h / FLOOR) + 1):
        put("rg", c.x, c.y, k * FLOOR, (0.25, 2 * r + 0.3, 2 * r + 0.3), "Cylinder", metal)
    for k, f in enumerate((1.0, 0.82, 0.6, 0.34)):
        put("dm", c.x, c.y, h + k * 1.3, (1.3, 2 * r * f, 2 * r * f), "Cylinder", glass)
    put("dt", c.x, c.y, h + 5.2, (0.6, 1.4, 1.4), "Cylinder", metal)
    return items
