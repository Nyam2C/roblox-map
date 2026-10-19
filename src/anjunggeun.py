"""안중근공원 (cell 8930e0af0a7ffff, user-approved 2026-10-15) from its traced ground layout regions/bucheon-dodang/anjunggeun_park.json:
lawns, grey and red-brown walks, plazas, the amphitheatre and stage, the memorial plaza and terrace, the statue on its round
platform, raised hedge beds, a brick hut and a curb railing. Called by facilities.build for the spec whose "custom" is "pxpark";
the facility is a Folder, so settleManual lifts every part onto the ground under it. Trees stay the satellite's (trees.json).

Polygons are filled with axis-aligned strips (plaza.strips); layers rise a few cm each (lawn < walk < plaza) so none flickers.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from shapely.geometry import LineString, Point, Polygon

import layout
import layout_details as LD
from layout import Frame, Item
from plaza import strips

LAYOUT = Path("regions/bucheon-dodang/anjunggeun_park.json")
TOP = {"lawn": 0.06, "paving": 0.08, "path": 0.10, "plaza": 0.12}   # top of each flat layer above the ground, m
STEP = {"lawn": 2.5, "paving": 2.0, "path": 1.0, "plaza": 1.2}
MATERIALS = {"Grass": "Grass", "Pavement": "Pavement", "Granite": "Granite", "Brick": "Brick", "Concrete": "Concrete", "Marble": "Marble",
             "Metal": "Metal", "Slate": "Slate", "Wood": "Wood"}


def to_latlon(tile_x0: int, tile_y0: int, px: float, py: float, zoom: int = 19) -> tuple[float, float]:
    """A pixel of the satellite mosaic -> lat/lon (web mercator; trees.Georef without its image imports)."""
    n = 2 ** zoom
    tx, ty = tile_x0 + px / 256, tile_y0 + py / 256
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n)))), tx / n * 360 - 180


def build(frame: Frame, key: str, layout_path: str | None = None) -> list[Item]:
    """The parts of a traced park; `layout_path` names another park's layout (spec "layout", 진달래공원 2026-10-16)."""
    data = json.loads(Path(layout_path or LAYOUT).read_text(encoding="utf-8"))
    items: list[Item] = []

    def m(px: float, py: float) -> tuple[float, float]:
        return layout.to_meters(frame, *to_latlon(int(data["tile_x0"]), int(data["tile_y0"]), px, py))

    def put(tail: str, east: float, north: float, y: float, size: tuple[float, float, float], f: Mapping[str, Any], shape: str = "Block",
            yaw: float = 0.0, **extra: Any) -> None:
        rgb = tuple(int(c) for c in f.get("rgb") or (180, 180, 175))
        items.append(LD._part(frame, "prop", f"{key}#{tail}-{len(items)}", key, len(items), east, north, y, size, yaw, owner=None,
                              shape=shape, material=MATERIALS.get(f.get("material"), "SmoothPlastic"), color=rgb, color_name=None, **extra))

    for n, f in enumerate(data["features"]):
        kind, shape, px = f["kind"], f["shape"], f["px"]
        h = float(f.get("height_m") or 0.0)
        if shape == "circle":
            (cx, cy), (rp, _) = px
            ce, cn = m(cx, cy)
            r = math.dist(m(cx, cy), m(cx + rp, cy))
            if kind == "statue" and f.get("material") == "Metal":  # the bronze figure: robe, shoulders, head
                put("sf", ce, cn, 2.3, (1.6, 0.9, 0.9), f, "Cylinder")
                put("ss", ce, cn, 3.9, (0.5, 1.1, 1.1), f, "Cylinder")
                put("sh", ce, cn, 4.4, (0.6, 0.6, 0.6), f, "Ball")
            elif kind == "statue":  # the pedestal
                put("sp", ce, cn, 0.3, (max(1.0, r * 2), h or 2.0, max(1.0, r * 2)), f)
            elif "amphitheatre" in f.get("note", ""):  # seating terraces stepping down to the stage
                for k, s in enumerate((1.0, 0.8, 0.6, 0.4)):
                    put("am", ce, cn, 0.0, (TOP["plaza"] + 0.15 * (3 - k), 2 * r * s, 2 * r * s), f, "Cylinder")
            else:
                put("pc", ce, cn, 0.0, (max(TOP["plaza"] + 0.02, h), 2 * r, 2 * r), f, "Cylinder")
            continue
        poly = Polygon([m(x, y) for x, y in px]).buffer(0)
        if poly.is_empty:
            continue
        if kind in TOP:
            for x, z, w, d in strips(poly, STEP[kind]):
                put(kind[:2], x, z, 0.0, (w, TOP[kind], d), f)
        elif kind in ("bed", "stage", "bench_row", "water", "stair"):  # raised (or a rimmed sunken oval) on its outline
            top = {"water": 0.18, "stair": 0.14}.get(kind, h or 0.4)
            for x, z, w, d in strips(poly, 1.0):
                put(kind[:2], x, z, 0.0, (w, top, d), f)
            if kind == "bed":  # a granite curb along the bed
                for a, b in zip(poly.exterior.coords[:-1], poly.exterior.coords[1:]):
                    seg = LineString([a, b])
                    if seg.length > 0.5:
                        c = seg.interpolate(0.5, normalized=True)
                        put("cb", c.x, c.y, 0.0, (seg.length, top + 0.1, 0.25), {"rgb": (170, 168, 160), "material": "Granite"},
                            yaw=math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))
        elif kind in ("wall", "fence"):  # along the long side (a rect) or every edge (a poly)
            coords = list(poly.exterior.coords) if shape == "poly" else None
            if shape == "rect":
                r = poly.minimum_rotated_rectangle
                pts = list(r.exterior.coords)[:4]
                edges = sorted(((math.dist(pts[i], pts[(i + 1) % 4]), i) for i in range(4)), reverse=True)
                _, i = edges[0]
                a, b = pts[i], pts[(i + 1) % 4]
                thick = max(0.4, edges[2][0])
                c = poly.centroid
                put("wl", c.x, c.y, 0.0, (math.dist(a, b), h or 2.5, thick), f, yaw=math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))
                continue
            for a, b in zip(coords[:-1], coords[1:]):
                seg = LineString([a, b])
                if seg.length < 0.5:
                    continue
                c = seg.interpolate(0.5, normalized=True)
                yaw = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                if kind == "fence":
                    put("fr", c.x, c.y, (h or 1.0) - 0.06, (seg.length, 0.06, 0.06), f, yaw=yaw)
                    for t in range(int(seg.length // 2.0) + 1):
                        q = seg.interpolate(min(seg.length, t * 2.0))
                        put("fp", q.x, q.y, 0.0, (0.06, h or 1.0, 0.06), f)
                else:
                    put("wl", c.x, c.y, 0.0, (seg.length, h or 3.0, 0.4), f, yaw=yaw)
        elif kind == "pergola":  # the small brick hut with a dark hipped roof
            r = poly.minimum_rotated_rectangle
            c = poly.centroid
            pts = list(r.exterior.coords)[:4]
            w, d = math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2])
            yaw = math.degrees(math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0]))
            if f.get("open"):  # an open shade tent (진달래공원, 2026-10-16): four posts under a thin membrane roof in its own colour
                for su in (-1, 1):
                    for sv in (-1, 1):
                        a = math.radians(yaw)
                        du, dv = su * (w / 2 - 0.2), sv * (d / 2 - 0.2)
                        put("tp", c.x + du * math.cos(a) - dv * math.sin(a), c.y + du * math.sin(a) + dv * math.cos(a), 0.0,
                            (0.15, h or 3.5, 0.15), {"rgb": (200, 200, 200), "material": "Metal"})
                put("tr", c.x, c.y, (h or 3.5), (w + 0.4, 0.15, d + 0.4), f, yaw=yaw)
                continue
            put("hu", c.x, c.y, 0.0, (w, (h or 3.5) - 1.0, d), f, yaw=yaw, collide=True)
            put("hr", c.x, c.y, (h or 3.5) - 1.0, (w + 0.6, 1.0, d + 0.6), {"rgb": (60, 60, 64), "material": "Slate"}, yaw=yaw)
    return items
