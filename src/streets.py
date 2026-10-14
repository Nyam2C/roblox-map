"""U5 streets (split out of layout_details.py in U7 B): junctions, sidewalk pieces, markings, crosswalks, street props and the
satellite trees.

No input or output except load_trees. Every number is computed here in metres and handed to layout.Item in studs (U2 BR-7.5).
Rules: aidlc-docs/construction/u5-details/functional-design/business-rules.md (BR-11, BR-12). Variety comes only from
details_rules.pick (BR-14.8).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import h3
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

import details_rules as R
import kits
import layout
from layout import Frame, Item
from layout_details import D, _part, _studs

CROSSWALK_CLASSES = ("tertiary", "residential")
POLE_CLASSES = ("living_street", "residential", "service")
LAMP_CLASSES = ("tertiary", "residential")
CAR_CLASSES = ("living_street", "residential")


# --- streets: junctions, sidewalk pieces, markings, crosswalks, props (BR-11) ----------------------------------------------

@dataclass(frozen=True)
class Arm:
    feature_id: str
    segment: int  # the segment index the arm runs along
    direction: tuple[float, float]  # unit vector away from the junction (east/north)
    length: float
    kind: str
    highway_class: str
    width: float
    forward: bool  # True: the arm runs from the vertex to the next vertex (segment = vertex index)


@dataclass(frozen=True)
class Junction:
    name: str
    lat: float
    lon: float
    east: float
    north: float
    owned: bool
    arms: tuple[Arm, ...]
    in_school_zone: bool

    @property
    def w_max(self) -> float:
        return max(a.width for a in self.arms)


@dataclass
class Street:
    """One feature's full geometry in metres with its class, width and the segments this cell owns."""
    feature: Mapping[str, Any]
    feature_id: str
    kind: str
    highway_class: str
    width: float
    pts: list[tuple[float, float]]
    owned: list[tuple[int, tuple[float, float], tuple[float, float], tuple[float, float], float]]  # (i, p, q, mid, length)
    sides: tuple[str, ...]


def streets_of(features: Sequence[Mapping[str, Any]], frame: Frame, cell_id: str, res: int, cfg: Mapping[str, Any]) -> list[Street]:
    out = []
    for f in sorted(features, key=lambda f: str(f["feature_id"])):
        if f["kind"] not in ("road", "path"):
            continue
        pts = [layout.to_meters(frame, p[0], p[1]) for p in f["geometry"] if layout._finite(p[0], p[1])]
        if len(pts) < 2:
            continue
        out.append(Street(f, str(f["feature_id"]), f["kind"], str(f.get("highway_class") or ""), layout.road_width_m(f, cfg), pts,
                          list(layout._segments(f, frame, cell_id, res)), layout.sidewalk_sides(f)))
    return out


def _school_distance(east: float, north: float, frame: Frame, cfg: Mapping[str, Any]) -> float:
    polys = [Polygon([layout.to_meters(frame, p[0], p[1]) for p in poly]) for poly in cfg.get("school_polygons") or []]
    return min((p.distance(Point(east, north)) for p in polys), default=float("inf"))


def junctions(streets: Sequence[Street], frame: Frame, cell_id: str, res: int, cfg: Mapping[str, Any]) -> list[Junction]:
    """Shared vertices of two or more features (lat/lon rounded to 6 places), with their arms (BR-11.8)."""
    at: dict[tuple[float, float], list[tuple[Street, int]]] = {}
    for st in streets:
        for vi, p in enumerate(st.feature["geometry"]):
            if layout._finite(p[0], p[1]):
                at.setdefault((round(float(p[0]), 6), round(float(p[1]), 6)), []).append((st, vi))
    out = []
    for (lat, lon), hits in sorted(at.items()):
        if len({st.feature_id for st, _ in hits}) < 2:
            continue
        east, north = layout.to_meters(frame, lat, lon)
        arms: list[Arm] = []
        for st, vi in sorted(hits, key=lambda h: (h[0].feature_id, h[1])):
            for nxt, forward in ((vi + 1, True), (vi - 1, False)):
                if 0 <= nxt < len(st.pts):
                    dx, dy = st.pts[nxt][0] - st.pts[vi][0], st.pts[nxt][1] - st.pts[vi][1]
                    length = math.hypot(dx, dy)
                    if length >= 0.001:
                        arms.append(Arm(st.feature_id, vi if forward else nxt, (dx / length, dy / length), length, st.kind, st.highway_class, st.width, forward))
        name = f"jct:{lat:.6f}_{lon:.6f}".replace("-", "m")
        zone = _school_distance(east, north, frame, cfg) <= float(cfg["school_zone_m"])
        out.append(Junction(name, lat, lon, east, north, h3.latlng_to_cell(lat, lon, res) == cell_id, tuple(arms), zone))
    return out


def _segment_part(frame: Frame, kind: str, name: str, group: str, seq: int, p: tuple[float, float], u: tuple[float, float], along: float,
                  lateral: float, y: float, size: tuple[float, float, float], *, y_studs: bool = False, **extra: Any) -> Item:
    """A part on a segment: `along` metres from p, `lateral` metres to the left of the direction u; size = (along, height, across)."""
    east, north = p[0] + u[0] * along - u[1] * lateral, p[1] + u[1] * along + u[0] * lateral
    yaw = math.degrees(math.atan2(u[1], u[0]))
    if y_studs:
        s = frame.studs_per_m
        x, z = _studs(frame, east, north)
        return layout._item(kind, name, group, seq, (x, y, z), (size[0] * s, size[1], size[2] * s), yaw % 360.0, **extra)
    return _part(frame, kind, name, group, seq, east, north, y, size, yaw, **extra)


