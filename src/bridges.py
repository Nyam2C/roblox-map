"""Overpasses (2026-10-15, cells 12b·10f·177·10b 계남고가도로 and 16b 신흥고가차도): OSM roads tagged bridge=yes|viaduct on a layer
of 1 or more stand on a deck over the ground instead of lying on it.

Ways of a bridge that meet end to end are one structure (a chain). Along a chain the deck rises to DECK_M over RAMP_M from an end
that meets an at-grade road; an end that meets nothing in the data runs on off the map at full height. The street-view cameras
never stood on these decks (elevation.json has no point within 5 m), so the height is a usual overpass: 4.7 m clearance and the
deck. The road, its markings and lamps rise with the deck (terrain.lift); a girder under it, a wall on both edges and piers to the
ground are added here; trees, poles and the like of the bridge way are dropped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import h3
from shapely.geometry import LineString, Point
from shapely.ops import linemerge

import layout
from layout import Frame, Item

DECK_M = 6.5  # road top over the ground on the deck
RAMP_M = 90.0  # 7 % up from an at-grade end
GIRDER_M = 1.2
WALL_H_M, WALL_T_M = 1.0, 0.4
PIER_EVERY_M, PIER_MIN_M, PIER_W_M = 30.0, 3.0, 1.6
KEEP = ("#cl", "#dash", "#lamp", "#larm", "#lhead")  # street props a deck keeps: centre and lane lines, lamps
LOOK = dict(material="Concrete", color=(176, 174, 168), color_name="bridge_deck")


def is_bridge(feature: Mapping[str, Any]) -> bool:
    tags = feature.get("tags") or {}
    try:
        layer = int(str(tags.get("layer", "1")))
    except ValueError:
        layer = 1
    return feature.get("kind") == "road" and tags.get("bridge") in ("yes", "viaduct") and layer >= 1


@dataclass
class Chain:
    line: LineString  # east/north metres
    ramp0: bool
    ramp1: bool

    def offset_m(self, east: float, north: float) -> float:
        s = self.line.project(Point(east, north))
        r = 1.0
        if self.ramp0:
            r = min(r, s / RAMP_M)
        if self.ramp1:
            r = min(r, (self.line.length - s) / RAMP_M)
        return DECK_M * max(0.0, r)


class Decks:
    """The bridge chains of a region, from all its road features (every cell must see the whole chain to get the same deck)."""

    keep = KEEP

    def __init__(self, features: Sequence[Mapping[str, Any]], frame: Frame, cfg: Mapping[str, Any]):
        self.frame = frame
        ways: dict[str, Mapping[str, Any]] = {}
        for f in features:
            if f.get("kind") == "road":
                ways.setdefault(str(f["feature_id"]), f)
        bridges = {fid: f for fid, f in ways.items() if is_bridge(f)}
        pts = {fid: [layout.to_meters(frame, p[0], p[1]) for p in f["geometry"]] for fid, f in bridges.items()}
        ends = {fid: (tuple(f["geometry"][0]), tuple(f["geometry"][-1])) for fid, f in bridges.items()}
        group = {fid: fid for fid in bridges}

        def root(a: str) -> str:
            while group[a] != a:
                group[a] = group[group[a]]
                a = group[a]
            return a

        for a in sorted(bridges):
            for b in sorted(bridges):
                if a < b and set(ends[a]) & set(ends[b]):
                    group[root(a)] = root(b)
        at_grade = {tuple(p) for fid, f in ways.items() if fid not in bridges for p in f["geometry"]}
        self.chain_of: dict[str, Chain] = {}
        for r in sorted({root(a) for a in bridges}):
            members = sorted(a for a in bridges if root(a) == r)
            merged = linemerge([LineString(pts[a]) for a in members])
            lines = [merged] if merged.geom_type == "LineString" else [LineString(pts[a]) for a in members]
            for line in lines:
                chain = Chain(line, *(self._meets(line, members, ends, at_grade, i) for i in (0, -1)))
                for a in members:
                    if len(lines) == 1 or LineString(pts[a]).equals(line):
                        self.chain_of[a] = chain
        self.widths: dict[str, float] = {fid: layout.road_width_m(bridges[fid], cfg) for fid in self.chain_of}

    def _meets(self, line: LineString, members: Sequence[str], ends: Mapping[str, tuple], at_grade: set, i: int) -> bool:
        """Whether the chain end i (0 or -1) is an end node of a member that an at-grade road also uses."""
        x, y = line.coords[i]
        for a in members:
            for node in ends[a]:
                e, n = layout.to_meters(self.frame, node[0], node[1])
                if math.hypot(e - x, n - y) < 0.05 and node in at_grade:
                    return True
        return False

    @property
    def fids(self) -> frozenset[str]:
        return frozenset(self.chain_of)

    def offset_studs(self, fid: str, x: float, z: float) -> float:
        """How far a bridge way's item at stud (x, z) rises over the ground."""
        chain = self.chain_of.get(fid)
        if chain is None:
            return 0.0
        s = self.frame.studs_per_m
        return chain.offset_m(x / s, -z / s) * s

    def over(self, x: float, z: float, margin_m: float = 1.0) -> float:
        """The deck height (studs) over stud (x, z) when it lies within a deck's width (plus margin), else 0."""
        s = self.frame.studs_per_m
        pt = Point(x / s, -z / s)
        best = 0.0
        for fid, chain in self.chain_of.items():
            if chain.line.distance(pt) <= self.widths.get(fid, 10.0) / 2 + margin_m:
                best = max(best, chain.offset_m(pt.x, pt.y) * s)
        return best


