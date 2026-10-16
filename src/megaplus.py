"""메가플러스 in cell 8930e0af0b3ffff, across 길주로 from 세이브존 (user 2026-10-17: "세이브존 건너편 메가플라자 건물 보강", eleven
photos of his own, looked at locally only), V-World record gis:11731027 (its duplicate gis:14851413 is only claimed). Called by
facilities.build for the spec whose "custom" is "megaplus". No business or building name anywhere: the boards carry trade words.

Look from the photos and the satellite:
- A 7-floor podium over the whole five-sided lot, its NW corner cut on a slant toward the 상동역 crossing. Floors 2-6 are covered
  with big signboards row on row, windows showing between them; floor 7 (a sauna) is all glass with lettering along its top.
  Glass shops on the ground floor and, on the north face (길주로), a passage open five floors high.
- A slab tower set back on the podium (satellite: 19.5 m from the north edge, 19 m from the south, 4 m west, 3 m east), to 16
  floors (62.8 m; the register says 14, the photos show 7 + 9): beige stone piers, a window band a floor, a steel frame along the
  top of the north face, two huge poster boards (no text); a green roof with two plant rooms and a small garden.
- Podium roof: pines along the north edge in the tower's shadow, a planter garden on the south part.
"""
from __future__ import annotations

import math
from typing import Any

from shapely.affinity import rotate
from shapely.geometry import Point, Polygon
from shapely.geometry import box as rect
from shapely.geometry.polygon import orient

import layout_details as LD
from layout import Box, Frame, Item
from savezone import fill

FLOORS, H, PODIUM = 16, 62.8, 7
FH = H / FLOORS
PH = PODIUM * FH
INSET = {"N": 19.5, "S": 19.0, "W": 4.0, "E": 3.0}  # the tower in from the podium edges (satellite, building frame)
STONE, TOWER, PIER = (206, 200, 188), (200, 186, 162), (210, 198, 176)
GLASS, SHOP_GLASS, METAL = (62, 82, 90), (52, 64, 72), (150, 152, 156)
TOWER_GLASS = (70, 94, 98)
WORDS = ("한의원", "치과의원", "안과", "정형외과", "내과", "피부과", "이비인후과", "소아청소년과", "재활의학과", "산부인과", "보청기",
         "검진센터", "미술학원", "독서실", "영상의학과", "통증의학과")
SHOPS = ("카페", "분식", "의류", "은행", "안경", "약국", "부동산", "제과")
BOARDS = ((38, 92, 62), (236, 196, 46), (226, 78, 140), (32, 52, 120), (196, 40, 40), (150, 196, 60), (28, 28, 30),
          (240, 240, 236), (230, 120, 40), (60, 140, 210))
LIGHT = {(236, 196, 46), (150, 196, 60), (240, 240, 236)}


def faces_of(poly: Polygon, min_len: float = 4.0) -> list[tuple[str, Box, float, float]]:
    """Every outline edge of min_len or more: (side, a 1 m box on the edge, s = which way along the box's v is out, length).
    side is N/E/S/W, or C for a slanted corner face."""
    out = []
    cs = list(orient(poly, 1.0).exterior.coords)
    for (x0, y0), (x1, y1) in zip(cs, cs[1:]):
        L = math.dist((x0, y0), (x1, y1))
        if L < min_len:
            continue
        bx = Box((x0 + x1) / 2, (y0 + y1) / 2, L, 1.0, math.degrees(math.atan2(y1 - y0, x1 - x0)), 1.0)
        e, n = LD._world(bx, 0.0, 2.0)
        s = -1.0 if poly.contains(Point(e, n)) else 1.0
        nx, ny = (e - bx.cx_m) / 2 * s, (n - bx.cy_m) / 2 * s
        side = "C" if abs(nx) > 0.45 and abs(ny) > 0.45 else "N" if ny > 0 and abs(ny) >= abs(nx) else "S" if abs(ny) >= abs(nx) else "E" if nx > 0 else "W"
        out.append((side, bx, s, L))
    return out


