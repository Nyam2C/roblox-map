"""U5 pure geometry: duplicate outlines, multi-box footprints, bodies and archetypes, the road-facing side, occlusion and free
spans, roofs, bands, windows, facade elements, storefronts and yards, signs. Streets and trees are in streets.py (U7 B).

No input or output. Every number is computed here in metres and handed to layout.Item in studs (U2 BR-7.5); studio/ServerStorage/MapBuilder.luau
only makes parts. Rules: aidlc-docs/construction/u5-details/functional-design/business-rules.md (BR-1 to BR-6, BR-8 to BR-12,
BR-14.1). Variety comes only from details_rules.pick (BR-14.8).

Local frame of a box: u along the box's long side (Roblox local +X), v along its short side (Roblox local +Z); a positive yaw
turns +X toward the north, so local +Z points to (sin yaw, -cos yaw) in east/north metres. Faces: f = -Z, b = +Z, l = -X, r = +X.
`along` on a face follows BR-5.1 (seen from the road, left is negative); `out` is the distance from the wall to the part's outer
face; `y` is the bottom of a part unless the name says otherwise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import split as shapely_split

import details_rules as R
import layout
from layout import Box, Frame, Item, fmt

D = R.DIMS
SIDES = ("f", "b", "l", "r")
FACE_YAW = {"f": 0.0, "b": 180.0, "l": 90.0, "r": 270.0}  # added to the box yaw so the part's Front (-Z) faces outward
OPPOSITE = {"f": "b", "b": "f", "l": "r", "r": "l"}
NEXT_FACE = {"f": ("r", "b", "l"), "b": ("l", "f", "r"), "l": ("f", "r", "b"), "r": ("b", "l", "f")}  # BR-8.5: faces after the facing one
# Measured WedgePart / CornerWedgePart conventions (S-7, 2026-10-13): a wedge's vertical face is its +Z side and the slope
# descends toward -Z; a corner wedge's apex is its (+X, +Y, -Z) corner. Corner yaws by (sign u, sign v) of the corner (BR-4.2).
CORNER_YAW = {(1, -1): 180.0, (1, 1): 90.0, (-1, -1): 270.0, (-1, 1): 0.0}


# --- small helpers -----------------------------------------------------------------------------------------------

def _poly_m(outline: Sequence[Sequence[float]], frame: Frame) -> Polygon | None:
    pts = [layout.to_meters(frame, p[0], p[1]) for p in outline if len(p) == 2 and layout._finite(p[0], p[1])]
    if len(pts) < 3:
        return None
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if poly.area > 1e-9 else None


def _box_poly(box: Box) -> Polygon:
    c, s = math.cos(math.radians(box.yaw_deg)), math.sin(math.radians(box.yaw_deg))
    w, d = box.width_m / 2, box.depth_m / 2
    pts = [(box.cx_m + u * c + v * s, box.cy_m + u * s - v * c) for u, v in ((-w, -d), (w, -d), (w, d), (-w, d))]
    return Polygon(pts)


def _world(box: Box, u: float, v: float) -> tuple[float, float]:
    """Box-local metres (u along X, v along Z) -> east/north metres."""
    t = math.radians(box.yaw_deg)
    return box.cx_m + u * math.cos(t) + v * math.sin(t), box.cy_m + u * math.sin(t) - v * math.cos(t)


def _studs(frame: Frame, east: float, north: float) -> tuple[float, float]:
    return east * frame.studs_per_m, -north * frame.studs_per_m


@dataclass(frozen=True)
class Face:
    side: str
    c: tuple[float, float]  # local centre
    n: tuple[float, float]  # outward normal
    t: tuple[float, float]  # `along` direction (up x n)
    length: float


def face_of(box: Box, side: str) -> Face:
    w, d = box.width_m, box.depth_m
    if side == "f":
        return Face("f", (0.0, -d / 2), (0.0, -1.0), (-1.0, 0.0), w)
    if side == "b":
        return Face("b", (0.0, d / 2), (0.0, 1.0), (1.0, 0.0), w)
    if side == "l":
        return Face("l", (-w / 2, 0.0), (-1.0, 0.0), (0.0, 1.0), d)
    return Face("r", (w / 2, 0.0), (1.0, 0.0), (0.0, -1.0), d)


def _part(frame: Frame, kind: str, name: str, group: str, seq: int, east: float, north: float, y_m: float,
          size_m: tuple[float, float, float], yaw: float, *, y_center: bool = False, **extra: Any) -> Item:
    """An item from east/north metres, a bottom (or centre) height in metres and a size in metres."""
    s = frame.studs_per_m
    x, z = _studs(frame, east, north)
    up = size_m[0] if extra.get("shape") == "Cylinder" else size_m[1]  # a standing cylinder's height is its first size (BR-14.3)
    cy = y_m * s if y_center else (y_m + up / 2) * s
    return layout._item(kind, name, group, seq, (x, cy, z), (size_m[0] * s, size_m[1] * s, size_m[2] * s), yaw % 360.0, **extra)


def _box_part(frame: Frame, body: "Body", bi: int, kind: str, tail: str, seq: int, u: float, v: float, y_m: float,
              size_m: tuple[float, float, float], yaw_add: float = 0.0, **extra: Any) -> Item:
    box = body.boxes[bi]
    east, north = _world(box, u, v)
    return _part(frame, kind, f"{body.building_id}#{tail}", body.building_id, seq, east, north, y_m, size_m,
                 box.yaw_deg + yaw_add, owner=body.building_id, **extra)


def _wall_part(frame: Frame, body: "Body", bi: int, side: str, kind: str, tail: str, seq: int, along: float, y_m: float, out: float,
               size_m: tuple[float, float, float], **extra: Any) -> Item:
    """A part on a face: size = (length along the face, height, depth out of the wall); its Front faces outward."""
    box, face = body.boxes[bi], face_of(body.boxes[bi], side)
    depth = size_m[2]
    u = face.c[0] + face.t[0] * along + face.n[0] * (out - depth / 2)
    v = face.c[1] + face.t[1] * along + face.n[1] * (out - depth / 2)
    return _box_part(frame, body, bi, kind, tail, seq, u, v, y_m, size_m, FACE_YAW[side], **extra)


def _cyl(frame: Frame, body: "Body", bi: int, side: str, kind: str, tail: str, seq: int, along: float, y_m: float, out: float,
         dia: float, height: float, **extra: Any) -> Item:
    """A standing cylinder on a face: size (height, dia, dia), Builder rolls it upright (BR-14.3)."""
    box, face = body.boxes[bi], face_of(body.boxes[bi], side)
    u = face.c[0] + face.t[0] * along + face.n[0] * (out - dia / 2)
    v = face.c[1] + face.t[1] * along + face.n[1] * (out - dia / 2)
    east, north = _world(box, u, v)
    return _part(frame, kind, f"{body.building_id}#{tail}", body.building_id, seq, east, north, y_m, (height, dia, dia),
                 box.yaw_deg, owner=body.building_id, shape="Cylinder", **extra)


# --- duplicates (BR-1.2) -------------------------------------------------------------------------------------------

def dedupe_buildings(buildings: Sequence[Mapping[str, Any]], frame: Frame) -> tuple[list[Mapping[str, Any]], list[tuple[str, str]]]:
    """Drop attribute-less records that overlap another record by DUP_OVERLAP or more. Returns (kept, [(dropped, kept)])."""
    rows = sorted(buildings, key=lambda b: str(b["building_id"]))
    polys = {str(b["building_id"]): _poly_m(b["outline"], frame) for b in rows}
    dropped: dict[str, str] = {}
    for b in rows:
        bid = str(b["building_id"])
        if (b.get("building_area") or 0) > 0 or (b.get("usability_code") or ""):
            continue
        poly = polys[bid]
        if poly is None:
            continue
        for other in rows:
            oid = str(other["building_id"])
            if oid == bid or oid in dropped or polys[oid] is None:
                continue
            opoly = polys[oid]
            if not poly.bounds or poly.distance(opoly) > 0:
                continue
            smaller = min(poly.area, opoly.area)
            if smaller > 1e-9 and poly.intersection(opoly).area / smaller >= D["dup_overlap"]:
                dropped[bid] = oid
                break
    kept = [b for b in rows if str(b["building_id"]) not in dropped]
    return kept, sorted(dropped.items())


# --- multi-box footprints (BR-2) ------------------------------------------------------------------------------------

def _fit(poly: Polygon, box: Box) -> float:
    return min(1.0, poly.area / (box.width_m * box.depth_m))


def _pieces_sorted(geoms: Iterable[Any]) -> list[Polygon]:
    polys = [g for g in geoms if g.geom_type == "Polygon" and g.area > 0.01]  # a cut through a vertex leaves slivers
    return sorted(polys, key=lambda g: (round(g.centroid.x, 3), round(g.centroid.y, 3)))


def _cut(poly: Polygon, box: Box, ratio: float) -> list[Polygon] | None:
    """The best cut of `poly` along the box axes at vertex projections (BR-2.2), or None when no cut is allowed."""
    t = math.radians(box.yaw_deg)
    axes = ((math.cos(t), math.sin(t), box.width_m), (math.sin(t), -math.cos(t), box.depth_m))  # (unit vector, extent)
    best: tuple[float, float, int, list[Polygon]] | None = None
    for ai, (ax, ay, extent) in enumerate(axes):
        half = extent / 2 - D["split_edge_margin"]
        exact = {round(v, 3): v for v in ((x - box.cx_m) * ax + (y - box.cy_m) * ay for x, y in poly.exterior.coords)}
        for pos in (exact[k] for k in sorted(exact)):
            if abs(pos) > half:
                continue
            px, py = box.cx_m + ax * pos, box.cy_m + ay * pos
            reach = extent + box.width_m + box.depth_m
            line = LineString([(px - ay * reach, py + ax * reach), (px + ay * reach, py - ax * reach)])
            pieces = _pieces_sorted(shapely_split(poly, line).geoms)
            if len(pieces) < 2 or any(p.area < D["split_min_piece"] for p in pieces):
                continue
            boxes = [layout.box_of_points(list(p.exterior.coords)[:-1], p.area) for p in pieces]
            if any(b is None for b in boxes):
                continue
            total = round(sum(b.width_m * b.depth_m for b in boxes), 3)  # type: ignore[union-attr]
            key = (total, round(abs(pos), 3), ai)
            if best is None or key < best[:3]:
                best = (total, round(abs(pos), 3), ai, pieces)
    return None if best is None else best[3]


def _split(poly: Polygon, depth: int, max_depth: int, budget: list[int], ratio: float) -> list[tuple[Polygon, Box]]:
    box = layout.box_of_points(list(poly.exterior.coords)[:-1], poly.area)
    if box is None:
        return []
    if _fit(poly, box) >= ratio or depth >= max_depth or budget[0] <= 0:
        return [(poly, box)]
    pieces = _cut(poly, box, ratio)
    if pieces is None or len(pieces) - 1 > budget[0]:
        return [(poly, box)]
    budget[0] -= len(pieces) - 1
    out: list[tuple[Polygon, Box]] = []
    for piece in pieces:
        out += _split(piece, depth + 1, max_depth, budget, ratio)
    return out


def outline_to_boxes(outline: Sequence[Sequence[float]], frame: Frame, cfg: Mapping[str, Any], archetype: str) -> list[Box]:
    """One box, or up to 6 (school 8) boxes when the single box covers the outline less than shape_fit and the pieces improve the
    union fit by split_gain (BR-2.1, BR-2.2; U7 2026-10-14: the outside follows the real outline, ㄱ, ㄷ and stepped blocks)."""
    poly = _poly_m(outline, frame)
    if poly is None:
        return []
    single = layout.box_of_points(list(poly.exterior.coords)[:-1], poly.area)
    if single is None:
        return []
    ratio = D["shape_fit"]
    if _fit(poly, single) >= ratio or poly.area < D["split_min_area"]:
        return [single]
    max_boxes, max_depth = (8, 4) if archetype == "school" else (6, 3)
    pieces = _split(poly, 0, max_depth, [max_boxes - 1], ratio)
    if len(pieces) < 2:
        return [single]
    union_fit = min(1.0, poly.area / sum(b.width_m * b.depth_m for _, b in pieces))
    if union_fit < _fit(poly, single) + D["split_gain"]:
        return [single]
    return [b for _, b in sorted(pieces, key=lambda pb: (round(pb[1].cx_m, 3), round(pb[1].cy_m, 3)))]


# --- bodies (BR-1.3 to BR-1.6, BR-3.1, BR-7.2) ----------------------------------------------------------------------

@dataclass(frozen=True)
class Facing:
    side: str
    length: float
    setback: float
    setback_s: float
    feature_id: str


@dataclass(frozen=True)
class Body:
    building_id: str
    archetype: str
    is_body: bool
    boxes: tuple[Box, ...]
    names: tuple[str, ...]
    floors: int
    fh: float
    height_m: float
    wall_color: str
    wall_rgb: tuple[int, int, int]
    material: str
    details: Mapping[str, Any]
    roof_shape: str
    name: str
    usability: str
    front: int = 0
    facing: Facing | None = None
    occluded: tuple[frozenset[str], ...] = ()
    far: bool = False
    warnings: tuple[str, ...] = ()
    single: bool = False  # one business: one name across the front, no floor signs (2026-10-14)
    officetel: bool = False  # punched-window grid above the shop base (2026-10-14)
    base: str | None = None  # wall colour of a two-floor brick base under a panel body (2026-10-14)
    side_shops: tuple[tuple[int, str], ...] = ()  # other faces of a shop block that front a road: storefront and band signs too
    pilotis: bool = False  # open parking on columns under the floors above (2026-10-15)

    @property
    def shop(self) -> bool:
        return self.is_body and self.archetype in ("commercial", "villa") and self.details["ground_use"] == "shop"

    @property
    def public_name(self) -> bool:
        return R.is_public_name(self.name)


def in_school_polygon(centroid: Sequence[float], cfg: Mapping[str, Any]) -> bool:
    pt = Point(centroid[1], centroid[0])  # (lon, lat)
    return any(Polygon([(p[1], p[0]) for p in poly]).covers(pt) for poly in cfg.get("school_polygons") or [])


def floors_and_fh(floors: int | None, height_m: float, cfg: Mapping[str, Any]) -> tuple[int, float]:
    f = int(floors) if floors and floors >= 1 else max(1, int(height_m / float(cfg["floor_height_m"]) + 0.5))
    return f, height_m / f


def make_body(building: Mapping[str, Any], eff: Any, detail: Mapping[str, Any] | None, note: str | None, frame: Frame,
              cfg: Mapping[str, Any]) -> Body | None:
    """The body of one building (boxes, archetype, floors, merged details). None when the outline has no area."""
    bid = str(building["building_id"])
    in_school = in_school_polygon(building["centroid"], cfg) if building.get("centroid") else False
    archetype = R.archetype(building.get("usability_code"), eff.floors_above, building.get("name"), in_school)
    if archetype == "public" and R.shop_house(building.get("usability_code"), building.get("name"), detail):
        archetype = "commercial"
    boxes = outline_to_boxes(building["outline"], frame, cfg, archetype)
    if not boxes:
        return None
    single = layout.box_of_points(list(_poly_m(building["outline"], frame).exterior.coords)[:-1])  # type: ignore[union-attr]
    assert single is not None
    floors, fh = floors_and_fh(eff.floors_above, eff.height_m, cfg)
    is_body = (eff.height_m > D["body_min_height"] and single.depth_m >= D["body_min_side"]
               and single.width_m <= D["body_max_ratio"] * single.depth_m)
    wall_rgb = tuple(int(c) for c in (cfg["wall_colors"].get(eff.wall_color) or cfg["wall_colors"][R.DEFAULT_WALL if hasattr(R, "DEFAULT_WALL") else "light_gray"]))
    merged = R.merged_details(detail, note, eff.wall_color, archetype)
    tags = building.get("osm_tags") if isinstance(building.get("osm_tags"), Mapping) else {}
    wall_color, material, base = eff.wall_color, R.wall_material(merged["finish"], eff.wall_color), None
    if archetype == "commercial" and floors >= R.BASE_MIN_FLOORS and merged["finish"] == "brick":
        base = eff.wall_color if eff.wall_color in ("red_brick", "brown", "orange") else "red_brick"  # brick only on the base
        wall_color = "light_gray"
        material = R.wall_material("panel", wall_color)
        wall_rgb = tuple(int(c) for c in cfg["wall_colors"][wall_color])
    names = (bid,) if len(boxes) == 1 else tuple(f"{bid}#b{i}" for i in range(len(boxes)))
    warnings: list[str] = []
    if is_body and fh < D["min_fh"]:
        warnings.append(f"{bid}: floor height {fh:.2f} m is below {D['min_fh']} m, no windows")
    return Body(bid, archetype, is_body, tuple(boxes), names, floors, fh, float(eff.height_m), wall_color, wall_rgb,  # type: ignore[arg-type]
                material, merged, eff.roof_shape, building.get("name") or "",
                building.get("usability_code") or "", warnings=tuple(warnings),
                single=archetype == "commercial" and R.single_business(building.get("name"), tags),
                officetel=archetype == "commercial" and R.is_officetel(building.get("usability_code"), building.get("name"), tags, floors),
                base=base,
                pilotis=is_body and R.pilotis(archetype, floors, merged, note))


# --- the road-facing side, occlusion and free spans (BR-5) -----------------------------------------------------------

def _feature_lines(features: Sequence[Mapping[str, Any]], frame: Frame, cfg: Mapping[str, Any]) -> list[tuple[str, LineString, float, Mapping[str, Any]]]:
    out = []
    for f in sorted(features, key=lambda f: str(f["feature_id"])):
        if f["kind"] not in ("road", "path"):
            continue
        pts = [layout.to_meters(frame, p[0], p[1]) for p in f["geometry"] if layout._finite(p[0], p[1])]
        if len(pts) >= 2:
            out.append((str(f["feature_id"]), LineString(pts), layout.road_width_m(f, cfg), f))
    return out


def facing_of(body: Body, lines: Sequence[tuple[str, LineString, float, Mapping[str, Any]]], cfg: Mapping[str, Any]) -> tuple[int, Facing | None]:
    """(front box index, facing) by the nearest road edge to any face midpoint, over the full feature geometry (BR-5.1)."""
    best: tuple[float, int, str, str, float, Mapping[str, Any]] | None = None
    for bi, box in enumerate(body.boxes):
        for side in SIDES:
            face = face_of(box, side)
            east, north = _world(box, *face.c)
            pt = Point(east, north)
            for fid, line, width, feature in lines:
                setback = max(0.0, line.distance(pt) - width / 2)
                key = (round(setback, 3), bi, side, fid)
                if best is None or key < best[:4]:
                    best = (setback, bi, side, fid, width, feature)
    if best is None or best[0] > D["facing_max"]:
        return 0, None
    setback, bi, side, fid, width, feature = best
    sides = layout.sidewalk_sides(feature)
    setback_s = setback - float(cfg["sidewalk_width_m"]) if sides and setback >= float(cfg["sidewalk_width_m"]) else setback
    return bi, Facing(side, face_of(body.boxes[bi], side).length, setback, max(0.0, setback_s), fid)


def occluded_faces(body: Body, bi: int, others: Sequence[Polygon], cfg: Mapping[str, Any]) -> frozenset[str]:
    """Faces whose pushed midpoint lies inside a sibling (0.3 m) or another building's box (2.5 m) (BR-5.2)."""
    box = body.boxes[bi]
    out: set[str] = set()
    siblings = [_box_poly(b) for i, b in enumerate(body.boxes) if i != bi]
    for side in SIDES:
        if cfg.get("window_faces") == "front" and not (body.facing and bi == body.front and side == body.facing.side):
            out.add(side)
            continue
        face = face_of(box, side)
        for polys, dist in ((siblings, D["occlude_sibling"]), (others, D["occlude_other"])):
            east, north = _world(box, face.c[0] + face.n[0] * dist, face.c[1] + face.n[1] * dist)
            if any(p.covers(Point(east, north)) for p in polys):
                out.add(side)
                break
    return frozenset(out)