def deck_items(feature: Mapping[str, Any], frame: Frame, cell_id: str, res: int, cfg: Mapping[str, Any]) -> list[Item]:
    """The girder under the road and a wall on both edges, per owned segment of a bridge way; terrain.lift raises and tilts them."""
    fid, width, s = str(feature["feature_id"]), layout.road_width_m(feature, cfg), frame.studs_per_m
    out: list[Item] = []
    for i, p, q, mid, length in layout._segments(feature, frame, cell_id, res):
        yaw = layout._yaw_of(q[0] - p[0], q[1] - p[1])
        ux, un = (q[0] - p[0]) / length, (q[1] - p[1]) / length
        top = layout.TOPS["road"]
        out.append(layout._item("prop", f"{fid}#{i}#deck", fid, 900 + 3 * i, (mid[0] * s, -GIRDER_M * s / 2, -mid[1] * s),
                                ((length + 0.4) * s, GIRDER_M * s, (width + 0.6) * s), yaw, **LOOK))
        for k, sign in enumerate((-1, 1)):
            off = sign * (width / 2 + 0.3 - WALL_T_M / 2)
            e, n = mid[0] - un * off, mid[1] + ux * off
            out.append(layout._item("prop", f"{fid}#{i}#bw{k}", fid, 901 + 3 * i + k, (e * s, top + WALL_H_M * s / 2, -n * s),
                                    ((length + 0.4) * s, WALL_H_M * s, WALL_T_M * s), yaw, collide=True, **LOOK))
    return out


def pier_items(decks: Decks, features: Sequence[Mapping[str, Any]], ground: Any, cell_id: str, res: int, cfg: Mapping[str, Any]) -> list[Item]:
    """Piers every PIER_EVERY_M along a chain where the deck is PIER_MIN_M up, those standing in this cell; absolute heights."""
    frame, s = decks.frame, decks.frame.studs_per_m
    out: list[Item] = []
    widths = {str(f["feature_id"]): layout.road_width_m(f, cfg) for f in features if str(f["feature_id"]) in decks.fids}
    done: set[int] = set()
    for fid in sorted(widths):
        chain = decks.chain_of[fid]
        if id(chain) in done:
            continue
        done.add(id(chain))
        n = int(chain.line.length // PIER_EVERY_M)
        for j in range(1, n + 1):
            pt = chain.line.interpolate(j * PIER_EVERY_M)
            off = chain.offset_m(pt.x, pt.y)
            lat, lon = layout.from_studs(frame, pt.x * s, -pt.y * s)
            if off < PIER_MIN_M or h3.latlng_to_cell(lat, lon, res) != cell_id:
                continue
            a, b = chain.line.interpolate(max(0.0, j * PIER_EVERY_M - 1)), chain.line.interpolate(j * PIER_EVERY_M + 1)
            yaw = layout._yaw_of(b.x - a.x, b.y - a.y)
            x, z = pt.x * s, -pt.y * s
            g = ground.h(x, z) if ground is not None else 0.0
            bottom, top = g - 1.0, g + (off - GIRDER_M) * s + 0.1
            out.append(layout._item("prop", f"{fid}#pier{j}", fid, 990 + j, (x, (bottom + top) / 2, z),
                                    (PIER_W_M * s, top - bottom, max(2.0, 0.55 * widths[fid]) * s), yaw, **LOOK))
    return out
