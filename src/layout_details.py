"""U5 pure geometry: duplicate outlines, multi-box footprints, bodies and archetypes, the road-facing side, occlusion and free
spans, roofs, bands, windows, facade elements, storefronts, yards, signs, junctions, sidewalk pieces, markings, crosswalks and
street props.

No input or output. Every number is computed here in metres and handed to layout.Item in studs (U2 BR-7.5); studio/Builder.luau
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

import h3
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
CROSSWALK_CLASSES = ("tertiary", "residential")
POLE_CLASSES = ("living_street", "residential", "service")
LAMP_CLASSES = ("tertiary", "residential")
CAR_CLASSES = ("living_street", "residential")


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
    cy = y_m * s if y_center else (y_m + size_m[1] / 2) * s
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
    """One box, or up to 3 (school 6) boxes for a poor fit when they improve the union fit by 0.10 (BR-2.1, BR-2.2)."""
    poly = _poly_m(outline, frame)
    if poly is None:
        return []
    single = layout.box_of_points(list(poly.exterior.coords)[:-1], poly.area)
    if single is None:
        return []
    ratio = float(cfg["poor_fit_ratio"])
    if _fit(poly, single) >= ratio or poly.area < D["split_min_area"]:
        return [single]
    max_boxes, max_depth = (6, 3) if archetype == "school" else (3, 2)
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
    names = (bid,) if len(boxes) == 1 else tuple(f"{bid}#b{i}" for i in range(len(boxes)))
    warnings: list[str] = []
    if is_body and fh < D["min_fh"]:
        warnings.append(f"{bid}: floor height {fh:.2f} m is below {D['min_fh']} m, no windows")
    return Body(bid, archetype, is_body, tuple(boxes), names, floors, fh, float(eff.height_m), eff.wall_color, wall_rgb,  # type: ignore[arg-type]
                R.wall_material(merged["finish"], eff.wall_color), merged, eff.roof_shape, building.get("name") or "",
                building.get("usability_code") or "", warnings=tuple(warnings))


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
    return dataclasses.replace(body, occluded=tuple(occluded_faces(body, i, others, cfg) for i in range(len(body.boxes))))


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
    """Bands, parapet or railing, plinth, windows or ribbons, rooftop objects of one box (BR-3, BR-4.4, BR-6)."""
    box = body.boxes[bi]
    w, d, F, fh, H = box.width_m, box.depth_m, body.floors, body.fh, body.height_m
    lip, items, seq = D["band_lip"], [], 0
    wall = dict(material=body.material, color=body.wall_rgb, color_name=body.wall_color)
    band_name = f"{body.wall_color}_band"
    band = dict(material=body.material, color=R.band_color(body.wall_rgb), color_name=band_name)
    for k in range(1, F):
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
            items.append(_box_part(frame, body, bi, "facade", f"cap{bi}", seq, 0.0, 0.0, H - D["cap_sink"], (w + lip, D["cap_h"], d + lip), **band))
            seq += 1
            roof_surface = H + D["cap_h"] - D["cap_sink"]
    if body.archetype in ("villa", "public") and not body.shop:
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
            for k in range(F):
                if body.archetype == "villa":
                    n = max(1, min(int(D["win_max"]), int((L - 1) // D["win_pitch"])))
                    wh = min(D["win_h"], fh - 1.0)
                    for j in range(n):
                        a = L * (j + 0.5) / n - L / 2
                        if is_front:
                            if body.shop and k == 0:
                                continue
                            if not _in_span(spans, a - D["win_w"] / 2, a + D["win_w"] / 2):
                                continue
                            if k == 0 and door is not None and abs(a - door) < (D["win_w"] + D["door_w"]) / 2 + D["span_clear"]:
                                continue
                        items.append(_wall_part(frame, body, bi, side, "facade", f"w{bi}{side}{k}-{j}", seq, a, k * fh + D["win_sill"],
                                                D["win_out"], (D["win_w"], wh, D["win_t"]), **glass))
                        seq += 1
                else:
                    rh = min(D["ribbon_school_h"] if body.archetype == "school" else D["ribbon_h"], 0.5 * fh)
                    if is_front and k == 0 and (body.shop or body.archetype == "public"):
                        continue
                    ranges = spans if is_front else [(-L / 2 + D["ribbon_inset"] / 2, L / 2 - D["ribbon_inset"] / 2)]
                    for j, (s0, s1) in enumerate(ranges):
                        if s1 - s0 < D["span_min"]:
                            continue
                        items.append(_wall_part(frame, body, bi, side, "facade", f"rb{bi}{side}{k}-{j}", seq, (s0 + s1) / 2, k * fh + D["ribbon_sill"],
                                                D["win_out"], (s1 - s0, rh, D["win_t"]), **glass))
                        seq += 1
    # rooftop (flat roofs only, BR-4.4)
    if flat and body.archetype != "school" and w >= 6.0 and d >= 5.0:
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


# --- facade elements, storefront, yard (BR-8, BR-9) ------------------------------------------------------------------------

def front_items(body: Body, frame: Frame, cfg: Mapping[str, Any], warnings: list[str]) -> list[Item]:
    """Stair tower, bay, balconies, door and canopy (or shutter), AC units, gas pipe, storefront: the front box's facing face."""
    if not body.is_body or body.facing is None or body.archetype == "school":
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
        items.append(_wall_part(frame, body, bi, side, "facade", "st0", seq, -L / 3, 0.0, D["stair_out"], (D["stair_w"], H + D["stair_extra"], D["stair_t"]), **glass))
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
                                    (bl, D["balcony_rail_h"], D["balcony_rail_t"]), material="Metal", color=R.PALETTE["iron"], color_name="iron"))
            seq += 2
    # door, canopy, shutter, name plate (BR-8.4) or storefront (BR-9.2)
    if body.shop:
        span = _longest_span(body)
        if span is None or span[1] - span[0] < D["span_min"]:
            warnings.append(f"{body.building_id}: no free span of {D['span_min']} m on the facing face, no storefront")
        else:
            s0, s1 = span
            Lf = s1 - s0
            units = 1 if body.archetype == "villa" else max(1, min(int(D["shop_units_max"]), int(Lf // D["shop_unit_m"])))
            uw = Lf / units
            for u in range(units):
                a = s0 + uw * (u + 0.5)
                items.append(_wall_part(frame, body, bi, side, "facade", f"sf{u}", seq, a, D["front_y"], D["win_out"], (uw - D["front_gap"], fh - D["front_drop"], D["front_t"]),
                                        material="SmoothPlastic", color=R.PALETTE["glass_shop"], color_name="glass_shop", reflectance=D["reflect_shop"]))
                seq += 1
            items.append(_wall_part(frame, body, bi, side, "facade", "sd0", seq, s0 + D["front_door_along"], 0.0, 0.08, (D["door_w"], D["door_h"], D["front_door_t"]),
                                    material="Metal", color=R.PALETTE["door_shop"], color_name="door_shop"))
            seq += 1
            items.append(_wall_part(frame, body, bi, side, "facade", "eb0", seq, (s0 + s1) / 2, fh - D["eyebrow_drop"], D["eyebrow_d"], (Lf - D["eyebrow_gap"], D["eyebrow_h"], D["eyebrow_d"]),
                                    material="Metal", color=R.PALETTE["eyebrow"], color_name="eyebrow"))
            seq += 1
    else:
        door = _door_along(body)
        if door is not None:
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
    if body.archetype == "villa":
        count = 1 + R.pick(body.building_id, "ac", 2)
        spans = free_spans(body)
        for i, a in enumerate((L / 4 + D["ac_along"], -(L / 4 + D["ac_along"]))[:count]):
            if _in_span(spans, a - D["ac_w"] / 2, a + D["ac_w"] / 2):
                items.append(_wall_part(frame, body, bi, side, "facade", f"ac{i}", seq, a, fh - D["ac_drop"], D["ac_d"], (D["ac_w"], D["ac_h"], D["ac_d"]),
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
    if det["finish"] == "brick":
        gas = dict(material="Metal", color=R.PALETTE["gas"], color_name="gas")
        items.append(_wall_part(frame, body, bi, side, "facade", "gs0", seq, 0.0, D["gas_y"], D["gas_out"], (L, D["gas_dia"], D["gas_dia"]), **gas))
        items.append(_wall_part(frame, body, bi, side, "facade", "gs1", seq + 1, -L / 2 + D["gas_along"], 0.0, D["gas_out"], (D["gas_dia"], D["gas_y"], D["gas_dia"]), **gas))
        seq += 2
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
    if not body.is_body or body.facing is None or body.archetype == "school":
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
        door = _door_along(body)
        if door is not None:
            sign("sn0", door + D["plate_along"], D["plate_y"], D["plate_t"] + 0.02, (D["plate_w"], D["plate_h"], D["plate_t"]), text, "sign_plate", "ink_white", "F", 200)
    if body.shop:
        span = _longest_span(body)
        if span is not None and span[1] - span[0] >= D["span_min"]:
            s0, s1 = span
            Lf = s1 - s0
            units = 1 if body.archetype == "villa" else max(1, min(int(D["shop_units_max"]), int(Lf // D["shop_unit_m"])))
            uw = Lf / units
            for u in range(units):
                text = _name(body, str(u), "gf", 0)
                bg, ink = _sign_colors(body, str(u), text[-2:] if text.endswith("약국") else text[-3:])
                sign(f"sg{u}", s0 + uw * (u + 0.5), fh - D["sign_drop"], D["sign_out"], (uw - D["front_gap"], D["sign_h"], D["sign_t"]), text, bg, ink, "F", 300)
        if body.archetype == "commercial" and F >= int(D["sign_floor_min_floors"]):
            p = max(1, min(int(D["sign_floor_max_panels"]), int(L // D["sign_floor_pitch"])))
            pw = L / p
            for k in range(1, min(F - 1, int(D["sign_floor_max"])) + 1):
                for i in range(p):
                    slot = f"f{k}-{i}"
                    text = _name(body, slot, "upper", k)
                    bg, ink = _sign_colors(body, slot, text[-3:])
                    sign(f"sgf{k}-{i}", pw * (i + 0.5) - L / 2, k * fh + D["sign_floor_y"], D["sign_out"], (pw - D["front_gap"], D["sign_floor_h"], D["sign_t"]),
                         text, bg, ink, "F", 200)
        proj = ((L / 4, 1.5 * fh, "gf"), (-L / 4, 2.5 * fh, "upper")) if body.archetype == "commercial" else ((L / 2 - D["proj_along_in"], 1.5 * fh, "gf"),)
        for i, (a, y, where) in enumerate(proj):
            text = _name(body, f"p{i}", where, 1 if where == "upper" else 0)
            bg, ink = _sign_colors(body, f"p{i}", text[-3:])
            sign(f"sp{i}", a, y, D["proj_out"] + D["proj_d"], (D["proj_t"], D["proj_h"], D["proj_d"]), text, bg, ink, "LR", 200)
        if body.archetype == "commercial" and F >= int(D["roof_sign_min_floors"]):
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


def sidewalk_pieces(st: Street, jcts: Sequence[Junction], frame: Frame, cfg: Mapping[str, Any]) -> list[tuple[int, str, int, float, float]]:
    """(segment, side, piece index, start, end) of the sidewalk pieces after the alley-mouth gaps (BR-11.10)."""
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
            for k, (s0, s1) in enumerate(pc for pc in pieces if pc[1] - pc[0] >= D["piece_min"]):
                out.append((i, side, k, s0, s1))
    return out


def street_items(streets: Sequence[Street], jcts: Sequence[Junction], frame: Frame, cfg: Mapping[str, Any]) -> tuple[list[Item], list[Item]]:
    """(sidewalk pieces replacing U2's, props: curbs, markings, crosswalks, poles, wires, lamps, trees, cars, zone kit, bollards, boxes)."""
    sidewalks: list[Item] = []
    props: list[Item] = []
    s = frame.studs_per_m
    sw = float(cfg["sidewalk_width_m"])
    top_road, top_side = layout.TOPS["road"], layout.TOPS["sidewalk"]
    by_id = {st.feature_id: st for st in streets}
    for st in streets:
        fid, w = st.feature_id, st.width
        jpos = _junction_positions(st, jcts)
        clear = {i: [pos for si, pos, _ in jpos if si == i] for i, *_ in st.owned}
        # sidewalks and curbs (BR-11.10, BR-11.6)
        pieces = sidewalk_pieces(st, jcts, frame, cfg)
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
            if st.highway_class == "residential" and not oneway and length > w:
                for n, lat in enumerate((D["line_gap"], -D["line_gap"])):
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#cl{n}", fid, 200 + 2 * i + n, p, u, length / 2, lat, top_road + D["mark_y_studs"],
                                               (length - w, D["mark_t_studs"], D["line_w"]), y_studs=True, material="SmoothPlastic",
                                               color=R.PALETTE["line_yellow"], color_name="line_yellow", collide=False))
            if st.highway_class == "tertiary":
                pos, n = w / 2, 0
                while pos + D["dash_len"] <= length - w / 2:
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
                    lamp_slots[side].append((i, pos))
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#lamp{j}", fid, 600 + 10 * i + j, p, u, pos, lat, 0.0, (D["lamp_h"], D["lamp_dia"], D["lamp_dia"]),
                                               shape="Cylinder", material="Metal", color=R.PALETTE["lamp_post"], color_name="lamp_post"))
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#larm{j}", fid, 600 + 10 * i + j, p, u, pos, lat - sign * D["lamp_arm"] / 2, D["lamp_arm_y"],
                                               (D["arm_t"], D["arm_t"], D["lamp_arm"]), material="Metal", color=R.PALETTE["lamp_post"], color_name="lamp_post", collide=False))
                    props.append(_segment_part(frame, "prop", f"{fid}#{i}#lhead{j}", fid, 600 + 10 * i + j, p, u, pos, lat - sign * D["lamp_arm"], D["lamp_arm_y"],
                                               (D["lamp_head_w"], D["lamp_head_h"], D["lamp_head_d"]), material="SmoothPlastic", color=R.PALETTE["lamp_head"],
                                               color_name="lamp_head", collide=False))
        # trees (BR-11.4)
        if st.sides:
            for i, p, q, mid, length in st.owned:
                u = ((q[0] - p[0]) / length, (q[1] - p[1]) / length)
                for side in st.sides:
                    sign = 1.0 if side == "L" else -1.0
                    avoid = [pos for si, pos in lamp_slots[side] if si == i] + ([pos for si, pos in pole_slots if si == i] if side == "R" else [])
                    for j, pos in _slots(length, float(cfg["tree_spacing_m"]), clear[i], D["slot_junction_clear"]):
                        if any(abs(pos - a) <= D["tree_clear"] for a in avoid):
                            continue
                        lat = sign * (w / 2 + D["tree_off"])
                        props.append(_segment_part(frame, "prop", f"{fid}#{i}#tree{side}{j}", fid, 700 + 100 * i + j, p, u, pos, lat, 0.0, (D["trunk_h"], D["trunk_dia"], D["trunk_dia"]),
                                                   shape="Cylinder", material="Wood", color=R.PALETTE["trunk"], color_name="trunk"))
                        props.append(_segment_part(frame, "prop", f"{fid}#{i}#crown{side}{j}", fid, 700 + 100 * i + j, p, u, pos, lat, D["crown_y"],
                                                   (D["crown_dia"], D["crown_dia"], D["crown_dia"]), shape="Ball", material="LeafyGrass", color=R.PALETTE["leaf"],
                                                   color_name="leaf", collide=False))
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
    for j in jcts:
        if not j.owned:
            continue
        for ai, a in enumerate(j.arms):
            u = a.direction
            p = (j.east, j.north)
            if a.highway_class in CROSSWALK_CLASSES and a.length >= D["cw_min_arm"]:
                n = int(a.width // D["cw_pitch"])
                start = j.w_max / 2 + D["cw_from"]
                along = start + (D["cw_to"] - D["cw_from"]) / 2
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
                    props.append(_segment_part(frame, "prop", f"{j.name}#bol{ai}-{i}", j.name, 200 + 10 * ai + i, p, u, D["bollard_in"], lat, 0.0,
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


def j_w_max_band(st: Street, jcts: Sequence[Junction], pos: float) -> float:
    """How far from a junction on this street the crosswalk band reaches (BR-11.5 uses it to keep cars off crosswalks)."""
    for j in jcts:
        if any(a.feature_id == st.feature_id for a in j.arms):
            return j.w_max / 2 + D["cw_to"]
    return D["cw_to"]


# --- the body boxes as building items (U2 BR-2 with U5 BR-2.3) --------------------------------------------------------------

def box_items(body: Body, building: Mapping[str, Any], eff: Any, frame: Frame) -> list[Item]:
    """One `building` item per box with the U2/U4 attributes; multi-box names end in #b<n> and carry the owner."""
    s = frame.studs_per_m
    items = []
    for i, (box, name) in enumerate(zip(body.boxes, body.names)):
        sy = body.height_m * s
        attrs: dict[str, Any] = {"BuildingId": body.building_id, "CellId": str(building["cell_id"]), "Source": str(building["source"]),
                                 "HeightM": fmt(body.height_m), "FitRatio": fmt(box.fit_ratio), "HeightBasis": eff.height_basis,
                                 "WallColor": eff.wall_color}
        if eff.floors_above:
            attrs["Floors"] = int(eff.floors_above)
        if eff.floors_basis:
            attrs["FloorsBasis"] = eff.floors_basis
        if eff.flags:
            attrs["Review"] = "-".join(eff.flags)
        items.append(layout._item("building", name, body.building_id, i, (box.cx_m * s, sy / 2, -box.cy_m * s),
                                  (max(box.width_m * s, 1.0), sy, max(box.depth_m * s, 1.0)), box.yaw_deg, attrs, body.wall_rgb,
                                  material=body.material, color_name=body.wall_color, owner=body.building_id if len(body.boxes) > 1 else None))
    return items