def _junction_positions(st: Street, jcts: Sequence[Junction]) -> list[tuple[int, float, Junction]]:
    """(segment index, along metres, junction) of every junction on this street's owned segments (either end)."""
    out = []
    for i, p, q, _, length in st.owned:
        for j in jcts:
            for a in j.arms:
                if a.feature_id == st.feature_id and a.segment == i:
                    out.append((i, 0.0 if a.forward else length, j))
                    break
    return sorted(out, key=lambda t: (t[0], t[1], t[2].name))


def _slots(length: float, spacing: float, clear: Sequence[float], clear_dist: float) -> list[tuple[int, float]]:
    if spacing < 1.0:  # 0 means "none" (BR-11.1); anything under a metre is treated the same so a config typo cannot make millions of slots
        return []
    out, j, pos = [], 0, spacing / 2
    while pos < length - 1e-9:
        if all(abs(pos - c) > clear_dist for c in clear):
            out.append((j, pos))
        j += 1
        pos = spacing / 2 + j * spacing
    return out


def carriageways(streets: Sequence[Street]) -> dict[str, Any]:
    """Each road's carriageway as a polygon in metres (flat ends), by feature id."""
    return {st.feature_id: LineString(st.pts).buffer(st.width / 2, cap_style=2) for st in streets if st.kind == "road" and len(st.pts) >= 2}


def others_of(st: Street, ways: Mapping[str, Any]) -> Any:
    """The carriageways of every road but this one (None when there are none)."""
    rest = [g for fid, g in sorted(ways.items()) if fid != st.feature_id]
    return unary_union(rest) if rest else None


def paths_off_roads(features: Sequence[Mapping[str, Any]], frame: Frame, cfg: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The features with every footpath cut where it crosses a road's carriageway (173, 2026-10-14: a pedestrian street drawn
    straight across a road covered the carriageway). A cut path becomes pieces "<id>.<n>"; roads and untouched paths stay as they are."""
    roads = [f for f in features if f["kind"] == "road"]
    ways = carriageways(streets_of(roads, frame, "", 0, cfg)) if roads else {}
    if not ways:
        return list(features)
    blocked = unary_union(list(ways.values())).buffer(0.3)
    s = frame.studs_per_m
    out: list[Mapping[str, Any]] = []
    for f in features:
        if f["kind"] != "path":
            out.append(f)
            continue
        pts = [layout.to_meters(frame, p[0], p[1]) for p in f["geometry"] if layout._finite(p[0], p[1])]
        if len(pts) < 2 or not LineString(pts).intersects(blocked):
            out.append(f)
            continue
        rest = LineString(pts).difference(blocked)
        parts = [g for g in getattr(rest, "geoms", [rest]) if g.geom_type == "LineString" and g.length >= 1.0]
        for n, g in enumerate(parts):
            geometry = [list(layout.from_studs(frame, e * s, -nn * s)) for e, nn in g.coords]
            out.append({**f, "feature_id": f"{f['feature_id']}.{n}", "geometry": geometry})
    return out


def _clear_spans(p: tuple[float, float], u: tuple[float, float], s0: float, s1: float, lat0: float, lat1: float,
                 blocked: Any) -> list[tuple[float, float]]:
    """Parts of [s0, s1] along the segment where the band from lat0 to lat1 metres left of it meets no blocked carriageway (2026-10-14:
    sidewalks of one carriageway ran across the other half of a divided road and across slip lanes)."""
    if blocked is None:
        return [(s0, s1)]
    step, keep, out, start = D["clip_step"], [], [], None
    n = max(1, int(math.ceil((s1 - s0) / step)))
    for k in range(n + 1):
        s = s0 + (s1 - s0) * k / n
        a = (p[0] + u[0] * s - u[1] * lat0, p[1] + u[1] * s + u[0] * lat0)
        b = (p[0] + u[0] * s - u[1] * lat1, p[1] + u[1] * s + u[0] * lat1)
        keep.append(LineString([a, b]).intersection(blocked).length <= D["clip_overlap"])
    if all(keep):
        return [(s0, s1)]  # exactly: a whole piece is recognised by its ends
    for k, ok in enumerate(keep):
        s = s1 if k == n else s0 + (s1 - s0) * k / n
        if ok and start is None:
            start = s
        if (not ok or k == n) and start is not None:
            end = s if ok else s0 + (s1 - s0) * (k - 0.5) / n
            out.append((start, end))
            start = None
    return out


def _on_other_road(blocked: Any, p: tuple[float, float], u: tuple[float, float], pos: float, lat: float) -> bool:
    """True when the point `pos` along and `lat` left of the segment lies on (or within a metre of) another road's carriageway."""
    if blocked is None:
        return False
    return blocked.distance(Point(p[0] + u[0] * pos - u[1] * lat, p[1] + u[1] * pos + u[0] * lat)) < 1.0


