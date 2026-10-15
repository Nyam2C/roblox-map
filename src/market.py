"""강남종합시장 (cell 8930e0af137ffff, user-approved 2026-10-15): the covered arcade read off the satellite and news photos
(regions/bucheon-dodang/gangnam_market.json): a translucent barrel roof over each alley (two wedges and a crown strip on dark ribs),
gate frames with the market's name, and stall fronts along both sides (goods on low tables, fascia boards). The shops themselves
are the Auto buildings. Called by facilities.build for the spec whose "custom" is "market"; the facility is a Folder.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import layout
import layout_details as LD
from anjunggeun import to_latlon
from layout import Box, Frame, Item

LAYOUT = Path("regions/bucheon-dodang/gangnam_market.json")
BAY = 3.6
GOODS = ((200, 70, 60), (230, 180, 60), (90, 150, 80), (70, 110, 170), (210, 210, 205))
BOARDS = ((245, 245, 240), (240, 200, 60), (200, 60, 50), (60, 130, 80))


def build(frame: Frame, key: str) -> list[Item]:
    data = json.loads(LAYOUT.read_text(encoding="utf-8"))
    tx, ty = int(data["tile_x0"]), int(data["tile_y0"])
    items: list[Item] = []

    def m(p) -> tuple[float, float]:
        return layout.to_meters(frame, *to_latlon(tx, ty, p[0], p[1]))

    def put(tail: str, box: Box, u: float, v: float, y: float, size, rgb, yaw_add: float = 0.0, **extra) -> None:
        e, n = LD._world(box, u, v)
        items.append(LD._part(frame, "prop", f"{key}#{tail}-{len(items)}", key, len(items), e, n, y, size, box.yaw_deg + yaw_add,
                              owner=None, color=tuple(rgb), color_name=None, **{"material": "SmoothPlastic", **extra}))

    for a in data["alleys"]:
        (x0, y0), (x1, y1) = m(a["px"][0]), m(a["px"][-1])
        L = math.dist((x0, y0), (x1, y1))
        w = float(a["width_m"])
        box = Box((x0 + x1) / 2, (y0 + y1) / 2, L, w, math.degrees(math.atan2(y1 - y0, x1 - x0)), 1.0)
        r = a["roof"]
        spring, top = float(r.get("spring_m", 4.8)), float(r.get("height_m", 6.0))
        glass = dict(transparency=float(r.get("transparency", 0.45)), material="Glass")
        half = w / 2 + 0.3
        for side, yaw in ((-1, 0.0), (1, 180.0)):  # the two slopes of the barrel, like the facilities' pitched roof
            put("rw", box, 0.0, side * half / 2, spring, (L + 0.6, top - spring - 0.2, half), r["rgb"], yaw, shape="Wedge", **glass)
        put("rc", box, 0.0, 0.0, top - 0.2, (L + 0.6, 0.12, 1.0), r["rgb"], **glass)
        for k in range(int(L // 5.0) + 1):  # ribs on posts at the alley sides
            u = -L / 2 + min(L, k * 5.0)
            put("rb", box, u, 0.0, spring, (0.15, 0.15, w + 0.6), r["ribs_rgb"], material="Metal")
            for s in (-1, 1):
                put("rp", box, u, s * (w / 2 + 0.25), 0.0, (0.15, spring, 0.15), r["ribs_rgb"], material="Metal")
        n = max(1, int(L // BAY))
        for k in range(n):  # stall fronts: goods on low tables and a fascia board each bay, both sides
            u = -L / 2 + BAY * (k + 0.5) + (L - n * BAY) / 2
            for s in (-1, 1):
                v = s * (w / 2 - 0.45)
                put("gt", box, u, v, 0.0, (BAY - 0.6, 0.8, 0.9), (110, 90, 70), material="Wood")
                put("gd", box, u, v, 0.8, (BAY - 0.9, 0.35, 0.7), GOODS[(k + (s > 0)) % len(GOODS)])
                put("fb", box, u, s * (w / 2 - 0.05), 3.0, (BAY - 0.3, 0.8, 0.1), BOARDS[(k * 2 + (s > 0)) % len(BOARDS)])
    for g in data["gates"]:  # a frame at the alley mouth: two posts, a beam with the market's name
        e, nn = m(g["px"])
        yaw = float(g.get("facing_deg", 0.0))
        box = Box(e, nn, 1.0, 1.0, yaw + 90.0, 1.0)  # local X runs across the alley mouth
        gw, gh = float(g["width_m"]), float(g["height_m"])
        for s in (-1, 1):
            put("gp", box, s * (gw / 2 + 0.3), 0.0, 0.0, (0.5, gh, 0.5), g["rgb"], material="Metal", collide=True)
        sign = g.get("sign")
        extra = {"text": sign, "faces": "F", "attrs": {"MaxDistance": 300, "Ink": [255, 255, 255]}} if sign else {}
        items_before = len(items)
        put("gb", box, 0.0, 0.0, gh - 1.2, (gw + 1.1, 1.2, 0.5), g["rgb"], **extra)
        if sign:
            items[items_before] = __import__("dataclasses").replace(items[items_before], kind="sign")
    return items
