"""The driving range in cell 8930e0af1afffff (user-approved 2026-10-15) from regions/bucheon-dodang/hyundai_golf.json: white lattice
poles every 14 m round the field, a translucent green net between them and across the top, turf and distance boards. The hitting
bay block is the Auto building (bays face south onto the field). Called by facilities.build for the spec whose "custom" is "golf";
the facility is a Folder, so each part settles on the ground under it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from shapely.geometry import LineString, Polygon

import layout
import layout_details as LD
from anjunggeun import to_latlon
from layout import Frame, Item
from plaza import strips

LAYOUT = Path("regions/bucheon-dodang/hyundai_golf.json")


def build(frame: Frame, key: str) -> list[Item]:
    data = json.loads(LAYOUT.read_text(encoding="utf-8"))
    tx, ty = int(data["tile_x0"]), int(data["tile_y0"])
    items: list[Item] = []

    def m(p) -> tuple[float, float]:
        return layout.to_meters(frame, *to_latlon(tx, ty, p[0], p[1]))

    def put(tail, e, n, y, size, rgb, yaw=0.0, **extra) -> None:
        items.append(LD._part(frame, "prop", f"{key}#{tail}-{len(items)}", key, len(items), e, n, y, size, yaw, owner=None,
                              color=tuple(rgb), color_name=None, **{"material": "SmoothPlastic", **extra}))

    net = data["net"]
    H, gap = float(net["height_m"]), float(net["pole_spacing_m"])
    ring = [m(p) for p in net["px"]]
    netlk = dict(material="Fabric", transparency=0.55)
    for a, b in zip(ring, ring[1:] + ring[:1]):
        seg = LineString([a, b])
        yaw = -math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        c = seg.interpolate(0.5, normalized=True)
        put("nt", c.x, c.y, 0.0, (seg.length, H, 0.08), net["net_rgb"], yaw, **netlk)  # the net wall on this side
        for k in range(int(seg.length // gap) + 1):  # lattice poles: a mast and two cross arms
            q = seg.interpolate(min(seg.length, k * gap))
            put("pl", q.x, q.y, 0.0, (0.6, H + 1.0, 0.6), net["pole_rgb"], yaw, material="Metal")
            for y in (H * 0.5, H):
                put("pa", q.x, q.y, y - 0.3, (2.4, 0.25, 0.25), net["pole_rgb"], yaw + 90.0, material="Metal")
    roof = Polygon(ring).buffer(0)
    for x, z, w, d in strips(roof, 12.0):  # the top net, a few wide panels
        put("nr", x, z, H, (w, 0.06, d), net["net_rgb"], **netlk)
    field = Polygon([m(p) for p in data["field"]["px"]]).buffer(0)
    for x, z, w, d in strips(field, 3.0):
        put("tf", x, z, 0.0, (w, 0.08, d), data["field"]["rgb"], material="Grass")
    # distance boards every 25 m out from the bay end (north), white with the yardage band
    north = max(p[1] for p in field.exterior.coords)
    for k, dist in enumerate((25, 50, 75, 100)):
        y_line = north - dist
        cut = field.intersection(LineString([(field.bounds[0] - 1, y_line), (field.bounds[2] + 1, y_line)]))
        if cut.is_empty:
            continue
        c = cut.centroid
        put("db", c.x, c.y, 0.0, (3.0, 2.2 + k * 0.4, 0.2), (240, 240, 236), 0.0)
    return items
