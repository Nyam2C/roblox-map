"""U2 pure functions: world frame, building boxes, road, sidewalk, ground and spawn items, ordering and chunks.

No input or output. Everything the Studio builder needs is computed here, in Python (BR-7.5); studio/ServerStorage/MapBuilder.luau only
turns the items into parts. Rules: aidlc-docs/construction/u2-studio-builder/functional-design/business-rules.md.
U5 (details) adds the item fields owner, shape, color_name, text, ink, faces, reflectance, shadow, collide, four kinds and the
sidewalk amendments (U5 BR-11.13, BR-11.14, BR-14.1); its geometry lives in layout_details.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import h3
from shapely.geometry import MultiPoint, Polygon

import common
import geo
import judgement

LatLon = tuple[float, float]
EARTH_R = 6371008.8  # same value as geo.EARTH_R and projection.EARTH_R
MAX_PART_STUDS = 2048  # Roblox's largest part dimension (BR-4.2)
GROUND_THICKNESS = 4.0
TOPS = {"road": 0.2, "path": 0.3, "sidewalk": 0.4}  # BR-3.5: top height in studs, the slab fills down to Y = 0
BIG_ROADS = {"trunk", "primary", "secondary", "tertiary"}  # and their _link classes (BR-3.7)
LOOKS = {  # BR-2.7, BR-3.6, BR-4.1 (U5 BR-11.14 paved ground and paver sidewalks, BR-14.1 the new kinds): (material, color)
    "building": ("Concrete", (200, 200, 205)), "road": ("Asphalt", (60, 60, 64)), "path": ("Pavement", (150, 150, 150)),
    "sidewalk": ("Brick", (165, 140, 135)), "ground": ("Concrete", (130, 128, 125)), "spawn": ("SmoothPlastic", (255, 255, 255)),
    "roof": ("Slate", (60, 60, 65)), "facade": ("SmoothPlastic", (225, 225, 222)), "sign": ("SmoothPlastic", (240, 240, 236)),
    "prop": ("Concrete", (150, 150, 148)),
}
ORDER = {"ground": 0, "road": 1, "path": 2, "sidewalk": 3, "building": 4, "roof": 5, "facade": 6, "sign": 7, "prop": 8, "spawn": 9}  # BR-7.1, U5 BR-14.1
# U5 BR-14.1: (casts a shadow, collides) by kind; an item that differs sends g=/l= (yard parts and parked cars collide, markings do not)
KIND_DEFAULTS = {"ground": (True, True), "road": (True, True), "path": (True, True), "sidewalk": (True, True), "building": (True, True),
                 "roof": (True, True), "facade": (False, False), "sign": (False, False), "prop": (False, True), "spawn": (False, False)}
SPAWN_SIZE = 6.0
SPAWN_THICKNESS = 0.2


# --- numbers ------------------------------------------------------------------------------

def fmt(v: float) -> float:
    """Three decimals, never -0.0 (BR-7.4). Every number that leaves this module goes through here."""
    r = round(float(v), 3)
    return 0.0 if r == 0 else r


def _finite(*values: Any) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def _yaw_of(dx: float, dy: float) -> float:
    """Direction of (east dx, north dy) as degrees counterclockwise from east, in [0, 180) (a box looks the same turned 180)."""
    yaw = math.degrees(math.atan2(dy, dx)) % 180.0
    return 0.0 if yaw >= 179.9995 else yaw  # 179.9995 and up would print as 180.000 (three decimals): that is 0


# --- world frame (BR-1) ---------------------------------------------------------------------

@dataclass(frozen=True)
class Frame:
    origin_lat: float
    origin_lon: float
    studs_per_m: float

    @classmethod
    def from_cfg(cls, cfg: Mapping[str, Any]) -> "Frame":
        return cls(float(cfg["origin_lat"]), float(cfg["origin_lon"]), float(cfg["studs_per_m"]))


def to_meters(frame: Frame, lat: float, lon: float) -> tuple[float, float]:
    """East and north meters from the origin (BR-1.2)."""
    east = math.radians(lon - frame.origin_lon) * math.cos(math.radians(frame.origin_lat)) * EARTH_R
    north = math.radians(lat - frame.origin_lat) * EARTH_R
    return east, north


def to_studs(frame: Frame, lat: float, lon: float) -> tuple[float, float]:
    """Studio (x, z): east is +X, north is -Z (BR-1.2). Not rounded; items round with fmt."""
    east, north = to_meters(frame, lat, lon)
    return east * frame.studs_per_m, -north * frame.studs_per_m


def from_studs(frame: Frame, x: float, z: float) -> LatLon:
    east, north = x / frame.studs_per_m, -z / frame.studs_per_m
    lat = frame.origin_lat + math.degrees(north / EARTH_R)
    lon = frame.origin_lon + math.degrees(east / (EARTH_R * math.cos(math.radians(frame.origin_lat))))
    return lat, lon


# --- items --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    """One part to build. Lengths in studs, rounded to three decimals. `group` and `seq` only fix the order (BR-7.1).

    U5 fields: `owner` (the building a roof, facade, sign or yard part belongs to), `shape` (Block, Wedge, CornerWedge, Cylinder
    standing with size = height, diameter, diameter, Ball), `color_name` (palette key the chunk's color table resolves), `text`,
    `ink`, `faces` (signs), `reflectance`, `shadow` and `collide` (the kind's default when None).
    """
    kind: str  # ground, road, path, sidewalk, building, roof, facade, sign, prop, spawn
    name: str
    group: str
    seq: int
    cx: float
    cy: float
    cz: float
    sx: float
    sy: float
    sz: float
    yaw_deg: float
    material: str
    color: tuple[int, int, int]
    attrs: Mapping[str, Any] = field(default_factory=dict)
    owner: str | None = None
    shape: str = "Block"
    color_name: str | None = None
    text: str | None = None
    ink: str | None = None
    faces: str | None = None
    reflectance: float = 0.0
    shadow: bool | None = None
    collide: bool | None = None
    transparency: float = 0.0  # see-through glass (subway entrance walls), key tr
    tilt_x: float = 0.0  # degrees about the part's own X after the yaw: a flat piece lying on sloping ground (terrain.py), key ax
    tilt_z: float = 0.0  # degrees about its own Z, key az
    kit: str | None = None  # U7 H: the Builder clones ServerStorage/Kits/<kit> (a MeshPart) instead of making a Part (key kt)

    @property
    def casts_shadow(self) -> bool:
        return KIND_DEFAULTS[self.kind][0] if self.shadow is None else self.shadow

    @property
    def collides(self) -> bool:
        return KIND_DEFAULTS[self.kind][1] if self.collide is None else self.collide


def _item(kind: str, name: str, group: str, seq: int, center: tuple[float, float, float], size: tuple[float, float, float],
          yaw: float, attrs: Mapping[str, Any] | None = None, color: tuple[int, int, int] | None = None, **extra: Any) -> Item:
    material, default_color = LOOKS[kind]
    color = color or default_color
    return Item(kind, name, group, seq, fmt(center[0]), fmt(center[1]), fmt(center[2]), fmt(size[0]), fmt(size[1]), fmt(size[2]),
                fmt(yaw), extra.pop("material", material), color, dict(attrs or {}), **extra)


def order_items(items: Sequence[Item]) -> list[Item]:
    """Ground, roads, paths, sidewalks, buildings, spawn; inside a kind by feature or building id and segment number (BR-7.1)."""
    return sorted(items, key=lambda i: (ORDER[i.kind], i.group, i.seq, i.name))


def chunk_items(items: Sequence[Item], size: int) -> list[list[Item]]:
    """Cut in order into pieces of at most `size` items; no empty piece (BR-7.2)."""
    if size < 1:
        raise ValueError("chunk size must be at least 1")
    return [list(items[i:i + size]) for i in range(0, len(items), size)]


# --- buildings (BR-2) ------------------------------------------------------------------------------

@dataclass(frozen=True)
class Box:
    cx_m: float  # center, east meters
    cy_m: float  # center, north meters
    width_m: float  # long side, along local X
    depth_m: float  # short side, along local Z
    yaw_deg: float  # direction of the long side, [0, 180)
    fit_ratio: float  # outline area / box area, in (0, 1]


def outline_to_box(outline: Sequence[LatLon], frame: Frame) -> Box | None:
    """Minimum-area rotated rectangle around the outline (BR-2.2). None when the outline has no area."""
    return box_of_points([to_meters(frame, lat, lon) for lat, lon in outline])


def box_of_points(pts: Sequence[tuple[float, float]], area: float | None = None) -> Box | None:
    """Minimum-area rotated rectangle around east/north metre points; `area` is the covered polygon's own area (default: the
    polygon through the points in order). None when there is no area.

    The rectangle is measured on every convex-hull edge direction. A tie (a right triangle fits its legs and its hypotenuse with
    the same area) goes to the direction most of the hull's edges run along (the legs, which follow the building grid), then to
    the smaller angle, so the vertex order and start never change the box (P5-3; GEOS's minimum_rotated_rectangle took the first
    of equal rectangles, which follows the order)."""
    hull = MultiPoint(pts).convex_hull
    if area is None:
        area = Polygon(pts).area if len(pts) >= 3 else 0.0
    if hull.geom_type != "Polygon" or hull.area <= 1e-9 or area <= 1e-9:
        return None
    ring = list(hull.exterior.coords)[:-1]
    edges = [(round(math.atan2(y1 - y0, x1 - x0) % (math.pi / 2), 9), math.hypot(x1 - x0, y1 - y0))
             for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])]
    best: tuple[float, ...] | None = None  # (area, -aligned length, angle, c, s, du, dv, centre along u, v)
    for t in sorted({e[0] for e in edges}):
        c, s = math.cos(t), math.sin(t)
        us = [x * c + y * s for x, y in ring]
        vs = [-x * s + y * c for x, y in ring]
        du, dv = max(us) - min(us), max(vs) - min(vs)
        a = du * dv
        along = sum(n for e, n in edges if abs(e - t) <= 1e-6 or abs(abs(e - t) - math.pi / 2) <= 1e-6)
        if best is None or a < best[0] * (1 - 1e-9) or (a <= best[0] * (1 + 1e-9) and -along < best[1] - 1e-9):
            best = (a, -along, t, c, s, du, dv, (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2)
    rect_area, _, _, c, s, du, dv, mu, mv = best  # type: ignore[misc]
    cx, cy = mu * c - mv * s, mu * s + mv * c
    if abs(du - dv) <= 1e-9 * max(du, dv):  # equal sides: the smaller yaw
        width, depth = du, dv
        yaw = min(_yaw_of(c, s), _yaw_of(-s, c))
    elif du > dv:
        width, depth, yaw = du, dv, _yaw_of(c, s)
    else:
        width, depth, yaw = dv, du, _yaw_of(-s, c)
    return Box(cx, cy, width, depth, yaw, min(1.0, area / rect_area))


def is_underground(building: Mapping[str, Any]) -> bool:
    """A record that is mostly below ground (a subway station, an underground car park under a plaza): floors below at least twice
    the floors above (0 counts as 1). Its V-World outline is the underground footprint, so a box on it would cover a road or plaza."""
    below = building.get("floors_below") or 0
    return below >= 2 * max(building.get("floors_above") or 0, 1)


def building_item(building: Mapping[str, Any], frame: Frame, cfg: Mapping[str, Any],
                  eff: judgement.EffectiveBuilding | None = None) -> tuple[Item | None, str | None]:
    """(item, None) for a good building, (None, reason) for one that is skipped (BR-2.9).

    With `eff` (the final value of the building, U4) the height, floors and wall color come from it and the part gets the attributes
    HeightBasis, FloorsBasis, WallColor and Review (BR-9). Without it the old U2 rules apply.
    """
    bid = str(building["building_id"])
    outline = building["outline"]
    if not (isinstance(outline, (list, tuple)) and len(outline) >= 3
            and all(isinstance(p, (list, tuple)) and len(p) == 2 and _finite(p[0], p[1]) for p in outline)):
        return None, f"{bid}: outline has fewer than 3 usable points"
    box = outline_to_box([(p[0], p[1]) for p in outline], frame)
    if box is None:
        return None, f"{bid}: outline has no area"
    s = frame.studs_per_m
    if eff is None:
        height_m, floors, color = common.building_height_m(building.get("height_m"), building.get("floors_above"), cfg), building.get("floors_above"), None
    else:
        height_m, floors, color = eff.height_m, eff.floors_above, judgement.wall_rgb(eff.wall_color, cfg)
    sy = height_m * s
    attrs: dict[str, Any] = {"BuildingId": bid, "CellId": str(building["cell_id"]), "Source": str(building["source"]),
                             "HeightM": fmt(height_m), "FitRatio": fmt(box.fit_ratio)}
    if floors:
        attrs["Floors"] = int(floors)
    if eff is not None:
        attrs["HeightBasis"], attrs["WallColor"] = eff.height_basis, eff.wall_color
        if eff.floors_basis:
            attrs["FloorsBasis"] = eff.floors_basis
        if eff.flags:
            attrs["Review"] = "-".join(eff.flags)  # not a comma: Luau text may only hold the characters in build_luau.SAFE_TEXT
    item = _item("building", bid, bid, 0, (box.cx_m * s, sy / 2, -box.cy_m * s),
                 (max(box.width_m * s, 1.0), sy, max(box.depth_m * s, 1.0)), box.yaw_deg, attrs, color,
                 color_name=eff.wall_color if eff is not None else None)
    return item, None


# --- roads, paths, sidewalks (BR-3) -------------------------------------------------------------------------

def road_width_m(feature: Mapping[str, Any], cfg: Mapping[str, Any]) -> float:
    """OSM width tag (1 to 40 m), else lanes x lane width (the OSM lanes tag, or the lanes of a named road in road_lanes_by_name,
    halved on a one-way carriageway), else the table value for the class (BR-3.4)."""
    tags = feature.get("tags") or {}
    tagged = geo.normalize_height(tags.get("width"))
    if tagged is not None:
        return min(40.0, max(1.0, tagged))
    lanes = geo.normalize_height(tags.get("lanes"))
    if lanes is None and tags.get("name") in cfg.get("road_lanes_by_name", {}):
        lanes = float(cfg["road_lanes_by_name"][tags["name"]]) / (2 if tags.get("oneway") == "yes" else 1)
    if lanes is not None and lanes >= 1:
        return min(40.0, round(lanes * float(cfg.get("lane_width_m", 3.25)), 2))
    cls = str(feature.get("highway_class") or "")
    key = "link" if cls.endswith("_link") else cls
    return float(cfg["road_widths_m"].get(key, 6 if feature.get("kind") == "road" else 2))


def _segments(feature: Mapping[str, Any], frame: Frame, cell_id: str, res: int):
    """(index, start, end, midpoint, length) in east/north meters for the segments this cell owns (BR-3.2)."""
    pts = feature["geometry"]
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        if not _finite(a[0], a[1], b[0], b[1]):
            continue
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if h3.latlng_to_cell(mid[0], mid[1], res) != cell_id:
            continue
        p, q = to_meters(frame, a[0], a[1]), to_meters(frame, b[0], b[1])
        length = math.hypot(q[0] - p[0], q[1] - p[1])
        if length >= 0.001:
            yield i, p, q, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2), length


def road_items(feature: Mapping[str, Any], frame: Frame, cell_id: str, res: int, cfg: Mapping[str, Any]) -> list[Item]:
    """One box per owned segment, longer by the width so joints leave no gap (BR-3.3)."""
    if feature["kind"] not in ("road", "path"):  # crossings, trees and the like are not built here (BR-3.1)
        return []
    kind = feature["kind"]
    fid, width, s = str(feature["feature_id"]), road_width_m(feature, cfg), frame.studs_per_m
    items = []
    for i, p, q, mid, length in _segments(feature, frame, cell_id, res):
        top = TOPS[kind]
        items.append(_item(kind, f"{fid}#{i}", fid, i, (mid[0] * s, top / 2, -mid[1] * s),
                           ((length + width) * s, top, width * s), _yaw_of(q[0] - p[0], q[1] - p[1])))
    return items


def sidewalk_sides(feature: Mapping[str, Any]) -> tuple[str, ...]:
    """Which sides get a sidewalk: the OSM sidewalk tag, else sidewalk:both/left/right, else both sides of the big roads and of
    residential roads (BR-3.7 as amended by U5 BR-11.13)."""
    if feature["kind"] != "road":
        return ()
    tags = feature.get("tags") or {}
    tag = tags.get("sidewalk")
    if isinstance(tag, str):
        return {"both": ("L", "R"), "left": ("L",), "right": ("R",)}.get(tag.strip().lower(), ())
    yes = ("yes", "separate")
    if isinstance(tags.get("sidewalk:both"), str):
        return ("L", "R") if tags["sidewalk:both"].strip().lower() in yes else ()
    sides = tuple(s for s, key in (("L", "sidewalk:left"), ("R", "sidewalk:right"))
                  if isinstance(tags.get(key), str) and tags[key].strip().lower() in yes)
    if sides or any(isinstance(tags.get(k), str) for k in ("sidewalk:left", "sidewalk:right")):
        return sides
    cls = str(feature.get("highway_class") or "")
    return ("L", "R") if cls.removesuffix("_link") in BIG_ROADS or cls == "residential" else ()


def sidewalk_items(feature: Mapping[str, Any], frame: Frame, cell_id: str, res: int, cfg: Mapping[str, Any]) -> list[Item]:
    """Boxes beside the road: road half width + sidewalk half width from the center line; left is left of the drawn direction (BR-3.8)."""
    sides = sidewalk_sides(feature)
    if not sides:
        return []
    fid, s = str(feature["feature_id"]), frame.studs_per_m
    sw, offset = float(cfg["sidewalk_width_m"]), road_width_m(feature, cfg) / 2 + float(cfg["sidewalk_width_m"]) / 2
    items = []
    for i, p, q, mid, length in _segments(feature, frame, cell_id, res):
        ux, uy = (q[0] - p[0]) / length, (q[1] - p[1]) / length
        for side in sides:
            sign = 1 if side == "L" else -1  # left normal = direction turned +90 degrees counterclockwise
            cx, cy = mid[0] - sign * uy * offset, mid[1] + sign * ux * offset
            top = TOPS["sidewalk"]
            items.append(_item("sidewalk", f"{fid}#{i}{side}", fid, 2 * i + (side == "R"), (cx * s, top / 2, -cy * s),
                               ((length + sw) * s, top, sw * s), _yaw_of(ux, uy)))
    return items


# --- ground and spawn (BR-4, BR-5) -----------------------------------------------------------------------------

def ground_item(cell_id: str, frame: Frame, cfg: Mapping[str, Any]) -> Item:
    """One slab per cell covering its boundary and the margin; top at Y = 0 (BR-4.1, BR-4.2)."""
    pts = [to_studs(frame, lat, lon) for lat, lon in h3.cell_to_boundary(cell_id)]
    margin = float(cfg["ground_margin_m"]) * frame.studs_per_m
    x0, x1 = min(p[0] for p in pts) - margin, max(p[0] for p in pts) + margin
    z0, z1 = min(p[1] for p in pts) - margin, max(p[1] for p in pts) + margin
    if max(x1 - x0, z1 - z0) > MAX_PART_STUDS:
        raise ValueError(f"ground for {cell_id} is {x1 - x0:.0f} x {z1 - z0:.0f} studs, more than the {MAX_PART_STUDS} a part can be")
    return _item("ground", "Ground", "Ground", 0, ((x0 + x1) / 2, -GROUND_THICKNESS / 2, (z0 + z1) / 2),
                 (x1 - x0, GROUND_THICKNESS, z1 - z0), 0.0)


def _distance_to_center_line(item: Item, x: float, z: float) -> float:
    """Distance in studs from (x, z) to the center line of a road or path piece (the piece minus its end caps)."""
    t = math.radians(item.yaw_deg)
    ax, az = math.cos(t), -math.sin(t)  # local +X in world
    half = max(0.0, (item.sx - item.sz) / 2)
    along = max(-half, min(half, (x - item.cx) * ax + (z - item.cz) * az))
    return math.hypot(x - (item.cx + along * ax), z - (item.cz + along * az))


def spawn_item(cell_id: str, frame: Frame, cfg: Mapping[str, Any], road_pieces: Sequence[Item]) -> tuple[Item | None, list[str]]:
    """The spawn pad, only in the cell that holds the configured point; warns when it is not on a road (BR-5)."""
    lat, lon = cfg.get("spawn_lat"), cfg.get("spawn_lon")
    if lat is None or lon is None or h3.latlng_to_cell(lat, lon, cfg["h3_res"]) != cell_id:
        return None, []
    x, z = to_studs(frame, lat, lon)
    top = TOPS["road"] + 0.05
    item = _item("spawn", "Spawn", "Spawn", 0, (x, top - SPAWN_THICKNESS / 2, z), (SPAWN_SIZE, SPAWN_THICKNESS, SPAWN_SIZE),
                 float(cfg.get("spawn_yaw_deg") or 0.0))
    near = [p for p in road_pieces if _distance_to_center_line(p, x, z) <= p.sz / 2 + frame.studs_per_m]
    return item, ([] if near else ["spawn point is not on a road or path"])