def resolve_body(body: Body, lines: Sequence[tuple[str, LineString, float, Mapping[str, Any]]], others: Sequence[Polygon],
                 cfg: Mapping[str, Any]) -> Body:
    """The body with its front box, facing side, far flag and occluded faces filled in (BR-5)."""
    import dataclasses
    front, facing = facing_of(body, lines, cfg) if body.is_body else (0, None)
    body = dataclasses.replace(body, front=front, facing=facing, far=bool(facing and facing.setback > D["far_facing"]))
    body = dataclasses.replace(body, occluded=tuple(occluded_faces(body, i, others, cfg) for i in range(len(body.boxes))))
    return dataclasses.replace(body, side_shops=shop_sides(body, lines))


def shop_sides(body: Body, lines: Sequence[tuple[str, LineString, float, Mapping[str, Any]]]) -> tuple[tuple[int, str], ...]:
    """The other faces of a commercial shop block that front a road or footpath (setback at most side_shop_max, the face turned toward it): they
    get storefronts and band signs like the facing face. A corner block downtown has shops on every street (cell 4, 2026-10-14)."""
    if body.facing is None or not body.shop or body.archetype != "commercial":
        return ()
    roads = [(line, width) for _, line, width, f in lines]  # roads and footpaths: downtown shops face wide pavements and plazas
    out = []
    for bi, box in enumerate(body.boxes):
        for side in SIDES:
            if (bi, side) == (body.front, body.facing.side) or side in body.occluded[bi]:
                continue
            face = face_of(box, side)
            if face.length < D["side_shop_min"]:
                continue
            pt = Point(*_world(box, *face.c))
            out_pt = Point(*_world(box, face.c[0] + face.n[0] * 2.0, face.c[1] + face.n[1] * 2.0))
            if any(line.distance(pt) - width / 2 <= D["side_shop_max"] and line.distance(out_pt) < line.distance(pt) for line, width in roads):
                out.append((bi, side))
    return tuple(out)


