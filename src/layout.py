"""U2 pure functions: world frame, building boxes, road, sidewalk, ground and spawn items, ordering and chunks.

No input or output. Everything the Studio builder needs is computed here, in Python (BR-7.5); studio/Builder.luau only
turns the items into parts. Rules: aidlc-docs/construction/u2-studio-builder/functional-design/business-rules.md
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
LOOKS = {  # BR-2.7, BR-3.6, BR-4.1: (material, color)
    "building": ("Concrete", (200, 200, 205)), "road": ("Asphalt", (60, 60, 64)), "path": ("Pavement", (150, 150, 150)),
    "sidewalk": ("Concrete", (185, 185, 185)), "ground": ("Grass", (95, 140, 70)), "spawn": ("SmoothPlastic", (255, 255, 255)),
}
ORDER = {"ground": 0, "road": 1, "path": 2, "sidewalk": 3, "building": 4, "spawn": 5}  # BR-7.1
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
    return 0.0 if yaw >= 180.0 else yaw


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
    """One part to build. Lengths in studs, rounded to three decimals. `group` and `seq` only fix the order (BR-7.1)."""
    kind: str  # ground, road, path, sidewalk, building, spawn
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


def _item(kind: str, name: str, group: str, seq: int, center: tuple[float, float, float], size: tuple[float, float, float],
          yaw: float, attrs: Mapping[str, Any] | None = None, color: tuple[int, int, int] | None = None) -> Item:
    material, default_color = LOOKS[kind]
    color = color or default_color
    return Item(kind, name, group, seq, fmt(center[0]), fmt(center[1]), fmt(center[2]), fmt(size[0]), fmt(size[1]), fmt(size[2]),
                fmt(yaw), material, color, dict(attrs or {}))


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
    pts = [to_meters(frame, lat, lon) for lat, lon in outline]
    rect = MultiPoint(pts).minimum_rotated_rectangle
    area = Polygon(pts).area
    if rect.geom_type != "Polygon" or rect.area <= 1e-9 or area <= 1e-9:
        return None
    c = list(rect.exterior.coords)[:4]
    e1, e2 = (c[1][0] - c[0][0], c[1][1] - c[0][1]), (c[2][0] - c[1][0], c[2][1] - c[1][1])
    l1, l2 = math.hypot(*e1), math.hypot(*e2)
    if abs(l1 - l2) <= 1e-9 * max(l1, l2):  # equal sides: the smaller yaw
        (long_, width, depth) = (e1, l1, l2) if _yaw_of(*e1) <= _yaw_of(*e2) else (e2, l2, l1)
    else:
        (long_, width, depth) = (e1, l1, l2) if l1 > l2 else (e2, l2, l1)
    return Box(rect.centroid.x, rect.centroid.y, width, depth, _yaw_of(*long_), min(1.0, area / rect.area))


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
                 (max(box.width_m * s, 1.0), sy, max(box.depth_m * s, 1.0)), box.yaw_deg, attrs, color)
    return item, None


# --- roads, paths, sidewalks (BR-3) -------------------------------------------------------------------------

def road_width_m(feature: Mapping[str, Any], cfg: Mapping[str, Any]) -> float:
    """OSM width tag (1 to 30 m) or the table value for the class (BR-3.4)."""
    tagged = geo.normalize_height((feature.get("tags") or {}).get("width"))
    if tagged is not None:
        return min(30.0, max(1.0, tagged))
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
    """Which sides get a sidewalk: the OSM sidewalk tag first, else both sides of the big roads (BR-3.7)."""
    if feature["kind"] != "road":
        return ()
    tag = (feature.get("tags") or {}).get("sidewalk")
    if isinstance(tag, str):
        return {"both": ("L", "R"), "left": ("L",), "right": ("R",)}.get(tag.strip().lower(), ())
    cls = str(feature.get("highway_class") or "")
    return ("L", "R") if cls.removesuffix("_link") in BIG_ROADS else ()


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