def build(frame: Frame, bid: str, poly: Polygon) -> list[Item]:
    items: list[Item] = []

    def put(kind: str, tail: str, e: float, n: float, y: float, size, rgb, yaw: float = 0.0, **extra: Any) -> None:
        extra = {"material": "SmoothPlastic", **extra}
        items.append(LD._part(frame, kind, f"{bid}#{tail}-{len(items)}", bid, len(items), e, n, y, size, yaw,
                              owner=bid, color=tuple(rgb), color_name=None, **extra))

    def on(tail: str, bx: Box, s: float, u: float, out: float, y: float, size, rgb, kind: str = "facade", **extra: Any) -> None:
        """A part on a face, its back `out` metres off the wall; a sign's Front (the box's -v) turned outward."""
        e, n = LD._world(bx, u, s * (out + size[2] / 2))
        put(kind, tail, e, n, y, size, rgb, bx.yaw_deg + (180.0 if kind == "sign" and s > 0 else 0.0), **extra)

    def board(tail: str, bx: Box, s: float, u: float, out: float, y: float, size, rgb, text: str | None) -> None:
        if text:
            ink = (30, 30, 30) if tuple(rgb) in LIGHT else (255, 255, 255)
            on(tail, bx, s, u, out, y, size, rgb, kind="sign", text=text, faces="F", attrs={"MaxDistance": 400, "Ink": list(ink)})
        else:
            on(tail, bx, s, u, out, y, size, rgb)

    body = orient(poly, 1.0)
    cs = list(body.exterior.coords)
    a, b = max(zip(cs, cs[1:]), key=lambda e: math.dist(*e))  # the longest wall (south): the frame the tower and fills line up with
    turn = (math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) + 90.0) % 180.0 - 90.0
    c0 = body.centroid
    x0, y0, x1, y1 = rotate(body, -turn, origin=c0).bounds
    tower = rotate(rect(x0 + INSET["W"], y0 + INSET["S"], x1 - INSET["E"], y1 - INSET["N"]), turn, origin=c0)
    tc = tower.centroid
    tw, td = (x1 - x0) - INSET["W"] - INSET["E"], (y1 - y0) - INSET["S"] - INSET["N"]

    # the podium mass (1 m fills keep the slanted corner) and the tower on it
    for x, z, w, d in fill(rotate(body, -turn, origin=c0), 1.0):
        q = rotate(Point(x, z), turn, origin=c0)
        put("building", "m", q.x, q.y, 0.0, (w, PH, d), STONE, turn, collide=True)
    put("building", "t", tc.x, tc.y, PH, (tw, H - PH, td), TOWER, turn, collide=True)

    # podium faces: shops, signboard rows over window bands, the sauna floor, parapet and railing
    faces = faces_of(body)
    north = max((f for f in faces if f[0] == "N"), key=lambda f: f[3], default=None)
    for fi, (side, bx, s, L) in enumerate(faces):
        east_u = 1.0 if math.cos(math.radians(bx.yaw_deg)) >= 0 else -1.0  # +u runs east (or west) along this face
        gap = None
        if north is not None and bx is north[1]:  # the passage, 40 % along from the west end, five floors high
            ua = east_u * (0.40 - 0.5) * L
            gap = (ua - 3.8, ua + 3.8)
            on("ad", bx, s, ua, 0.05, 0.0, (7.0, 5 * FH, 0.4), (26, 26, 30))
            on("al", bx, s, ua, 0.46, 5 * FH - 0.6, (6.6, 0.25, 0.05), (255, 236, 190), material="Neon")
            board("as", bx, s, ua, 0.5, 5 * FH + 0.4, (7.0, 1.1, 0.2), (28, 28, 30), "아케이드")

        def pieces(lo: float, hi: float, k: int) -> list[tuple[float, float]]:
            if gap is None or k > 4 or gap[1] <= lo or gap[0] >= hi:
                return [(lo, hi)]
            return [p for p in ((lo, gap[0]), (gap[1], hi)) if p[1] - p[0] > 1.0]

        talk = side in ("N", "W", "C")  # lettering on the street faces round the crossing; colour only behind
        for a, b in pieces(-L / 2 + 0.5, L / 2 - 0.5, 0):  # ground floor: shop glass and fascias
            on("sg", bx, s, (a + b) / 2, 0.02, 0.3, (b - a, FH - 1.5, 0.1), SHOP_GLASS, material="Glass", reflectance=0.2)
            u, j = a, 0
            while b - u > 3.0:
                w = min(b - u, 5.5 + ((j * 5 + fi * 3) % 4) * 1.2)
                c = BOARDS[(j * 7 + fi * 3 + 1) % len(BOARDS)]
                board("sf", bx, s, u + w / 2, 0.15, FH - 1.15, (w - 0.3, 0.9, 0.2), c, SHOPS[(j * 3 + fi * 5) % len(SHOPS)] if talk else None)
                u, j = u + w, j + 1
        for k in range(1, PODIUM - 1):  # floors 2-6: a window band, signboards row on row over it
            for a, b in pieces(-L / 2 + 0.5, L / 2 - 0.5, k):
                on("wg", bx, s, (a + b) / 2, 0.02, k * FH + 0.6, (b - a, FH - 1.3, 0.08), GLASS, material="Glass", reflectance=0.15)
            u, j = -L / 2 + 0.5, 0
            while u < L / 2 - 3.0:
                w = min(L / 2 - 0.5 - u, 6.0 + ((k * 7 + j * 5 + fi * 3) % 7) * 1.6)  # big boards, most of a floor (photos)
                bh = 2.3 + ((k + j) % 3) * 0.35
                hole = (j * 3 + k + fi) % 9 == 4  # now and then a bare stretch of windows
                hit = gap is not None and k <= 4 and u < gap[1] and u + w > gap[0]
                if w >= 2.5 and not hole and not hit:
                    word = WORDS[(k * 5 + j * 3 + fi * 7) % len(WORDS)]
                    c = BOARDS[(k * 3 + j * 7 + fi * 5) % len(BOARDS)]
                    board("bd", bx, s, u + w / 2, 0.12 + 0.08 * (j % 2), (k + 1) * FH - bh - 0.2, (w - 0.25, bh, 0.25), c,
                          f"{word} {k + 1}F" if talk else None)
                u, j = u + w + 0.3 + ((k + j * 3 + fi) % 3) * 0.5, j + 1
        k = PODIUM - 1  # the sauna floor: tall glass with mullions, its lettering along the top
        on("ug", bx, s, 0.0, 0.02, k * FH + 0.4, (L - 1.0, FH - 1.3, 0.08), (110, 140, 140), material="Glass", reflectance=0.2)
        for m in range(1, int(L // 2.2)):
            on("um", bx, s, -L / 2 + m * L / int(L // 2.2), 0.1, k * FH + 0.4, (0.15, FH - 1.3, 0.12), PIER)
        if talk and L >= 10.0:
            board("us", bx, s, 0.0, 0.12, PH - 1.25, (min(14.0, L - 2.0), 1.1, 0.12), STONE, "불가마 사우나" if side == "C" else "24시 사우나")
        on("pp", bx, s, 0.0, 0.0, PH - 0.5, (L + 0.2, 0.5, 0.3), PIER)
        on("rl", bx, s, 0.0, -0.3, PH + 1.0, (L, 0.08, 0.08), METAL, material="Metal")
        for m in range(int(L // 2.5) + 1):
            on("rp", bx, s, -L / 2 + m * L / max(1, int(L // 2.5)), -0.3, PH, (0.08, 1.0, 0.08), METAL, material="Metal")
        if side == "C":  # the two tall blade signs on the slanted corner's edges (colour only)
            for du, c in ((-L / 2 + 0.6, (32, 52, 120)), (L / 2 - 0.6, (40, 92, 62))):
                on("bl", bx, s, du, 0.6, FH, (0.9, 5 * FH, 0.3), c)

    # the tower: a window band a floor between stone piers, floor bands, the parapet; posters; the frame on the north edge
    tf = faces_of(tower)
    for side, bx, s, L in tf:
        east_u = 1.0 if math.cos(math.radians(bx.yaw_deg)) >= 0 else -1.0
        for k in range(PODIUM, FLOORS):
            on("tg", bx, s, 0.0, 0.02, k * FH + 0.9, (L - 0.6, FH - 1.6, 0.08), TOWER_GLASS, material="Glass", reflectance=0.25)
            on("tb", bx, s, 0.0, 0.05, k * FH, (L + 0.1, 0.8, 0.2), PIER)
        n = max(2, int(L // 3.4))
        for j in range(1, n):
            on("tp", bx, s, -L / 2 + j * L / n, 0.05, PH, (0.7, H - PH, 0.3), PIER)
        on("tt", bx, s, 0.0, 0.05, H - 1.0, (L + 0.2, 1.0, 0.3), PIER)
        if side == "N":  # the big blue poster at the west (corner) end, the white one low at the east end (photos)
            on("po", bx, s, -east_u * 0.38 * L, 0.4, PH + 2 * FH, (9.0, 6 * FH, 0.2), (32, 48, 128))
            on("pe", bx, s, east_u * 0.40 * L, 0.4, PH + 0.3, (6.0, 4 * FH, 0.2), (236, 236, 232))
            for j in range(int(L // 3.0) + 1):  # the steel frame along the top
                on("fp", bx, s, -L / 2 + j * L / max(1, int(L // 3.0)), -1.2, H, (0.25, 3.5, 0.25), (70, 72, 78), material="Metal")
            for y in (H + 1.2, H + 3.3):
                on("fr", bx, s, 0.0, -1.2, y, (L, 0.2, 0.2), (70, 72, 78), material="Metal")
        elif side == "W":  # its lettering along the top
            board("ts", bx, s, 0.0, 0.4, H - 2.6, (min(16.0, L - 4.0), 1.8, 0.15), TOWER, "한방병원")

    # roofs: the tower's green roof, two plant rooms, a small garden; the podium roof with pines north and planters south
    for x, z, w, d in fill(rotate(tower.buffer(-0.3), -turn, origin=c0), 2.0):
        q = rotate(Point(x, z), turn, origin=c0)
        put("facade", "tr", q.x, q.y, H - 0.05, (w, 0.15, d), (96, 150, 128), turn)
    for f in (-0.28, 0.28):
        e, n = LD._world(Box(tc.x, tc.y, tw, td, turn, 1.0), f * tw, 0.0)
        put("facade", "mr", e, n, H, (9.0, 4.0, min(16.0, td - 4.0)), (196, 196, 192), turn)
    for j in range(5):
        e, n = LD._world(Box(tc.x, tc.y, tw, td, turn, 1.0), (j - 2) * 3.5, ((j * 3) % 5 - 2) * 1.2)
        put("facade", "gk", e, n, H, (1.8, 0.3, 0.3), (110, 84, 60), shape="Cylinder")
        put("facade", "gc", e, n, H + 1.2, (2.8, 2.8, 2.8), (72, 120, 64), shape="Ball")
    deck = body.buffer(-0.4).difference(tower.buffer(0.2))
    for x, z, w, d in fill(rotate(deck, -turn, origin=c0), 2.0):
        q = rotate(Point(x, z), turn, origin=c0)
        put("facade", "pr", q.x, q.y, PH - 0.05, (w, 0.15, d), (150, 150, 146), turn)
    frame_box = Box(c0.x, c0.y, x1 - x0, y1 - y0, turn, 1.0)
    for j in range(12):  # pines along the north edge of the podium roof
        u = (x0 - c0.x) + (j + 0.5) * (x1 - x0) / 12
        e, n = LD._world(frame_box, u, -((y1 - c0.y) - 2.5))
        if body.buffer(-1.5).contains(Point(e, n)) and not tower.buffer(1.0).contains(Point(e, n)):
            put("facade", "pk", e, n, PH, (2.4, 0.35, 0.35), (100, 76, 56), shape="Cylinder")
            put("facade", "pc", e, n, PH + 2.0, (3.4, 3.0, 3.4), (50, 92, 56), shape="Ball")
    for i in range(6):  # the planter garden on the south part, the middle left open as on the satellite
        for k2 in range(2):
            if i in (2, 3):
                continue
            u = (x0 - c0.x) + (i + 0.5) * (x1 - x0) / 6
            v = (y0 - c0.y) + 5.0 + k2 * 7.0
            e, n = LD._world(frame_box, u, -v)
            if body.buffer(-1.5).contains(Point(e, n)):
                put("facade", "gp", e, n, PH, (9.0, 0.6, 3.0), (140, 100, 70), turn)
                put("facade", "gg", e, n, PH + 0.6, (8.6, 0.25, 2.6), (92, 132, 70), turn, material="Grass")
    return items