def sidewalk_pieces(st: Street, jcts: Sequence[Junction], frame: Frame, cfg: Mapping[str, Any],
                    blocked: Any = None) -> list[tuple[int, str, int, float, float]]:
    """(segment, side, piece index, start, end) of the sidewalk pieces after the alley-mouth gaps (BR-11.10) and away from other
    roads' carriageways: a span is cut where the band from the road edge to the sidewalk's outer edge plus median_margin meets
    another carriageway, so the median of a divided road and the islands between slip lanes get no sidewalk (2026-10-14)."""
    out = []
    jpos = _junction_positions(st, jcts)
    for i, p, q, mid, length in st.owned:
        u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
        for side in st.sides:
            gaps: list[tuple[float, float]] = []
            for si, pos, j in jpos:
                if si != i:
                    continue
                for a in j.arms:
                    if a.feature_id == st.feature_id:
                        continue
                    cross = u[0] * a.direction[1] - u[1] * a.direction[0]
                    if abs(cross) < D["collinear_sin"]:
                        continue
                    if (cross > 0) != (side == "L"):
                        continue
                    g = a.width + D["gap_extra"]
                    gaps.append((pos - g / 2, pos + g / 2))
            pieces = [(0.0, length)]
            for a, b in sorted(gaps):
                new = []
                for s0, s1 in pieces:
                    if b <= s0 or a >= s1:
                        new.append((s0, s1))
                    else:
                        if a > s0:
                            new.append((s0, a))
                        if b < s1:
                            new.append((b, s1))
                pieces = new
            sign = 1.0 if side == "L" else -1.0
            sw = float(cfg["sidewalk_width_m"])
            pieces = [c for s0, s1 in pieces
                      for c in _clear_spans(p, u, s0, s1, sign * (st.width / 2 + 0.05), sign * (st.width / 2 + sw + D["median_margin"]), blocked)]
            for k, (s0, s1) in enumerate(pc for pc in pieces if pc[1] - pc[0] >= D["piece_min"]):
                out.append((i, side, k, s0, s1))
    return out


TREE_SPAN = 7.2  # width in metres of the street-tree crown cluster at scale 1 (BR-11.4a)


def load_trees(path: Path) -> list[list[float]] | None:
    """The rows (x, z, crown diameter m) of a cell's trees.json made by trees.py, or None when there is no file (the rule-based trees stay)."""
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))["trees"]
    return [[float(v) for v in r] for r in rows if len(r) == 3 and all(math.isfinite(float(v)) for v in r)]


def tree_items(frame: Frame, trees: Sequence[Sequence[float]]) -> list[Item]:
    """The trees read off the satellite photo: a trunk and a crown kit mesh (U7 H; it was three balls) scaled to the crown diameter,
    turned by hash (BR-11.4a)."""
    out: list[Item] = []
    for n, (x, z, dia) in enumerate(trees):
        name = f"sat#{n}#tree"
        east, north = x / frame.studs_per_m, -z / frame.studs_per_m
        sc = min(1.1, max(0.55, dia / TREE_SPAN))  # big satellite crowns hid the houses (review 2026-10-13)
        yaw = 45.0 * R.pick(name, "yaw", 8)
        ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        leaf = R.TREE_LEAVES[R.pick(name, "leaf", len(R.TREE_LEAVES))]
        out.append(_part(frame, "prop", name, "sat", n, east, north, 0.0, (D["trunk_h"] * sc, D["trunk_dia"] * max(sc, 0.8), D["trunk_dia"] * max(sc, 0.8)), yaw,
                         shape="Cylinder", material="Wood", color=R.PALETTE["trunk"], color_name="trunk"))
        kit = sorted(kits.CROWNS)[R.pick(name, "tree", len(kits.CROWNS))]  # U7 H: one crown mesh instead of three balls
        da, dl, y0, size = kits.crown_box(kit)
        da, dl, y0 = da * sc, dl * sc, y0 * sc
        out.append(_part(frame, "prop", f"sat#{n}#crown", "sat", n, east + da * ca - dl * sa, north + da * sa + dl * ca, y0,
                         tuple(v * sc for v in size), yaw, material="LeafyGrass", color=R.PALETTE[leaf], color_name=leaf, collide=False, kit=kit))
    return out