def _blocked(body: Body) -> list[tuple[float, float]]:
    """`along` ranges the stair tower and the bay take on the facing face (BR-5.4)."""
    if body.facing is None:
        return []
    L = body.facing.length
    det = body.details
    out = []
    if det["stair"] == "glass":
        out.append((-L / 3 - D["stair_w"] / 2, -L / 3 + D["stair_w"] / 2))
    elif det["stair"] == "brick":
        out.append((-L / 2, -L / 2 + D["stair_brick"]))
    elif det["stair"] == "round":
        out.append((-L / 2, -L / 2 + D["stair_round_dia"]))
    if det["bay"] and body.floors >= 2:
        out.append((L / 3 - D["bay_w"] / 2, L / 3 + D["bay_w"] / 2))
    return out


def free_spans(body: Body) -> list[tuple[float, float]]:
    """The facing-face `along` intervals not taken by the stair tower or the bay, with margins (BR-5.4)."""
    if body.facing is None:
        return []
    L = body.facing.length
    spans = [(-L / 2 + D["span_margin"], L / 2 - D["span_margin"])]
    for a, b in _blocked(body):
        a, b = a - D["span_clear"], b + D["span_clear"]
        new = []
        for s0, s1 in spans:
            if b <= s0 or a >= s1:
                new.append((s0, s1))
            else:
                if a > s0:
                    new.append((s0, a))
                if b < s1:
                    new.append((b, s1))
        spans = new
    return [s for s in spans if s[1] - s[0] > 1e-6]


def _door_along(body: Body) -> float | None:
    spans = free_spans(body)
    if not spans:
        return None
    for s0, s1 in spans:
        if s0 <= 0.0 <= s1:
            return 0.0
    s0, s1 = max(spans, key=lambda s: (s[1] - s[0], -abs((s[0] + s[1]) / 2)))
    return (s0 + s1) / 2


def _in_span(spans: Sequence[tuple[float, float]], a: float, b: float) -> bool:
    return any(s0 - 1e-6 <= a and b <= s1 + 1e-6 for s0, s1 in spans)


def _longest_span(body: Body) -> tuple[float, float] | None:
    spans = free_spans(body)
    if not spans:
        return None
    return max(spans, key=lambda s: (s[1] - s[0], -abs((s[0] + s[1]) / 2)))


# --- roofs (BR-4) ---------------------------------------------------------------------------------------------------

def roof_items(body: Body, bi: int, frame: Frame, cfg: Mapping[str, Any]) -> list[Item]:
    box = body.boxes[bi]
    shape = body.roof_shape if body.archetype != "school" else "flat"
    if shape not in ("gable", "hip", "shed"):
        return []
    material, color_key = R.ROOF_MATERIALS[body.details["roof_color"]]
    w, d, o = box.width_m, box.depth_m, D["roof_overhang"]
    y_top = body.height_m - D["roof_sink"]
    extra = dict(material=material, color=R.PALETTE[color_key], color_name=color_key)
    items: list[Item] = []
    if shape == "shed":
        rise = math.tan(math.radians(D["shed_pitch_deg"])) * (d + 2 * o)
        side = body.facing.side if (body.facing and bi == body.front) else None
        yaw = 180.0 if side == "b" else 0.0
        items.append(_box_part(frame, body, bi, "roof", f"rf{bi}-0", 0, 0.0, 0.0, y_top, (w + 2 * o, rise, d + 2 * o), yaw, shape="Wedge", **extra))
        return items
    Dd = d / 2 + o
    H = math.tan(math.radians(float(cfg["roof_pitch_deg"]))) * Dd
    if shape == "gable":
        items.append(_box_part(frame, body, bi, "roof", f"rf{bi}-0", 0, 0.0, -Dd / 2, y_top, (w + 2 * o, H, Dd), 0.0, shape="Wedge", **extra))
        items.append(_box_part(frame, body, bi, "roof", f"rf{bi}-1", 1, 0.0, Dd / 2, y_top, (w + 2 * o, H, Dd), 180.0, shape="Wedge", **extra))
        return items
    ridge = w - d
    n = 0
    if ridge >= D["hip_min_ridge"]:
        items.append(_box_part(frame, body, bi, "roof", f"rf{bi}-0", 0, 0.0, -Dd / 2, y_top, (ridge, H, Dd), 0.0, shape="Wedge", **extra))
        items.append(_box_part(frame, body, bi, "roof", f"rf{bi}-1", 1, 0.0, Dd / 2, y_top, (ridge, H, Dd), 180.0, shape="Wedge", **extra))
        n = 2
        cu = ridge / 2 + Dd / 2
    else:
        cu = Dd / 2
    for su in (1, -1):
        for sv in (-1, 1):
            items.append(_box_part(frame, body, bi, "roof", f"rf{bi}-{n}", n, su * cu, sv * Dd / 2, y_top, (Dd, H, Dd),
                                   CORNER_YAW[(su, sv)], shape="CornerWedge", **extra))
            n += 1
    return items


# --- bands, parapet, plinth, windows, rooftop (BR-3, BR-4.4, BR-6) --------------------------------------------------------

def _rear_corner(body: Body) -> tuple[int, int, str]:
    """(sign u, sign v, rear side) of the corner away from the road on the along-negative end (BR-4.4)."""
    side = body.facing.side if body.facing else "b"
    rear = OPPOSITE[side]
    return {"b": (-1, 1), "f": (1, -1), "r": (1, 1), "l": (-1, -1)}[rear] + (rear,)