def street_items(streets: Sequence[Street], jcts: Sequence[Junction], frame: Frame, cfg: Mapping[str, Any],
                 rule_trees: bool = True) -> tuple[list[Item], list[Item]]:
    """(sidewalk pieces replacing U2's, props: curbs, markings, crosswalks, poles, wires, lamps, trees, cars, zone kit, bollards, boxes).

    rule_trees=False leaves the street trees out (the cell has trees read off the satellite photo, see tree_items)."""
    sidewalks: list[Item] = []
    props: list[Item] = []
    s = frame.studs_per_m
    sw = float(cfg["sidewalk_width_m"])
    top_road, top_side = layout.TOPS["road"], layout.TOPS["sidewalk"]
    by_id = {st.feature_id: st for st in streets}
    ways = carriageways(streets)
    for st in streets:
        fid, w = st.feature_id, st.width
        blocked = others_of(st, ways)
        jpos = _junction_positions(st, jcts)
        clear = {i: [pos for si, pos, _ in jpos if si == i] for i, *_ in st.owned}
        # sidewalks and curbs (BR-11.10, BR-11.6)
        pieces = sidewalk_pieces(st, jcts, frame, cfg, blocked)
        for i, side, k, s0, s1 in pieces:
            _, p, q, _, length = next(seg for seg in st.owned if seg[0] == i)
            u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
            sign = 1.0 if side == "L" else -1.0
            whole = (s0 == 0.0 and s1 == length)
            ext = sw if whole else 0.0
            sidewalks.append(_segment_part(frame, "sidewalk", f"{fid}#{i}{side}.{k}", fid, 2 * i + (side == "R"), p, u, (s0 + s1) / 2,
                                           sign * (w / 2 + sw / 2), top_side / 2, (s1 - s0 + ext, top_side, sw), y_studs=True))
            props.append(_segment_part(frame, "prop", f"{fid}#{i}#curb{side}{k}", fid, 10 * i + k, p, u, (s0 + s1) / 2, sign * (w / 2 + D["curb_in"]),
                                       D["curb_h_studs"] / 2, (s1 - s0, D["curb_h_studs"], D["curb_w"]), y_studs=True, material="Granite",
                                       color=R.PALETTE["curb"], color_name="curb"))
            # school-zone guard fence (BR-11.11)
            mid_e = p[0] + u[0] * (s0 + s1) / 2 - u[1] * sign * (w / 2 + sw / 2)
            mid_n = p[1] + u[1] * (s0 + s1) / 2 + u[0] * sign * (w / 2 + sw / 2)
            opp_e = p[0] + u[0] * (s0 + s1) / 2 + u[1] * sign * (w / 2 + sw / 2)
            opp_n = p[1] + u[1] * (s0 + s1) / 2 - u[0] * sign * (w / 2 + sw / 2)
            dist = _school_distance(mid_e, mid_n, frame, cfg)
            if dist <= float(cfg["school_zone_m"]) and dist <= _school_distance(opp_e, opp_n, frame, cfg):
                pos = s0 + D["fence_len"] / 2
                n = 0
                while pos + D["fence_len"] / 2 <= s1 - D["fence_end_clear"] + 1e-9:
                    if pos - D["fence_len"] / 2 >= s0 + D["fence_end_clear"] - 1e-9:
                        props.append(_segment_part(frame, "prop", f"{fid}#{i}#gf{side}{k}-{n}", fid, 100 + 10 * i + n, p, u, pos, sign * (w / 2 + D["fence_off"]), 0.0,
                                                   (D["fence_len"], D["fence_h"], D["fence_t"]), material="Metal", color=R.PALETTE["fence_zone"],
                                                   color_name="fence_zone", collide=False))
                        n += 1
                    pos += D["fence_len"]
        # markings (BR-11.7)
        oneway = str((st.feature.get("tags") or {}).get("oneway") or "").strip().lower() == "yes"
        for i, p, q, mid, length in st.owned:
            u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
            # lines stop at the widest road of the junction at each end, not inside it (2026-10-14: a lane's centre line ran into 신흥로)
            cw = D["cw_to"] if st.highway_class in CROSSWALK_CLASSES else 0.0  # and before the crosswalk band on this arm
            t0 = max([w / 2] + [j.w_max / 2 + cw for si, pos, j in jpos if si == i and pos < 1e-6])
            t1 = max([w / 2] + [j.w_max / 2 + cw for si, pos, j in jpos if si == i and pos > length - 1e-6])
            if st.highway_class == "residential" and not oneway and length > t0 + t1:
                for n, lat in enumerate((D["line_gap"], -D["line_gap"])):
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#cl{n}", fid, 200 + 2 * i + n, p, u, (t0 + length - t1) / 2, lat, top_road + D["mark_y_studs"],
                                               (length - t0 - t1, D["mark_t_studs"], D["line_w"]), y_studs=True, material="SmoothPlastic",
                                               color=R.PALETTE["line_yellow"], color_name="line_yellow", collide=False))
            if st.highway_class == "tertiary":
                pos, n = t0, 0
                while pos + D["dash_len"] <= length - t1:
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#dash{n}", fid, 300 + 10 * i + n, p, u, pos + D["dash_len"] / 2, 0.0,
                                               top_road + D["mark_y_studs"], (D["dash_len"], D["mark_t_studs"], D["line_w"]), y_studs=True,
                                               material="SmoothPlastic", color=R.PALETTE["line_white"], color_name="line_white", collide=False))
                    pos += D["dash_len"] + D["dash_gap"]
                    n += 1
        # poles and wires (BR-11.2)
        pole_tops: list[tuple[float, float]] = []
        lamp_slots: dict[str, list[tuple[int, float]]] = {"L": [], "R": []}
        pole_slots: list[tuple[int, float]] = []
        if st.highway_class in POLE_CLASSES:
            for i, p, q, mid, length in st.owned:
                u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
                for j, pos in _slots(length, float(cfg["pole_spacing_m"]), clear[i], D["slot_junction_clear"]):
                    lat = -(w / 2 + D["pole_off"])
                    if _on_other_road(blocked, p, u, pos, lat):
                        continue
                    name = f"{fid}#{i}#pole{j}"
                    props.append(_segment_part(frame, "prop", name, fid, 400 + 10 * i + j, p, u, pos, lat, 0.0, (D["pole_h"], D["pole_dia"], D["pole_dia"]),
                                               shape="Cylinder", material="Concrete", color=R.PALETTE["pole"], color_name="pole"))
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#arm{j}", fid, 400 + 10 * i + j, p, u, pos, lat, D["arm_y"], (D["arm_t"], D["arm_t"], D["arm_w"]),
                                               material="Concrete", color=R.PALETTE["pole"], color_name="pole", collide=False))
                    if j % 3 == 2:
                        props.append(_segment_part(frame, "prop", f"{fid}#{i}#tr{j}", fid, 400 + 10 * i + j, p, u, pos, lat, D["transformer_y"],
                                                   (D["transformer_h"], D["transformer_dia"], D["transformer_dia"]), shape="Cylinder", material="Metal",
                                                   color=R.PALETTE["transformer"], color_name="transformer", collide=False))
                    pole_tops.append((p[0] + u[0] * pos - u[1] * lat, p[1] + u[1] * pos + u[0] * lat))
                    pole_slots.append((i, pos))
            for n, (a, b) in enumerate(zip(pole_tops, pole_tops[1:])):
                dx, dy = b[0] - a[0], b[1] - a[1]
                span = math.hypot(dx, dy)
                if 0.001 < span <= D["wire_max_span"]:
                    for m, y in enumerate((D["wire_y1"], D["wire_y2"])):
                        props.append(_part(frame, "prop", f"{fid}#wire{n}-{m}", fid, 500 + 2 * n + m, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, y,
                                           (span, D["wire_t"], D["wire_t"]), math.degrees(math.atan2(dy, dx)), y_center=True, material="SmoothPlastic",
                                           color=R.PALETTE["wire"], color_name="wire", collide=False))
        # lamps (BR-11.3)
        if st.highway_class in LAMP_CLASSES:
            for i, p, q, mid, length in st.owned:
                u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
                for j, pos in _slots(length, float(cfg["lamp_spacing_m"]), clear[i], D["slot_junction_clear"]):
                    side = "L" if j % 2 == 0 else "R"
                    sign = 1.0 if side == "L" else -1.0
                    lat = sign * (w / 2 + sw - D["lamp_in"])
                    if _on_other_road(blocked, p, u, pos, lat):
                        continue
                    lamp_slots[side].append((i, pos))
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#lamp{j}", fid, 600 + 10 * i + j, p, u, pos, lat, 0.0, (D["lamp_h"], D["lamp_dia"], D["lamp_dia"]),
                                               shape="Cylinder", material="Metal", color=R.PALETTE["lamp_post"], color_name="lamp_post"))
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#larm{j}", fid, 600 + 10 * i + j, p, u, pos, lat - sign * D["lamp_arm"] / 2, D["lamp_arm_y"],
                                               (D["arm_t"], D["arm_t"], D["lamp_arm"]), material="Metal", color=R.PALETTE["lamp_post"], color_name="lamp_post", collide=False))
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#lhead{j}", fid, 600 + 10 * i + j, p, u, pos, lat - sign * D["lamp_arm"], D["lamp_arm_y"],
                                               (D["lamp_head_w"], D["lamp_head_h"], D["lamp_head_d"]), material="SmoothPlastic", color=R.PALETTE["lamp_head"],
                                               color_name="lamp_head", collide=False))
        # trees (BR-11.4)
        if st.sides and rule_trees:
            for i, p, q, mid, length in st.owned:
                u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
                for side in st.sides:
                    sign = 1.0 if side == "L" else -1.0
                    avoid = [pos for si, pos in lamp_slots[side] if si == i] + ([pos for si, pos in pole_slots if si == i] if side == "R" else [])
                    for j, pos in _slots(length, float(cfg["tree_spacing_m"]), clear[i], D["slot_junction_clear"]):
                        if any(abs(pos - a) <= D["tree_clear"] for a in avoid):
                            continue
                        lat = sign * (w / 2 + D["tree_off"])
                        if _on_other_road(blocked, p, u, pos, lat):
                            continue
                        name = f"{fid}#{i}#tree{side}{j}"
                        crown = R.TREE_CROWNS[R.pick(name, "tree", len(R.TREE_CROWNS))]
                        leaf = R.TREE_LEAVES[R.pick(name, "leaf", len(R.TREE_LEAVES))]
                        props.append(_segment_part(frame, "prop", name, fid, 700 + 100 * i + j, p, u, pos, lat, 0.0, (D["trunk_h"], D["trunk_dia"], D["trunk_dia"]),
                                                   shape="Cylinder", material="Wood", color=R.PALETTE["trunk"], color_name="trunk"))
                        for k, (da, dl, cy, dia) in enumerate(crown):
                            props.append(_segment_part(frame, "prop", f"{fid}#{i}#crown{side}{j}{'abc'[k]}", fid, 700 + 100 * i + j, p, u, pos + da, lat + dl, cy - dia / 2,
                                                       (dia, dia, dia), shape="Ball", material="LeafyGrass", color=R.PALETTE[leaf], color_name=leaf, collide=False))
        # parked cars (BR-11.5)
        if st.highway_class in CAR_CLASSES and w >= D["car_min_width"] and float(cfg["car_spacing_m"]) > 0:
            spacing = float(cfg["car_spacing_m"]) * (D["car_residential"] if st.highway_class == "residential" else 1.0)
            cw_pos = {i: [] for i, *_ in st.owned}
            for si, pos, j in jpos:
                if st.highway_class in CROSSWALK_CLASSES:
                    cw_pos[si].append(pos)
            for i, p, q, mid, length in st.owned:
                u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
                for j, pos in _slots(length, spacing, clear[i], D["slot_junction_clear"]):
                    if any(abs(pos - c) <= j_w_max_band(st, jcts, c) + D["car_crosswalk_clear"] for c in cw_pos[i]):
                        continue
                    name = f"{fid}#{i}#car{j}"
                    key = ("car_white",) * 5 + ("car_silver",) * 2 + ("car_black", "car_gray", "car_blue")
                    color_key = key[R.pick(name, "car", 10)]
                    rgb = R.PALETTE[color_key]
                    lat = -(w / 2 - D["car_in"])
                    props.append(_segment_part(frame, "prop", name, fid, 800 + 10 * i + j, p, u, pos, lat, D["car_y"], (D["car_w"], D["car_h"], D["car_d"]),
                                               material="SmoothPlastic", color=rgb, color_name=color_key, collide=True))
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#cab{j}", fid, 800 + 10 * i + j, p, u, pos, lat, D["car_y"] + D["car_h"], (D["cab_w"], D["cab_h"], D["cab_d"]),
                                               material="SmoothPlastic", color=tuple(int(round(c * 0.7)) for c in rgb), color_name=color_key + "_cab", collide=True))
    # junction kits: crosswalks, stop lines, zone poles, bollards, boxes (BR-11.9, BR-11.12)
    placed: list[tuple[float, float, float, float]] = []  # crosswalk centres and arm directions: a divided road has several junctions at one crossing (2026-10-14)
    for j in jcts:
        if not j.owned:
            continue
        for ai, a in enumerate(j.arms):
            u = a.direction
            p = (j.east, j.north)
            start = j.w_max / 2 + D["cw_from"]
            along = start + (D["cw_to"] - D["cw_from"]) / 2
            # 2026-10-14: the short link between the two halves of a divided road got crosswalks in the middle of the other road
            on_other = any(g.distance(Point(p[0] + u[0] * along, p[1] + u[1] * along)) < 0.5 for fid, g in ways.items() if fid != a.feature_id)
            centre = (p[0] + u[0] * along, p[1] + u[1] * along)
            # a crosswalk side by side with an earlier one (parallel arms within cw_merge) is the same crossing seen from a second junction
            near = any(math.hypot(centre[0] - c[0], centre[1] - c[1]) < D["cw_merge"] and abs(u[0] * c[2] + u[1] * c[3]) > 0.9 for c in placed)
            if a.highway_class in CROSSWALK_CLASSES and a.length >= D["cw_min_arm"] and not on_other and not near and _crossing(j):
                placed.append((centre[0], centre[1], u[0], u[1]))
                n = int(a.width // D["cw_pitch"])
                for i in range(n):
                    lat = (i - (n - 1) / 2) * D["cw_pitch"]
                    key = "line_yellow" if j.in_school_zone and i % 2 == 0 else "line_white"
                    props.append(_segment_part(frame, "prop", f"{j.name}#cw{ai}-{i}", j.name, 10 * ai + i, p, u, along, lat, top_road + D["cw_y_studs"],
                                               (D["cw_len"], D["mark_t_studs"], D["cw_stripe"]), y_studs=True, material="SmoothPlastic", color=R.PALETTE[key],
                                               color_name=key, collide=False))
                props.append(_segment_part(frame, "prop", f"{j.name}#sl{ai}", j.name, 10 * ai + 9, p, u, start + D["cw_to"] - D["cw_from"] + D["stop_gap"] + D["stop_w"] / 2,
                                           a.width / 4, top_road + D["cw_y_studs"], (D["stop_w"], D["mark_t_studs"], a.width / 2), y_studs=True,
                                           material="SmoothPlastic", color=R.PALETTE["line_white"], color_name="line_white", collide=False))
                if j.in_school_zone:
                    lat = -(a.width / 2 + D["zone_pole_off"])
                    props.append(_segment_part(frame, "prop", f"{j.name}#zp{ai}", j.name, 100 + ai, p, u, j.w_max / 2, lat, 0.0,
                                               (D["zone_pole_h"], D["zone_pole_dia"], D["zone_pole_dia"]), shape="Cylinder", material="Metal",
                                               color=R.PALETTE["pole_zone"], color_name="pole_zone"))
                    props.append(_segment_part(frame, "prop", f"{j.name}#zs{ai}", j.name, 100 + ai, p, u, j.w_max / 2, lat, D["zone_pole_h"],
                                               (D["fence_t"], D["zone_sign"], D["zone_sign"]), material="SmoothPlastic", color=R.PALETTE["pole_zone"],
                                               color_name="pole_zone", collide=False))
            if a.kind == "path" and any(o.kind == "road" for o in j.arms):
                for i, lat in enumerate((-D["bollard_gap"], 0.0, D["bollard_gap"])):
                    # past the widest road's edge, not on its carriageway (173, 2026-10-14: the bollards stood in the road)
                    road_w = max((o.width for o in j.arms if o.kind == "road"), default=0.0)
                    props.append(_segment_part(frame, "prop", f"{j.name}#bol{ai}-{i}", j.name, 200 + 10 * ai + i, p, u, road_w / 2 + D["bollard_in"], lat, 0.0,
                                               (D["bollard_h"], D["bollard_dia"], D["bollard_dia"]), shape="Cylinder", material="Metal",
                                               color=R.PALETTE["bollard"], color_name="bollard"))
        if j.arms and all(a.highway_class in ("living_street", "service") for a in j.arms):
            a = j.arms[0]
            telecom = R.pick(j.name, "box", 2) == 0
            size = (D["box_telecom_w"], D["box_telecom_h"], D["box_telecom_d"]) if telecom else (D["box_recycle_w"], D["box_recycle_h"], D["box_recycle_d"])
            key = "box_telecom" if telecom else "box_recycle"
            props.append(_segment_part(frame, "prop", f"{j.name}#box0", j.name, 300, (j.east, j.north), a.direction, j.w_max / 2 + D["box_along"],
                                       -(a.width / 2 + D["box_off"]), 0.0, size, material="Metal", color=R.PALETTE[key], color_name=key))
    return sidewalks, props


def _crossing(j: Junction) -> bool:
    """A real crossing: two of its arms meet at cw_cross_deg or more. A slip lane joining a big road at a shallow angle is not one and
    gets no crosswalks (cell 4, 2026-10-14: crosswalks across 길주로 at every merge point)."""
    for k, a in enumerate(j.arms):
        for b in j.arms[k + 1:]:
            c = abs(a.direction[0] * b.direction[0] + a.direction[1] * b.direction[1])
            if math.degrees(math.acos(min(1.0, c))) >= D["cw_cross_deg"]:
                return True
    return False


def j_w_max_band(st: Street, jcts: Sequence[Junction], pos: float) -> float:
    """How far from a junction on this street the crosswalk band reaches (BR-11.5 uses it to keep cars off crosswalks)."""
    for j in jcts:
        if any(a.feature_id == st.feature_id for a in j.arms):
            return j.w_max / 2 + D["cw_to"]
    return D["cw_to"]


# --- subway entrances (OSM railway=subway_entrance, 2026-10-14 cell 4) ----------------------------------------------------------

ENTRANCE = {"len": 9.0, "wid": 3.6, "h": 3.0, "landing": 1.2, "gap": 0.5, "nose_pitch": 0.45, "noses": 6}
# A glass box over a stair that goes down at the closed end (신중동역 street view: aluminium frame, glass walls and roof, the exit
# number over the open end). The ground is one slab, so the stair is a dark well with step noses fading into it, not a real descent
# (no interiors, user decision 2026-10-14). Reference measured: creator store 11939324887 (NYC style: 23 x 34 stud well, 4 stud rail).


def entrance_items(entrances: Sequence[Mapping[str, Any]], streets_: Sequence[Street], frame: Frame, cell_id: str, res: int) -> list[Item]:
    """Glass entrance boxes for the subway entrances inside the cell. Each runs along the nearest road, its open end away from the
    middle of all the given entrances (the neighbours' too: the stair goes down toward the station), pushed clear of the carriageway."""
    E = ENTRANCE
    pts = {str(f["feature_id"]): layout.to_meters(frame, *f["geometry"][0]) for f in entrances}
    if not pts:
        return []
    cx, cy = sum(p[0] for p in pts.values()) / len(pts), sum(p[1] for p in pts.values()) / len(pts)
    segs = [(st, st.pts[i], st.pts[i + 1]) for st in streets_ if st.kind == "road" for i in range(len(st.pts) - 1)]
    out: list[Item] = []
    for fid, (px, py) in sorted(pts.items()):
        f = next(f for f in entrances if str(f["feature_id"]) == fid)
        if h3.latlng_to_cell(f["geometry"][0][0], f["geometry"][0][1], res) != cell_id:
            continue
        ux, uy, near = 1.0, 0.0, None
        for st, a, b in segs:
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            if L < 1e-6:
                continue
            tx, ty = dx / L, dy / L
            t = max(0.0, min(L, (px - a[0]) * tx + (py - a[1]) * ty))
            d = math.hypot(px - (a[0] + tx * t), py - (a[1] + ty * t))
            if near is None or d < near[0]:
                near = (d, tx, ty, (px - a[0]) * -ty + (py - a[1]) * tx, st.width)  # last: signed distance, left of the road positive
        if near is not None:
            _, ux, uy, s, w = near
            need = w / 2 + E["wid"] / 2 + E["gap"]
            if abs(s) < need:  # on the carriageway: move it out to the side it stands on
                side = 1.0 if s >= 0 else -1.0
                px, py = px + side * (need - abs(s)) * -uy, py + side * (need - abs(s)) * ux
        if (px - cx) * ux + (py - cy) * uy < 0:
            ux, uy = -ux, -uy
        vx, vy = -uy, ux  # left of the stair
        yaw = math.degrees(math.atan2(uy, ux))
        seq = 0
        ref = str((f.get("tags") or {}).get("ref", ""))
        Lh, Wh, H = E["len"] / 2, E["wid"] / 2, E["h"]

        def put(tail: str, a: float, b: float, y: float, size: tuple[float, float, float], color: str, material: str, **kw: Any) -> None:
            nonlocal seq
            out.append(_part(frame, "prop", f"{fid}#{tail}", fid, seq, px + ux * a + vx * b, py + uy * a + vy * b, y, size, yaw,
                             material=material, color=R.PALETTE[color], color_name=color, **kw))
            seq += 1

        glass = dict(transparency=0.6, reflectance=0.1)
        for side, b in (("l", Wh), ("r", -Wh)):
            put(f"cb{side}", 0.0, b * 0.97, 0.0, (E["len"], 0.3, 0.2), "sub_floor", "Granite")
            put(f"gw{side}", 0.0, b, 0.3, (E["len"], H - 0.3, 0.05), "sub_glass", "Glass", **glass)
            put(f"fa{side}", 0.0, b + 0.12 * (1 if b > 0 else -1), H - 0.25, (E["len"] + 0.3, 0.3, 0.1), "sub_frame", "Metal")
            for k, a in enumerate((-Lh, -Lh / 3, Lh / 3, Lh)):
                put(f"po{side}{k}", a, b, 0.0, (0.12, H, 0.12), "sub_frame", "Metal")
        put("cbb", -Lh + 0.1, 0.0, 0.0, (0.2, 0.3, E["wid"]), "sub_floor", "Granite")
        put("gwb", -Lh, 0.0, 0.3, (0.05, H - 0.3, E["wid"]), "sub_glass", "Glass", **glass)
        put("rf", 0.0, 0.0, H, (E["len"] + 0.3, 0.08, E["wid"] + 0.3), "sub_glass", "Glass", transparency=0.5, reflectance=0.1)
        put("faf", Lh + 0.12, 0.0, H - 0.3, (0.1, 0.4, E["wid"] + 0.3), "sub_frame", "Metal")
        put("ld", Lh - E["landing"] / 2, 0.0, 0.0, (E["landing"], 0.04, E["wid"] - 0.4), "sub_floor", "Granite")
        well = E["len"] - E["landing"] - 0.2
        put("wl", Lh - E["landing"] - well / 2, 0.0, 0.0, (well, 0.03, E["wid"] - 0.4), "sub_void", "SmoothPlastic")
        for k in range(E["noses"]):
            put(f"ns{k}", Lh - E["landing"] - E["nose_pitch"] * (k + 0.5), 0.0, 0.03, (0.08, 0.01, E["wid"] - 0.6), "sub_nose", "SmoothPlastic")
        text = f"{ref}번 출구" if R.SIGN_TEXT.fullmatch(f"{ref}번 출구") and ref.isdigit() else "출구"
        sx, sy = px + ux * (Lh + 0.2), py + uy * (Lh + 0.2)
        out.append(_part(frame, "sign", f"{fid}#ex", fid, seq, sx, sy, H - 0.75, (E["wid"] * 0.8, 0.45, 0.06), math.degrees(math.atan2(-ux, uy)),
                         material="SmoothPlastic", color=R.PALETTE["sign_plate"], color_name="sign_plate", text=text, ink="ink_yellow",
                         faces="F", attrs={"MaxDistance": 200}))
    return out


# --- trick ramps (user 2026-10-14: "도로 중간에 묘기 하고나 공중 가능하게 경사 있는거 하나씩") ------------------------------------------

RAMP = {"h": 0.6, "up": 1.1, "down": 2.4, "wid": 2.0, "min_seg": 40.0, "classes": ("residential", "tertiary", "unclassified", "living_street")}
# A kicker in the middle of one road per cell: a steep side (about 29 degrees, the scooter takes off at its lip) and a gentle landing side
# (about 14 degrees), back to back. Real beginner kickers are about 0.3 m high, 0.6-0.9 m wide, 15-30 degrees (surfertoday.com, skatepro);
# this one is 0.6 m high and 2 m wide so a rider can hit it at speed, and ScooterClient gives the launch. Parts are named <road>#rampup
# and <road>#rampdn; ScooterClient finds the kicker by that name.


def ramp_items(streets_: Sequence[Street], frame: Frame) -> list[Item]:
    """One ramp on the longest owned segment (at least min_seg) of a minor road in the cell, at its middle, on the road's centre line."""
    best = None
    for st in streets_:
        if st.kind != "road" or st.highway_class not in RAMP["classes"]:
            continue
        for i, p, q, mid, length in st.owned:
            if length >= RAMP["min_seg"] and (best is None or (length, st.feature_id) > (best[4], best[0].feature_id)):
                best = (st, i, p, q, length)
    if best is None:
        return []
    st, i, p, q, length = best
    u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
    yaw = math.degrees(math.atan2(u[1], u[0]))
    top = layout.TOPS["road"] / frame.studs_per_m  # the ramp stands on the road surface
    out = []
    for n, (tail, along, length_m, high_toward) in enumerate((("rampup", -RAMP["up"] / 2, RAMP["up"], 90.0),
                                                              ("rampdn", RAMP["down"] / 2, RAMP["down"], -90.0))):
        east, north = p[0] + u[0] * (length / 2 + along), p[1] + u[1] * (length / 2 + along)
        # a wedge is high at its local +Z end; local Z points along u at yaw + 90 and against it at yaw - 90
        out.append(_part(frame, "prop", f"{st.feature_id}#{i}#{tail}", st.feature_id, 950 + n, east, north, top, (RAMP["wid"], RAMP["h"], length_m),
                         yaw + high_toward, shape="Wedge", material="WoodPlanks", color=R.PALETTE["ramp"], color_name="ramp", collide=True))
    return out