def body_items(body: Body, bi: int, frame: Frame, cfg: Mapping[str, Any], warnings: list[str]) -> list[Item]:
    """Bands, parapet or railing, plinth, windows or ribbons (an apartment's faces by BR-6.5), rooftop objects of one box (BR-3,
    BR-4.4, BR-6)."""
    box = body.boxes[bi]
    win_t = D["win_t"]
    w, d, F, fh, H = box.width_m, box.depth_m, body.floors, body.fh, body.height_m
    lip, items, seq = D["band_lip"], [], 0
    wall = dict(material=body.material, color=body.wall_rgb, color_name=body.wall_color)
    band_name = f"{body.wall_color}_band"
    band = dict(material=body.material, color=R.band_color(body.wall_rgb), color_name=band_name)
    for k in range(1, F):
        if k == 1 and body.archetype != "school":  # BR-3.2a: the ground floor ends in a thick band proud of the window skin
            bh, bl = D["band1_h"], 2 * D["band1_out"]
            items.append(_box_part(frame, body, bi, "facade", f"fl{bi}-{k}", seq, 0.0, 0.0, k * fh - bh / 2, (w + bl, bh, d + bl),
                                   material="Concrete", color=R.PALETTE["band_ground"], color_name="band_ground"))
        else:
            items.append(_box_part(frame, body, bi, "facade", f"fl{bi}-{k}", seq, 0.0, 0.0, k * fh - D["band_h"] / 2, (w + lip, D["band_h"], d + lip), **band))
        seq += 1
    flat = body.archetype == "school" or body.roof_shape not in ("gable", "hip", "shed")
    roof_surface = H
    if flat:
        if body.details["rooftop"] == "railing":
            rl = D["rail_lip"]
            for i, (su, sv, size) in enumerate(((0, -1, (w + rl, D["rail_h"], D["rail_h"])), (0, 1, (w + rl, D["rail_h"], D["rail_h"])),
                                                 (-1, 0, (D["rail_h"], D["rail_h"], d + rl)), (1, 0, (D["rail_h"], D["rail_h"], d + rl)))):
                items.append(_box_part(frame, body, bi, "facade", f"rl{bi}-{i}", seq, su * (w / 2 + 0.02), sv * (d / 2 + 0.02), H + 0.94, size,
                                       material="Metal", color=R.PALETTE["railing"], color_name="railing"))
                seq += 1
        else:
            rt = body.details.get("roof_top")  # the satellite's colour of the top (roofs.py); without it the darkened wall colour
            top = dict(material="Concrete", color=R.PALETTE[rt], color_name=rt) if rt else band
            items.append(_box_part(frame, body, bi, "facade", f"cap{bi}", seq, 0.0, 0.0, H - D["cap_sink"], (w + lip, D["cap_h"], d + lip), **top))
            seq += 1
            roof_surface = H + D["cap_h"] - D["cap_sink"]
    if body.pilotis:
        items += pilotis_items(body, bi, frame, seq)
        seq += 100
    elif body.archetype in ("villa", "public") and not body.shop:
        items.append(_box_part(frame, body, bi, "facade", f"pl{bi}", seq, 0.0, 0.0, 0.0, (w + lip, D["plinth_h"], d + lip),
                               material="Granite", color=R.PALETTE["plinth"], color_name="plinth"))
        seq += 1
    # windows
    if fh >= D["min_fh"]:
        occluded = body.occluded[bi] if bi < len(body.occluded) else frozenset()
        glass_key = {"villa": "glass", "school": "glass_school"}.get(body.archetype, "glass_com")
        glass = dict(material="SmoothPlastic", color=R.PALETTE[glass_key], color_name=glass_key, reflectance=D["reflect_win"])
        facing_here = body.facing is not None and bi == body.front
        spans = free_spans(body) if facing_here else []
        door = _door_along(body) if facing_here else None
        for side in SIDES:
            face = face_of(box, side)
            L = face.length
            if side in occluded or L < D["face_min"]:
                continue
            is_front = facing_here and side == body.facing.side  # type: ignore[union-attr]
            if body.archetype == "apartment":
                end = L < 0.5 * max(face_of(box, sd).length for sd in SIDES)
                more = (_apartment_end if end else _apartment_face)(body, bi, side, frame, seq, win_t, door if is_front else None)
                items += more
                seq += len(more)
                continue
            if body.archetype == "store":  # windowless stone walls: glass on the ground floor and one tall glass bay per long face
                items.append(_wall_part(frame, body, bi, side, "facade", f"rb{bi}{side}0-0", seq, 0.0, D["ribbon_sill"], D["win_out"],
                                        (L - D["ribbon_inset"], min(D["ribbon_h"], 0.5 * fh) * 1.5, win_t), **glass))
                seq += 1
                if L >= D["store_bay_min"] and F >= 3:
                    items.append(_wall_part(frame, body, bi, side, "facade", f"bay{bi}{side}", seq, 0.0, fh, D["win_out"],
                                            (min(D["store_bay_w"], L / 4), (F - 2) * fh, win_t), **glass))
                    seq += 1
                continue
            if body.archetype == "villa":
                more = _villa_face(body, bi, side, frame, seq, win_t, glass, is_front)
                items += more
                seq += len(more)
                continue
            for k in range(F):
                if body.archetype == "school":  # the dense classroom grid (BR-6.1, street view 2026-10-13)
                    pitch, win_w, win_h, win_max = D["school_win_pitch"], D["school_win_w"], D["school_win_h"], 60
                    n = max(1, min(win_max, int((L - 1) // pitch)))
                    wh = min(win_h, fh - 1.0)
                    for j in range(n):
                        a = L * (j + 0.5) / n - L / 2
                        if is_front:
                            if body.shop and k == 0:
                                continue
                            if not _in_span(spans, a - win_w / 2, a + win_w / 2):
                                continue
                            if k == 0 and door is not None and abs(a - door) < (win_w + D["door_w"]) / 2 + D["span_clear"]:
                                continue
                        items.append(_wall_part(frame, body, bi, side, "facade", f"w{bi}{side}{k}-{j}", seq, a, k * fh + D["win_sill"],
                                                D["win_out"], (win_w, wh, win_t), **glass))
                        seq += 1
                else:
                    rh = min(D["ribbon_school_h"] if body.archetype == "school" else D["ribbon_h"], 0.5 * fh)
                    if k == 0 and ((is_front and (body.shop or body.archetype == "public")) or (bi, side) in body.side_shops):
                        continue
                    ranges = spans if is_front else [(-L / 2 + D["ribbon_inset"] / 2, L / 2 - D["ribbon_inset"] / 2)]
                    for j, (s0, s1) in enumerate(ranges):
                        if s1 - s0 < D["span_min"]:
                            continue
                        items.append(_wall_part(frame, body, bi, side, "facade", f"rb{bi}{side}{k}-{j}", seq, (s0 + s1) / 2, k * fh + D["ribbon_sill"],
                                                D["win_out"], (s1 - s0, rh, win_t), **glass))
                        seq += 1
            if body.officetel and F > D["otel_base"]:  # full-height piers in front of the ribbons above the shop base: punched windows
                y0, out = D["otel_base"] * fh, D["win_out"] + 0.05
                n = max(2, int(L // D["otel_pitch"]))
                for j in range(1, n):
                    items.append(_wall_part(frame, body, bi, side, "facade", f"op{bi}{side}{j}", seq, L * j / n - L / 2, y0, out,
                                            (D["otel_pier_w"], H - y0, out), material=body.material, color=body.wall_rgb, color_name=body.wall_color))
                    seq += 1
    if body.base and body.is_body:  # the brick base of a panel block: a skin over the two lowest floors, under windows and shopfronts
        bo, rgb = D["base_out"], tuple(int(c) for c in cfg["wall_colors"][body.base])
        items.append(_box_part(frame, body, bi, "facade", f"bs{bi}", seq, 0.0, 0.0, 0.0, (w + 2 * bo, min(D["base_floors"], F) * fh, d + 2 * bo),
                               material="Brick", color=rgb, color_name=body.base))
        seq += 1
    if flat and body.archetype == "apartment":  # BR-6.5 crown: a parapet round the roof, above the cap
        ch, ct = D["apt_crown_h"], D["apt_crown_t"]
        for i, (su, sv, size) in enumerate(((0, -1, (w + lip, ch, ct)), (0, 1, (w + lip, ch, ct)), (-1, 0, (ct, ch, d + lip - 2 * ct)),
                                             (1, 0, (ct, ch, d + lip - 2 * ct)))):
            items.append(_box_part(frame, body, bi, "facade", f"cr{bi}-{i}", seq, su * (w + lip - ct) / 2, sv * (d + lip - ct) / 2, H - D["cap_sink"],
                                   size, collide=True, **band))
            seq += 1
    # rooftop (flat roofs only, BR-4.4)
    if flat and body.archetype not in ("school", "apartment") and w >= 6.0 and d >= 5.0:
        su, sv, rear = _rear_corner(body)
        pw, ph, pd = (D["penthouse_w"], D["penthouse_h"], D["penthouse_d"]) if body.archetype == "commercial" and F >= 5 else \
            (D["rooftop_box_w"], D["rooftop_box_h"], D["rooftop_box_d"])
        want_box = (body.archetype == "commercial" and F >= 5) or body.details["rooftop"] == "box"
        want_tank = (body.archetype == "commercial" and F >= 5) or body.details["rooftop"] == "tank"
        inset = D["rooftop_inset"]
        cu, cv = su * (w / 2 - inset - pw / 2), sv * (d / 2 - inset - pd / 2)
        if want_box:
            items.append(_box_part(frame, body, bi, "facade", f"rt{bi}", seq, cu, cv, roof_surface, (pw, ph, pd), **wall))
            seq += 1
        if want_tank:
            t = face_of(box, rear).t
            shift = pw / 2 + D["tank_offset"] + D["tank_dia"] / 2
            tu, tv = cu + t[0] * shift, cv + t[1] * shift
            if abs(tu) <= w / 2 - D["tank_dia"] / 2 and abs(tv) <= d / 2 - D["tank_dia"] / 2:
                east, north = _world(box, tu, tv)
                items.append(_part(frame, "facade", f"{body.building_id}#tk{bi}", body.building_id, seq, east, north, roof_surface,
                                   (D["tank_h"], D["tank_dia"], D["tank_dia"]), box.yaw_deg, owner=body.building_id, shape="Cylinder",
                                   material="SmoothPlastic", color=R.PALETTE["tank"], color_name="tank"))
                seq += 1
    return items


def pilotis_items(body: Body, bi: int, frame: Frame, seq: int) -> list[Item]:
    """필로티 (2026-10-15): the open ground floor of a villa. Columns every `piloti_pitch` along the long sides (and a middle row in a
    deep box), each with a yellow guard at car height; a dark ceiling under the rooms, a concrete parking floor, and a closed stair
    core at the rear corner when the front has no stair tower."""
    box, fh = body.boxes[bi], body.fh
    w, d = box.width_m, box.depth_m
    c, g = D["piloti_col"], D["piloti_guard"]
    col = dict(material="Concrete", color=R.PALETTE["piloti_col"], color_name="piloti_col")
    guard = dict(material="SmoothPlastic", color=R.PALETTE["piloti_guard"], color_name="piloti_guard")
    items: list[Item] = [
        _box_part(frame, body, bi, "facade", f"pc{bi}", seq, 0.0, 0.0, fh - D["piloti_ceiling"], (w, D["piloti_ceiling"], d), collide=False,
                  material="SmoothPlastic", color=R.PALETTE["piloti_ceiling"], color_name="piloti_ceiling"),
        _box_part(frame, body, bi, "facade", f"pf{bi}", seq + 1, 0.0, 0.0, 0.0, (w, 0.1, d),
                  material="Concrete", color=R.PALETTE["piloti_floor"], color_name="piloti_floor")]
    n_u = max(2, int(round(w / D["piloti_pitch"])) + 1)
    rows = [-(d / 2 - c / 2), d / 2 - c / 2] + ([0.0] if d > 2 * D["piloti_pitch"] else [])
    k = 0
    for v in rows:
        for j in range(n_u):
            u = -(w / 2 - c / 2) + (w - c) * j / (n_u - 1)
            items.append(_box_part(frame, body, bi, "facade", f"pq{bi}-{k}", seq + 2 + 2 * k, u, v, 0.0, (c, fh - D["piloti_ceiling"], c), **col))
            items.append(_box_part(frame, body, bi, "facade", f"pg{bi}-{k}", seq + 3 + 2 * k, u, v, 0.0, (c + 0.04, g, c + 0.04), collide=False, **guard))
            k += 1
    if bi == body.front and body.details["stair"] == "none":
        su, sv, _ = _rear_corner(body)
        cw, cd = min(D["piloti_core_w"], w / 2), min(D["piloti_core_d"], d / 2)
        items.append(_box_part(frame, body, bi, "facade", f"pk{bi}", seq + 3 + 2 * k, su * (w / 2 - cw / 2), sv * (d / 2 - cd / 2), 0.0,
                               (cw, fh - D["piloti_ceiling"], cd), material=body.material, color=body.wall_rgb, color_name=body.wall_color))
    return items


FRAMES = ("frame_white", "frame_gray", "frame_dark")


def _villa_columns(body: Body, bi: int, side: str, is_front: bool) -> tuple[list[tuple[float, list[int]]], float]:
    """BR-6.1 window places of a villa face as columns: (along, floors with a window there), and the window height. The front
    face skips the stair tower and bay spans, the shop's ground floor and the door's slot on the ground floor (BR-6.4)."""
    L, F, fh = face_of(body.boxes[bi], side).length, body.floors, body.fh
    win_w = D["win_w"]
    n = max(1, min(int(D["win_max"]), int((L - 1) // D["win_pitch"])))
    spans = free_spans(body) if is_front else []
    door = _door_along(body) if is_front else None
    cols = []
    for j in range(n):
        a = L * (j + 0.5) / n - L / 2
        if is_front and not _in_span(spans, a - win_w / 2, a + win_w / 2):
            continue
        ks = [k for k in range(F) if not (k == 0 and body.pilotis) and not (is_front and k == 0 and (body.shop or (door is not None and
                                                                                abs(a - door) < (win_w + D["door_w"]) / 2 + D["span_clear"])))]
        cols.append((a, ks))
    return cols, min(D["win_h"], fh - 1.0)


def villa_skin_at(body: Body, bi: int, side: str, k: int, is_front: bool) -> bool:
    """BR-6.6: a villa face has wall skin between rows k-1 and k when some window column runs across that floor line."""
    if body.archetype != "villa" or body.fh < D["min_fh"]:
        return False
    return any(k - 1 in ks and k in ks for _, ks in _villa_columns(body, bi, side, is_front)[0])


def _villa_face(body: Body, bi: int, side: str, frame: Frame, seq: int, win_t: float, glass: Mapping[str, Any], is_front: bool) -> list[Item]:
    """BR-6.6: a villa face's windows in few parts. Each run of floors with a window in the same place is one frame (proud of the
    wall by `frame_out`, a colour picked per building) with one glass on it; between two rows a wall-colour skin (`skin_out`)
    covers the frames and glass across the face, so each floor reads as a framed window set in a deeper wall. The skin stops at
    the stair tower and the bay on the front face."""
    L, fh = face_of(body.boxes[bi], side).length, body.fh
    cols, wh = _villa_columns(body, bi, side, is_front)
    fr = FRAMES[R.pick(body.building_id, "frame", len(FRAMES))]
    frame_look = dict(material="SmoothPlastic", color=R.PALETTE[fr], color_name=fr)
    wall = dict(material=body.material, color=body.wall_rgb, color_name=body.wall_color)
    win_w, m, sill = D["win_w"], D["frame_m"], D["win_sill"]
    items: list[Item] = []

    def add(tail: str, along: float, y: float, out: float, size: tuple[float, float, float], look: Mapping[str, Any]) -> None:
        items.append(_wall_part(frame, body, bi, side, "facade", tail, seq + len(items), along, y, out, size, **look))

    for j, (a, ks) in enumerate(cols):
        runs: list[list[int]] = []
        for k in ks:
            if runs and runs[-1][-1] == k - 1:
                runs[-1].append(k)
            else:
                runs.append([k])
        for run in runs:
            y0, y1 = run[0] * fh + sill, run[-1] * fh + sill + wh
            add(f"wf{bi}{side}{run[0]}-{j}", a, y0 - m, D["frame_out"], (win_w + 2 * m, y1 - y0 + 2 * m, D["frame_out"]), frame_look)
            add(f"w{bi}{side}{run[0]}-{j}", a, y0, D["frame_out"] + D["frame_glass"], (win_w, y1 - y0, win_t), glass)
    so = D["skin_out"]
    ranges = [(-L / 2 - so, L / 2 + so)]  # past the corner so two faces' skins meet
    if is_front:
        for b0, b1 in _blocked(body):
            b0, b1 = b0 - D["span_clear"], b1 + D["span_clear"]
            ranges = [r for s0, s1 in ranges for r in ((s0, min(s1, b0)), (max(s0, b1), s1)) if r[1] - r[0] > 1e-6]
    for k in range(1, body.floors):
        if not any(k - 1 in ks and k in ks for _, ks in cols):
            continue
        bottom, top = (k - 1) * fh + sill + wh, k * fh + sill
        for i, (s0, s1) in enumerate(ranges):
            if s1 - s0 >= D["span_min"]:
                add(f"ws{bi}{side}{k}-{i}", (s0 + s1) / 2, bottom, so, (s1 - s0, top - bottom, so), wall)
    return items


APT_ACCENTS = ("apt_beige", "apt_tan", "apt_sand")
APT_PANEL = {"white": "apt_white", "light_gray": "apt_gray", "cream": "apt_sand", "beige": "apt_beige", "brown": "apt_tan"}


def _block_no(body: Body) -> int | None:
    """BR-6.5 (2026-10-14): the block number of a complex building, read off its register name "<number>동"; none otherwise."""
    name = body.name or ""
    return int(name[:-1]) if name.endswith("동") and name[:-1].isdigit() and len(name) <= 6 else None


def _apartment_face(body: Body, bi: int, side: str, frame: Frame, seq: int, win_t: float, door: float | None) -> list[Item]:
    """BR-6.5: a long face of an apartment, few parts for many floors. Units ~10 m wide between full-height wall piers (a dark
    line in front of each); a unit is one full-height accent panel with full-height white mullions. A floor adds one dark glass
    band, a rail and a white slab across the face (the ground floor's band split round the entrance), so slabs and mullions draw
    the window grid. The entrance gets a canopy with the block number."""
    L, F, fh, H = face_of(body.boxes[bi], side).length, body.floors, body.fh, body.height_m
    # the judged wall colour first: here 60 of 62 judged apartments are white or light gray, the beige panels read wrong (2026-10-15)
    accent = APT_PANEL.get(body.wall_color) or APT_ACCENTS[R.pick(body.building_id, "apt_accent", len(APT_ACCENTS))]
    glass = dict(material="SmoothPlastic", color=R.PALETTE["glass_apt"], color_name="glass_apt")  # no reflectance: it mirrors the sky blue
    rail = dict(material="Metal", color=R.PALETTE["apt_rail"], color_name="apt_rail")
    slab = dict(material="Concrete", color=R.PALETTE["apt_slab"], color_name="apt_slab")
    line = dict(material="Concrete", color=R.PALETTE["apt_line"], color_name="apt_line")
    panel = dict(material="Plaster", color=R.PALETTE[accent], color_name=accent)
    wall = dict(material=body.material, color=body.wall_rgb, color_name=body.wall_color)
    items: list[Item] = []

    def add(tail: str, along: float, y: float, out: float, size: tuple[float, float, float], look: Mapping[str, Any], kind: str = "facade",
            **extra: Any) -> None:
        items.append(_wall_part(frame, body, bi, side, kind, tail, seq + len(items), along, y, out, size, **look, **extra))

    a0, a1 = -L / 2 + D["apt_end"], L / 2 - D["apt_end"]
    gh = fh - D["apt_glass_sill"] - D["apt_glass_head"]
    gap = (D["door_w"] + 0.2) / 2 + D["span_clear"]
    for k in range(F):
        ranges = [(a0, door - gap), (door + gap, a1)] if k == 0 and door is not None else [(a0, a1)]
        for j, (s0, s1) in enumerate(ranges):
            if s1 - s0 < D["span_min"]:
                continue
            add(f"ag{bi}{side}{k}-{j}", (s0 + s1) / 2, k * fh + D["apt_glass_sill"], D["win_out"], (s1 - s0, gh, win_t), glass)
            add(f"ar{bi}{side}{k}-{j}", (s0 + s1) / 2, k * fh + D["apt_rail_y"], D["apt_rail_out"], (s1 - s0, D["apt_rail_h"], D["apt_rail_h"]), rail)
        if k > 0:
            add(f"as{bi}{side}{k}", 0.0, k * fh - D["apt_slab_h"], D["apt_slab_out"], (L, D["apt_slab_h"], D["apt_slab_out"]), slab)
    n = max(2, round(L / D["apt_unit"]))
    cuts = [L * j / n - L / 2 for j in range(1, n)]
    if door is not None:  # a pier never stands in the entrance
        clear = (D["door_w"] + D["apt_pier_w"]) / 2 + D["span_clear"]
        cuts = [door + math.copysign(clear, a - door or 1.0) if abs(a - door) < clear else a for a in cuts]
    for j, a in enumerate(cuts, 1):
        add(f"ap{bi}{side}{j}", a, 0.0, D["apt_pier_out"], (D["apt_pier_w"], H, D["apt_pier_out"]), wall)
        add(f"al{bi}{side}{j}", a, 0.0, D["apt_line_out"], (D["apt_line_w"], H, D["apt_line_out"]), line)
    edges = [a0] + cuts + [a1]
    for j in range(len(edges) - 1):
        u0 = edges[j] + (D["apt_pier_w"] / 2 if j > 0 else 0.0)
        u1 = edges[j + 1] - (D["apt_pier_w"] / 2 if j < len(edges) - 2 else 0.0)
        if u1 - u0 < D["span_min"]:
            continue
        if door is not None and u0 < door < u1:  # the panel goes round the entrance: left, right and above it
            top = D["apt_canopy_y"]
            for i, (p0, p1, y) in enumerate(((u0, door - gap, 0.0), (door + gap, u1, 0.0), (door - gap, door + gap, top))):
                if p1 - p0 > 0.1:
                    add(f"au{bi}{side}{j}-{i}", (p0 + p1) / 2, y, D["apt_panel_t"], (p1 - p0, H - y, D["apt_panel_t"]), panel)
        else:
            add(f"au{bi}{side}{j}", (u0 + u1) / 2, 0.0, D["apt_panel_t"], (u1 - u0, H, D["apt_panel_t"]), panel)
        m = int(D["apt_mulls"])
        for i in range(1, m + 1):
            a = u0 + (u1 - u0) * i / (m + 1)
            if door is not None and abs(a - door) < gap:
                continue
            add(f"am{bi}{side}{j}-{i}", a, D["apt_glass_sill"], D["apt_mull_out"], (D["apt_mull_w"], H - D["apt_glass_sill"], D["apt_mull_out"]),
                slab)
    if door is not None:
        cw, cd, ch, cy = D["apt_canopy_w"], D["apt_canopy_d"], D["apt_canopy_h"], D["apt_canopy_y"]
        add("acn", door, cy, cd, (cw, ch, cd), dict(material="Concrete", color=R.PALETTE["canopy"], color_name="canopy"))
    if door is not None and _block_no(body) is not None:
        add("acs", door, cy + ch, cd, (0.6 * cw, 0.6, 0.06), dict(material="SmoothPlastic", color=R.PALETTE["canopy"], color_name="canopy"),
            kind="sign", text=str(_block_no(body)), ink="apt_slab", faces="F", attrs={"MaxDistance": 300})
    return items


def _apartment_end(body: Body, bi: int, side: str, frame: Frame, seq: int, win_t: float, door: float | None) -> list[Item]:
    """BR-6.5: an apartment's end wall stays blank but for the block number high up (only a complex building's real number)."""
    L, H = face_of(body.boxes[bi], side).length, body.height_m
    if H < D["apt_no_drop"] + D["apt_no_h"] + 3.0 or _block_no(body) is None:
        return []
    return [_wall_part(frame, body, bi, side, "sign", "no" + side, seq, 0.0, H - D["apt_no_drop"], D["apt_no_t"],
                       (min(0.6 * L, 2.2 * D["apt_no_h"]), D["apt_no_h"], D["apt_no_t"]), material="SmoothPlastic", color=body.wall_rgb,
                       color_name=body.wall_color, text=f"{_block_no(body)}동", ink="apt_line", faces="F", attrs={"MaxDistance": 1500})]


# --- facade elements, storefront, yard (BR-8, BR-9) ------------------------------------------------------------------------

# storefront looks (material, palette key, reflectance): dark glass, light glass, wood frame, open shutter
SHOP_FRONTS = (("SmoothPlastic", "glass_shop", D["reflect_shop"]), ("SmoothPlastic", "glass_shop_b", D["reflect_shop"]),
               ("Wood", "shop_wood", 0.0), ("Metal", "shutter", 0.0))


def front_items(body: Body, frame: Frame, cfg: Mapping[str, Any], warnings: list[str]) -> list[Item]:
    """Stair tower, bay, balconies, door and canopy (or shutter), AC units, gas pipe, storefront: the front box's facing face."""
    if not body.is_body or body.facing is None or body.archetype in ("school", "apartment", "store"):
        return []
    bi, side, F, fh, H = body.front, body.facing.side, body.floors, body.fh, body.height_m
    L = body.facing.length
    det = body.details
    items: list[Item] = []
    seq = 1000
    wall = dict(material=body.material, color=body.wall_rgb, color_name=body.wall_color)
    glass = dict(material="SmoothPlastic", color=R.PALETTE["glass"], color_name="glass", reflectance=D["reflect_win"])
    # stair tower (BR-8.1)
    if det["stair"] == "glass":
        items.append(_wall_part(frame, body, bi, side, "facade", "st0", seq, -L / 3, 0.0, D["stair_out"], (D["stair_w"], H + D["stair_extra"], D["stair_t"]),
                                material="SmoothPlastic", color=R.PALETTE["glass_stair"], color_name="glass_stair", reflectance=D["reflect_glass"]))
    elif det["stair"] == "brick":
        items.append(_wall_part(frame, body, bi, side, "facade", "st0", seq, -L / 2 + D["stair_brick"] / 2, 0.0, D["stair_brick_out"],
                                (D["stair_brick"], H + D["stair_brick_extra"], D["stair_brick"]), **wall))
    elif det["stair"] == "round":
        items.append(_cyl(frame, body, bi, side, "facade", "st0", seq, -L / 2 + D["stair_round_dia"] / 2, 0.0, D["stair_brick_out"],
                          D["stair_round_dia"], H + D["stair_extra"], **wall))
    seq += 1
    # bay (BR-8.2)
    if det["bay"] and F >= 2:
        bay_h = (F - 1) * fh
        items.append(_wall_part(frame, body, bi, side, "facade", "bay0", seq, L / 3, fh, D["bay_d"], (D["bay_w"], bay_h, D["bay_d"]),
                                material="SmoothPlastic", color=R.PALETTE["bay"], color_name="bay"))
        seq += 1
        for k in range(1, F):
            items.append(_wall_part(frame, body, bi, side, "facade", f"bw{k}", seq, L / 3, k * fh + D["win_sill"], D["bay_d"] + D["win_out"],
                                    (D["win_w"], min(D["win_h"], fh - 1.0), D["win_t"]), **glass))
            seq += 1
    # balconies (BR-8.3)
    if det["balcony"]:
        bl = D["balcony_frac"] * L
        for k in range(1, F):
            items.append(_wall_part(frame, body, bi, side, "facade", f"bk{k}-0", seq, 0.0, k * fh, D["balcony_d"], (bl, D["balcony_slab_h"], D["balcony_d"]),
                                    material="Concrete", color=R.PALETTE["balcony"], color_name="balcony"))
            items.append(_wall_part(frame, body, bi, side, "facade", f"bk{k}-1", seq + 1, 0.0, k * fh + D["balcony_slab_h"], D["balcony_d"],
                                    (bl, D["balcony_rail_h"], D["balcony_rail_t"]), material="SmoothPlastic", color=R.PALETTE["railing"], color_name="railing"))
            seq += 2
    # door, canopy, shutter, name plate (BR-8.4) or storefront (BR-9.2)
    if body.shop:
        span = _longest_span(body)
        if span is None or span[1] - span[0] < D["span_min"]:
            warnings.append(f"{body.building_id}: no free span of {D['span_min']} m on the facing face, no storefront")
        else:
            s0, s1 = span
            Lf = s1 - s0
            units = 1 if body.archetype == "villa" or body.single else max(1, min(int(D["shop_units_max"]), int(Lf // D["shop_unit_m"])))
            uw = Lf / units
            for u in range(units):
                a0, a1 = s0 + uw * u + D["front_gap"] / 2, s0 + uw * (u + 1) - D["front_gap"] / 2
                look = SHOP_FRONTS[R.pick(f"{body.building_id}#sf{u}", "front", len(SHOP_FRONTS))]  # varied fronts (review 2026-10-13)
                if a1 - a0 > 0.3:
                    items.append(_wall_part(frame, body, bi, side, "facade", f"sf{u}", seq, (a0 + a1) / 2, D["front_y"], D["win_out"],
                                            (a1 - a0, fh - D["front_drop"], D["front_t"]), material=look[0], color=R.PALETTE[look[1]],
                                            color_name=look[1], reflectance=look[2]))
                seq += 1
            items.append(_wall_part(frame, body, bi, side, "facade", "sd0", seq, s0 + D["front_door_along"], 0.0, 0.08, (D["door_w"], D["door_h"], D["front_door_t"]),
                                    material="Metal", color=R.PALETTE["door_shop"], color_name="door_shop"))
            seq += 1
            items.append(_wall_part(frame, body, bi, side, "facade", "eb0", seq, (s0 + s1) / 2, fh - D["eyebrow_drop"], D["eyebrow_d"], (Lf - D["eyebrow_gap"], D["eyebrow_h"], D["eyebrow_d"]),
                                    material="Metal", color=R.PALETTE["eyebrow"], color_name="eyebrow"))
            seq += 1
    else:
        door = _door_along(body)
        if door is not None and not body.pilotis:  # pilotis: the way in is the stair core among the columns
            if det["ground_use"] == "garage":
                items.append(_wall_part(frame, body, bi, side, "facade", "sh0", seq, door, 0.0, D["door_t"], (D["shutter_w"], D["shutter_h"], D["shutter_t"]),
                                        material="Metal", color=R.PALETTE["shutter"], color_name="shutter"))
            else:
                items.append(_wall_part(frame, body, bi, side, "facade", "dr0", seq, door, 0.0, D["door_t"], (D["door_w"], D["door_h"], D["door_t"]),
                                        material="Wood", color=R.PALETTE["door"], color_name="door"))
                items.append(_wall_part(frame, body, bi, side, "facade", "cn0", seq + 1, door, D["canopy_y"], D["canopy_d"], (D["canopy_w"], D["canopy_h"], D["canopy_d"]),
                                        material="Slate", color=R.PALETTE["canopy"], color_name="canopy"))
            seq += 2
    # AC units (BR-8.5)
    skin = D["skin_out"] if villa_skin_at(body, bi, side, 1, True) else 0.0  # BR-6.6: the AC and the gas pipe sit on the skin
    ac_y = (2 * fh if body.pilotis else fh) - D["ac_drop"]  # over pilotis the AC hangs on the first floor of rooms
    if body.archetype == "villa":
        count = 1 + R.pick(body.building_id, "ac", 2)
        spans = free_spans(body)
        for i, a in enumerate((L / 4 + D["ac_along"], -(L / 4 + D["ac_along"]))[:count]):
            if _in_span(spans, a - D["ac_w"] / 2, a + D["ac_w"] / 2):
                items.append(_wall_part(frame, body, bi, side, "facade", f"ac{i}", seq, a, ac_y, skin + D["ac_d"], (D["ac_w"], D["ac_h"], D["ac_d"]),
                                        material="Metal", color=R.PALETTE["ac"], color_name="ac"))
                seq += 1
    elif body.archetype == "commercial":
        occluded = body.occluded[bi] if bi < len(body.occluded) else frozenset()
        for other in NEXT_FACE[side]:
            if other not in occluded and face_of(body.boxes[bi], other).length >= D["face_min"]:
                for i, k in enumerate((2, 3, 4)):
                    if k < F:
                        items.append(_wall_part(frame, body, bi, other, "facade", f"ac{i}", seq, 0.0, k * fh + D["ac_com_y"], D["ac_d"], (D["ac_w"], D["ac_h"], D["ac_d"]),
                                                material="Metal", color=R.PALETTE["ac"], color_name="ac"))
                        seq += 1
                break
    # gas pipe (BR-8.6)
    if det["finish"] == "brick" and not body.pilotis:
        gas = dict(material="Metal", color=R.PALETTE["gas"], color_name="gas")
        go = skin + D["gas_out"]
        items.append(_wall_part(frame, body, bi, side, "facade", "gs0", seq, 0.0, D["gas_y"], go, (L, D["gas_dia"], D["gas_dia"]), **gas))
        items.append(_wall_part(frame, body, bi, side, "facade", "gs1", seq + 1, -L / 2 + D["gas_along"], 0.0, go, (D["gas_dia"], D["gas_y"], D["gas_dia"]), **gas))
        seq += 2
    items += _side_shop_fronts(body, frame, seq + 100)
    return items


def _shop_units(body: Body, L: float) -> list[tuple[float, float]]:
    """(start, end) of the shop units across a side face (whole face but the margins; one unit for a single business)."""
    s0, s1 = -L / 2 + D["span_margin"], L / 2 - D["span_margin"]
    units = 1 if body.single else max(1, min(int(D["shop_units_max"]), int((s1 - s0) // D["shop_unit_m"])))
    uw = (s1 - s0) / units
    return [(s0 + uw * u, s0 + uw * (u + 1)) for u in range(units)]


def _side_shop_fronts(body: Body, frame: Frame, seq: int) -> list[Item]:
    """Storefronts and an eyebrow on the other road-facing faces of a shop block (shop_sides)."""
    items: list[Item] = []
    fh = body.fh
    for bi, side in body.side_shops:
        L = face_of(body.boxes[bi], side).length
        units = _shop_units(body, L)
        for u, (a0, a1) in enumerate(units):
            a0, a1 = a0 + D["front_gap"] / 2, a1 - D["front_gap"] / 2
            look = SHOP_FRONTS[R.pick(f"{body.building_id}#ss{bi}{side}{u}", "front", len(SHOP_FRONTS))]
            if a1 - a0 > 0.3:
                items.append(_wall_part(frame, body, bi, side, "facade", f"ss{bi}{side}{u}", seq, (a0 + a1) / 2, D["front_y"], D["win_out"],
                                        (a1 - a0, fh - D["front_drop"], D["front_t"]), material=look[0], color=R.PALETTE[look[1]],
                                        color_name=look[1], reflectance=look[2]))
            seq += 1
        Lf = units[-1][1] - units[0][0]
        items.append(_wall_part(frame, body, bi, side, "facade", f"es{bi}{side}", seq, 0.0, fh - D["eyebrow_drop"], D["eyebrow_d"],
                                (Lf - D["eyebrow_gap"], D["eyebrow_h"], D["eyebrow_d"]), material="Metal", color=R.PALETTE["eyebrow"], color_name="eyebrow"))
        seq += 1
    return items


def yard_items(body: Body, frame: Frame, cfg: Mapping[str, Any]) -> list[Item]:
    """Wall, returns, posts, gate, globe lamps and shrubs in front of a villa that is not a shop (BR-9.3)."""
    if not body.is_body or body.facing is None or body.archetype != "villa" or body.shop:
        return []
    if body.facing.setback_s < D["yard_min"]:
        return []
    bi, side, L = body.front, body.facing.side, body.facing.length
    yd = min(body.facing.setback_s, D["yard_max"]) - D["yard_back"]
    brick = body.details["finish"] == "brick"
    wall = dict(material="Brick", color=body.wall_rgb, color_name=body.wall_color) if brick else \
        dict(material="Concrete", color=R.PALETTE["concrete"], color_name="concrete")
    half, gap, wt, wh = (L + D["wall_extra"]) / 2, D["gate_gap"] / 2, D["wall_t"], D["wall_h"]
    seq, items = 2000, []
    seg = half - gap
    for i, a in enumerate((-(gap + seg / 2), gap + seg / 2)):
        items.append(_wall_part(frame, body, bi, side, "prop", f"yw{i}", seq, a, 0.0, yd + wt / 2, (seg, wh, wt), collide=True, **wall))
        seq += 1
    for i, a in enumerate((-half, half)):
        items.append(_wall_part(frame, body, bi, side, "prop", f"yr{i}", seq, a, 0.0, yd, (wt, wh, yd), collide=True, **wall))
        seq += 1
    pw = D["post_w"]
    for i, a in enumerate((-(gap + pw / 2), gap + pw / 2)):
        items.append(_wall_part(frame, body, bi, side, "prop", f"yp{i}", seq, a, 0.0, yd + pw / 2, (pw, D["post_h"], pw), collide=True, **wall))
        seq += 1
    items.append(_wall_part(frame, body, bi, side, "prop", "yg0", seq, 0.0, 0.0, yd + D["gate_t"] / 2, (D["gate_gap"], D["gate_h"], D["gate_t"]),
                            material="Metal", color=R.PALETTE["iron"], color_name="iron", collide=True))
    seq += 1
    g = D["globe_dia"]
    for i, a in enumerate((-(gap + pw / 2), gap + pw / 2)):
        items.append(_wall_part(frame, body, bi, side, "prop", f"yl{i}", seq, a, D["post_h"], yd + pw / 2 + g / 2, (g, g, g), shape="Ball",
                                material="SmoothPlastic", color=R.PALETTE["lamp_globe"], color_name="lamp_globe"))
        seq += 1
    shrubs = 1 + R.pick(body.building_id, "shrub", 2)
    dia = min(D["shrub_min"] + D["shrub_step"] * ((R.pick(body.building_id, "shrub", 65536) >> 8) % 2), yd - D["shrub_clear"])
    if dia > 0.3:
        for i, a in enumerate((-L / 4, L / 4)[:shrubs]):
            items.append(_wall_part(frame, body, bi, side, "prop", f"ys{i}", seq, a, 0.0, yd / 2 + dia / 2, (dia, dia, dia), shape="Ball",
                                    material="LeafyGrass", color=R.PALETTE["leaf"], color_name="leaf", collide=True))
            seq += 1
    return items


# --- signs (BR-10) --------------------------------------------------------------------------------------------------

def _sign_colors(body: Body, slot: str, word: str) -> tuple[str, str]:
    if word == "약국":
        return "sign_pharmacy", "ink_red"
    if word == "부동산":
        return ("sign_yellow", "ink_black") if R.pick(body.building_id, f"sign{slot}", 2) == 0 else ("sign_blue", "ink_white")
    return R.SIGN_PAIRS[R.pick(body.building_id, f"sign{slot}", len(R.SIGN_PAIRS))]


def _name(body: Body, slot: str, where: str, floor: int) -> str:
    pool = R.pool_for(body.archetype, body.usability, floor, where)
    name = R.sign_name(body.building_id, slot, pool)
    return name


def sign_items(body: Body, frame: Frame, cfg: Mapping[str, Any], warnings: list[str]) -> tuple[list[Item], int]:
    """Band signs, per-floor signs, projecting signs, the rooftop frame and the name plate; (items, label count) (BR-10)."""
    if not body.is_body or body.facing is None or body.archetype in ("school", "apartment", "store"):
        return [], 0
    bi, side, F, fh, H, L = body.front, body.facing.side, body.floors, body.fh, body.height_m, body.facing.length
    items: list[Item] = []
    labels = 0
    seq = 3000
    texts: list[str] = []

    def sign(tail: str, along: float, y: float, out: float, size: tuple[float, float, float], text: str, bg: str, ink: str, faces: str,
             max_dist: int, face: str = side, kind: str = "sign") -> None:
        nonlocal seq, labels
        item = _wall_part(frame, body, bi, face, kind, tail, seq, along, y, out, size, material="SmoothPlastic", color=R.PALETTE[bg],
                          color_name=bg, text=text, ink=ink, faces=faces, attrs={"MaxDistance": max_dist})
        items.append(item)
        texts.append(text)
        labels += 2 if faces == "LR" else 1
        seq += 1

    if body.archetype == "public":
        text = body.name if body.public_name else _name(body, "n", "plate", 0)
        if body.usability == R.PARKING_CODE:  # a parking building's plate says what it is, not a made-up office name (17b, 2026-10-14)
            text = "공영주차장" if "공영" in (body.name or "") else "주차장"
        door = _door_along(body)
        if door is not None:
            sign("sn0", door + D["plate_along"], D["plate_y"], D["plate_t"] + 0.02, (D["plate_w"], D["plate_h"], D["plate_t"]), text, "sign_plate", "ink_white", "F", 200)
    office = body.usability == R.OFFICE_CODE  # BR-10.1a: an office block's shop signs stop at the 3rd floor, no rooftop sign
    if body.shop:
        span = _longest_span(body)
        if span is not None and span[1] - span[0] >= D["span_min"]:
            s0, s1 = span
            Lf = s1 - s0
            units = 1 if body.archetype == "villa" or body.single else max(1, min(int(D["shop_units_max"]), int(Lf // D["shop_unit_m"])))
            uw = Lf / units
            for u in range(units):
                text = _name(body, str(u), "gf", 0)
                bg, ink = _sign_colors(body, str(u), text[-2:] if text.endswith("약국") else text[-3:])
                # the band sign hangs below the first floor line, on the ground floor's top, so it never meets the floor-1 sign (seen in S-10)
                sign(f"sg{u}", s0 + uw * (u + 0.5), fh - D["sign_drop"] - D["sign_h"], D["sign_out"], (uw - D["front_gap"], D["sign_h"], D["sign_t"]), text, bg, ink, "F", 300)
        for bi2, side2 in body.side_shops:  # band signs on the other road-facing faces (2026-10-14)
            L2 = face_of(body.boxes[bi2], side2).length
            for u, (a0, a1) in enumerate(_shop_units(body, L2)):
                slot = "0" if body.single else f"s{bi2}{side2}{u}"  # a single business shows its one name on every street
                text = _name(body, slot, "gf", 0)
                bg, ink = _sign_colors(body, slot, text[-2:] if text.endswith("약국") else text[-3:])
                items.append(_wall_part(frame, body, bi2, side2, "sign", f"sgs{bi2}{side2}{u}", seq, (a0 + a1) / 2, fh - D["sign_drop"] - D["sign_h"],
                                        D["sign_out"], (a1 - a0 - D["front_gap"], D["sign_h"], D["sign_t"]), material="SmoothPlastic",
                                        color=R.PALETTE[bg], color_name=bg, text=text, ink=ink, faces="F", attrs={"MaxDistance": 300}))
                texts.append(text)
                labels += 1
                seq += 1
        if body.archetype == "commercial" and not body.single and F >= int(D["sign_floor_min_floors"]):
            p = max(1, min(int(D["sign_floor_max_panels"]), int(L // D["sign_floor_pitch"])))
            pw = L / p
            for k in range(1, min(F - 1, int(D["sign_floor_max_office"] if office else D["sign_floor_max"])) + 1):
                for i in range(p):
                    slot = f"f{k}-{i}"
                    text = _name(body, slot, "upper", k)
                    bg, ink = _sign_colors(body, slot, text[-3:])
                    sign(f"sgf{k}-{i}", pw * (i + 0.5) - L / 2, k * fh + D["sign_floor_y"], D["sign_out"], (pw - D["front_gap"], D["sign_floor_h"], D["sign_t"]),
                         text, bg, ink, "F", 200)
        proj = ((L / 4, 1.5 * fh, "gf"), (-L / 4, 2.5 * fh, "upper")) if body.archetype == "commercial" and not body.single else ((L / 2 - D["proj_along_in"], 1.5 * fh, "gf"),)
        for i, (a, y, where) in enumerate(proj):
            text = _name(body, f"p{i}", where, 1 if where == "upper" else 0)
            bg, ink = _sign_colors(body, f"p{i}", text[-3:])
            sign(f"sp{i}", a, y, D["proj_out"] + D["proj_d"], (D["proj_t"], D["proj_h"], D["proj_d"]), text, bg, ink, "LR", 200)
        if body.archetype == "commercial" and not office and F >= int(D["roof_sign_min_floors"]):
            flat = body.roof_shape not in ("gable", "hip", "shed")
            surface = H + D["cap_h"] - D["cap_sink"] if flat and body.details["rooftop"] != "railing" else H
            text = _name(body, "r", "roof", 0)
            rw = D["roof_sign_frac"] * L
            box = body.boxes[bi]
            face = face_of(box, side)
            inset = D["roof_sign_t"] / 2 + 0.1
            u, v = face.c[0] - face.n[0] * inset, face.c[1] - face.n[1] * inset
            items.append(_box_part(frame, body, bi, "sign", "sr0", seq, u, v, surface + D["roof_sign_h"], (rw, D["roof_sign_h"], D["roof_sign_t"]),
                                   FACE_YAW[side], material="SmoothPlastic", color=R.PALETTE["sign_white"], color_name="sign_white", text=text,
                                   ink="ink_black", faces="F", attrs={"MaxDistance": 400}))
            texts.append(text)
            labels += 1
            seq += 1
            for i, a in enumerate((-rw * 0.4, rw * 0.4)):
                pu, pv = u + face.t[0] * a, v + face.t[1] * a
                items.append(_box_part(frame, body, bi, "facade", f"rp{i}", seq, pu, pv, surface, (D["roof_sign_post"], D["roof_sign_h"], D["roof_sign_post"]),
                                       material="Metal", color=R.PALETTE["lamp_post"], color_name="lamp_post"))
                seq += 1
    bad = [t for t in texts if not R.SIGN_TEXT.fullmatch(t)]
    if bad:
        warnings.append(f"{body.building_id}: sign text not allowed ({bad[0][:20]!r}), no signs")
        return [], 0
    return items, labels


# --- elevated footbridges (cell 163, 2026-10-14) -------------------------------------------------------------------------------

BRIDGE_WORDS = ("skybridge", "footbridge", "pedestrian bridge", "elevated walkway")


def is_skybridge(building: Mapping[str, Any], note: str | None, frame: Frame) -> bool:
    """An elevated footbridge: nothing in the register, a thin long outline (mean width 2 x area / perimeter at most 6 m, perimeter
    30 m or more) and a photo judgement that calls it a bridge. Built as a raised deck so it does not wall off the road under it."""
    if building.get("floors_above") or building.get("usability_code") or building.get("building_area"):
        return False
    if not note or not any(w in note.lower() for w in BRIDGE_WORDS):
        return False
    poly = _poly_m(building["outline"], frame)
    return poly is not None and poly.length >= 30.0 and 2 * poly.area / poly.length <= 6.0


def skybridge_items(building: Mapping[str, Any], frame: Frame, cfg: Mapping[str, Any]) -> list[Item]:
    """Per box of the outline: a walkable deck 5.5 m up, glass sides and a light roof (the street view: white truss, glass roof)."""
    bid = str(building["building_id"])
    items: list[Item] = []
    for bi, box in enumerate(outline_to_boxes(building["outline"], frame, cfg, "villa")):
        w, d = box.width_m, box.depth_m
        parts = (("dk", 0.0, 5.5, (w, 0.6, d), "Concrete", "bridge_deck", dict(collide=True)),
                 ("gl", d / 2 - 0.05, 6.1, (w, 2.3, 0.1), "Glass", "bridge_glass", dict(transparency=0.5, collide=True)),
                 ("gr", -(d / 2 - 0.05), 6.1, (w, 2.3, 0.1), "Glass", "bridge_glass", dict(transparency=0.5, collide=True)),
                 ("rf", 0.0, 8.4, (w + 0.2, 0.2, d + 0.2), "Metal", "bridge_roof", {}))
        for k, (tail, v, y, size, mat, key, extra) in enumerate(parts):
            east, north = _world(box, 0.0, v)
            items.append(_part(frame, "facade", f"{bid}#{tail}{bi}", bid, 10 * bi + k, east, north, y, size, box.yaw_deg, owner=bid,
                               material=mat, color=R.PALETTE[key], color_name=key, **extra))
    return items


# --- the body boxes as building items (U2 BR-2 with U5 BR-2.3) --------------------------------------------------------------

def box_items(body: Body, building: Mapping[str, Any], eff: Any, frame: Frame) -> list[Item]:
    """One `building` item per box with the U2/U4 attributes; multi-box names end in #b<n> and carry the owner."""
    s = frame.studs_per_m
    items = []
    y0 = body.fh if body.pilotis else 0.0  # pilotis: the rooms start on the first floor, the ground floor is open
    for i, (box, name) in enumerate(zip(body.boxes, body.names)):
        sy = (body.height_m - y0) * s
        attrs: dict[str, Any] = {"BuildingId": body.building_id, "CellId": str(building["cell_id"]), "Source": str(building["source"]),
                                 "HeightM": fmt(body.height_m), "FitRatio": fmt(box.fit_ratio), "HeightBasis": eff.height_basis,
                                 "WallColor": body.wall_color}  # the body's (a brick-base block is panel above, 2026-10-14)
        if eff.floors_above:
            attrs["Floors"] = int(eff.floors_above)
        if eff.floors_basis:
            attrs["FloorsBasis"] = eff.floors_basis
        if eff.flags:
            attrs["Review"] = "-".join(eff.flags)
        items.append(layout._item("building", name, body.building_id, i, (box.cx_m * s, y0 * s + sy / 2, -box.cy_m * s),
                                  (max(box.width_m * s, 1.0), sy, max(box.depth_m * s, 1.0)), box.yaw_deg, attrs, body.wall_rgb,
                                  material=body.material, color_name=body.wall_color, owner=body.building_id if len(body.boxes) > 1 else None))
    return items
