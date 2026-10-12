"""Pure geometry, value normalization and building assembly for U1 (no I/O).

Outlines are tuples of (lat, lon) points. A repeated closing point is dropped.
Rules: aidlc-docs/construction/u1-data-foundation/functional-design/business-rules.md
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import h3
from shapely.geometry import Polygon

LatLon = tuple[float, float]
Outline = tuple[LatLon, ...]

EARTH_R = 6371008.8  # mean earth radius in meters
MIN_AREA_M2 = 0.01  # an outline smaller than this counts as having no area


# --- value types ---------------------------------------------------------------

@dataclass(frozen=True)
class OsmBuilding:
    osm_id: int
    cell_id: str
    outline: Outline
    centroid: LatLon
    tags: Mapping[str, str]
    height_m: float | None
    levels: int | None
    valid: bool


@dataclass(frozen=True)
class GisBuilding:
    gis_key: str
    cell_id: str
    outline: Outline
    centroid: LatLon
    floors_above: int | None
    floors_below: int | None
    height_m: float | None
    name: str
    usability_code: str
    approval_date: str
    building_area: float | None
    valid: bool


@dataclass(frozen=True)
class Building:
    building_id: str
    cell_id: str
    source: str  # "gis" (V-World outline) or "osm" (no V-World building overlaps it)
    outline: Outline
    centroid: LatLon
    gis_key: str | None
    osm_id: int | None
    name: str
    osm_tags: Mapping[str, str] | None
    floors_above: int | None
    floors_below: int | None
    height_m: float | None
    usability_code: str | None
    approval_date: str | None
    building_area: float | None
    osm_height_m: float | None
    osm_levels: int | None
    status: str  # always "ok": invalid outlines never reach a Building


# --- plane projection ----------------------------------------------------------

def _ring(outline: Sequence[LatLon]) -> list[LatLon]:
    pts = [(float(a), float(b)) for a, b in outline]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def _vertex_mean(pts: Sequence[LatLon]) -> LatLon:
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _to_xy(pts: Sequence[LatLon], origin: LatLon) -> list[tuple[float, float]]:
    """Local equirectangular projection to meters around origin."""
    lat0, lon0 = origin
    k = math.cos(math.radians(lat0))
    return [
        (EARTH_R * math.radians(lon - lon0) * k, EARTH_R * math.radians(lat - lat0))
        for lat, lon in pts
    ]


def _from_xy(x: float, y: float, origin: LatLon) -> LatLon:
    lat0, lon0 = origin
    k = math.cos(math.radians(lat0))
    return (lat0 + math.degrees(y / EARTH_R), lon0 + math.degrees(x / (EARTH_R * k)))


def _polygon(outline: Sequence[LatLon], origin: LatLon) -> Polygon:
    return Polygon(_to_xy(_ring(outline), origin))


# --- BR-2, BR-3: centroid, cell, validity -------------------------------------

def centroid(outline: Sequence[LatLon]) -> LatLon:
    """Area centroid (BR-2.1). Vertex mean when there is no usable area."""
    pts = _ring(outline)
    if not pts:
        raise ValueError("empty outline")
    mean = _vertex_mean(pts)
    if len(set(pts)) < 3:
        return mean
    poly = _polygon(pts, mean)
    if not poly.is_valid or poly.area < MIN_AREA_M2:
        return mean
    c = poly.centroid
    return _from_xy(c.x, c.y, mean)


def assign_cell(point: LatLon, res: int) -> str:
    """The H3 cell holding the point (BR-2.2)."""
    return h3.latlng_to_cell(point[0], point[1], res)


def is_valid_outline(outline: Sequence[LatLon]) -> bool:
    """Three or more distinct points, positive area, no self-intersection (BR-3.1)."""
    pts = _ring(outline)
    if len(set(pts)) < 3:
        return False
    poly = _polygon(pts, _vertex_mean(pts))
    return poly.is_valid and poly.area >= MIN_AREA_M2


def outline_from_geojson(geometry: Mapping[str, Any]) -> tuple[Outline, int]:
    """Outline of the largest polygon in a GeoJSON (Multi)Polygon and how many were dropped (BR-3.3).

    GeoJSON order is [lon, lat]; the result is (lat, lon). Holes are ignored.
    """
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Polygon":
        polygons = [coords]
    elif kind == "MultiPolygon":
        polygons = list(coords)
    else:
        raise ValueError(f"unsupported geometry type: {kind!r}")
    if not polygons:
        raise ValueError("geometry has no polygons")
    rings: list[list[LatLon]] = []
    for poly in polygons:
        outer = poly[0]
        rings.append([(float(p[1]), float(p[0])) for p in outer])
    areas = []
    for ring in rings:
        pts = _ring(ring)
        if len(set(pts)) < 3:
            areas.append(0.0)
            continue
        areas.append(abs(_polygon(pts, _vertex_mean(pts)).area))
    best = max(range(len(rings)), key=lambda i: (areas[i], -i))
    return tuple(_ring(rings[best])), len(rings) - 1


# --- BR-4.1: overlap -----------------------------------------------------------

def _bbox(outline: Sequence[LatLon]) -> tuple[float, float, float, float]:
    lats = [p[0] for p in outline]
    lons = [p[1] for p in outline]
    return (min(lats), min(lons), max(lats), max(lons))


def _bbox_disjoint(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]


def overlap_ratio(a: Sequence[LatLon], b: Sequence[LatLon]) -> float:
    """Overlapping area divided by the smaller area, between 0 and 1 (BR-4.1)."""
    pa, pb = _ring(a), _ring(b)
    if len(set(pa)) < 3 or len(set(pb)) < 3:
        return 0.0
    origin = _vertex_mean(pa + pb)
    poly_a, poly_b = _polygon(pa, origin), _polygon(pb, origin)
    smaller = min(poly_a.area, poly_b.area)
    if smaller < MIN_AREA_M2 or not poly_a.is_valid or not poly_b.is_valid:
        return 0.0
    inter = poly_a.intersection(poly_b).area
    return max(0.0, min(1.0, inter / smaller))


# --- BR-5: value normalization -------------------------------------------------

_NUMBER = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:[mM])?\s*$")
_INTEGER = re.compile(r"^\s*([0-9]+)\s*$")


def normalize_height(raw: str | None) -> float | None:
    """'12', '12 m', '12.5', '18.15' -> meters. Missing, unreadable or zero -> None (BR-5.1, 5.3)."""
    if not isinstance(raw, str):
        return None
    m = _NUMBER.match(raw)
    if not m:
        return None
    value = float(m.group(1))
    return value if value > 0 else None


def normalize_levels(raw: str | None) -> int | None:
    """OSM building:levels or V-World above-ground floors: an integer of 1 or more (BR-5.2, 5.3)."""
    if not isinstance(raw, str):
        return None
    m = _INTEGER.match(raw)
    if not m:
        return None
    value = int(m.group(1))
    return value if value >= 1 else None


def normalize_floors_above(raw: str | None) -> int | None:
    return normalize_levels(raw)


def normalize_floors_below(raw: str | None) -> int | None:
    """V-World underground floors: an integer of 0 or more (BR-5.3)."""
    if not isinstance(raw, str):
        return None
    m = _INTEGER.match(raw)
    return int(m.group(1)) if m else None


def _number(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


# --- builders for parsed source records ----------------------------------------

def new_osm_building(osm_id: int, outline: Sequence[LatLon], tags: Mapping[str, str], res: int) -> OsmBuilding:
    ring = tuple(_ring(outline))
    c = centroid(ring)
    return OsmBuilding(
        osm_id=int(osm_id),
        cell_id=assign_cell(c, res),
        outline=ring,
        centroid=c,
        tags=dict(tags),
        height_m=normalize_height(tags.get("height")),
        levels=normalize_levels(tags.get("building:levels")),
        valid=is_valid_outline(ring),
    )


def new_gis_building(gis_key: str, outline: Sequence[LatLon], props: Mapping[str, Any], res: int) -> GisBuilding:
    ring = tuple(_ring(outline))
    c = centroid(ring)

    def text(key: str) -> str:
        v = props.get(key)
        return v.strip() if isinstance(v, str) else ""

    return GisBuilding(
        gis_key=str(gis_key),
        cell_id=assign_cell(c, res),
        outline=ring,
        centroid=c,
        floors_above=normalize_floors_above(text("grnd_flr")),
        floors_below=normalize_floors_below(text("ugrnd_flr")),
        height_m=normalize_height(text("height")),
        name=text("bld_nm"),
        usability_code=text("usability"),
        approval_date=text("useapr_day"),
        building_area=_number(props.get("archarea")),
        valid=is_valid_outline(ring),
    )


# --- BR-4: assembly -------------------------------------------------------------

def _osm_name(tags: Mapping[str, str]) -> str:
    return (tags.get("name:ko") or tags.get("name") or "").strip()


def assemble(osm: Sequence[OsmBuilding], gis: Sequence[GisBuilding], threshold: float) -> list[Building]:
    """V-World buildings are the base; matching OSM buildings add name and tags (BR-4.3 to 4.7).

    Result order and content do not depend on input order. Sorted by building_id.
    """
    gis_ok = sorted((g for g in gis if g.valid), key=lambda g: g.gis_key)
    osm_ok = sorted((o for o in osm if o.valid), key=lambda o: o.osm_id)
    gis_boxes = {g.gis_key: _bbox(g.outline) for g in gis_ok}

    # Each OSM building picks the V-World building it overlaps most (BR-4.4).
    best: dict[int, tuple[float, GisBuilding]] = {}
    for o in osm_ok:
        obox = _bbox(o.outline)
        found: tuple[float, GisBuilding] | None = None
        for g in gis_ok:
            if _bbox_disjoint(obox, gis_boxes[g.gis_key]):
                continue
            ratio = overlap_ratio(o.outline, g.outline)
            if ratio >= threshold and (found is None or ratio > found[0]):
                found = (ratio, g)  # gis_ok is sorted, so ties keep the smaller gis_key
        if found is not None:
            best[o.osm_id] = found

    # Each V-World building keeps one OSM building: the best overlap, ties to the smaller OSM id.
    winner: dict[str, tuple[float, OsmBuilding]] = {}
    for o in osm_ok:
        if o.osm_id not in best:
            continue
        ratio, g = best[o.osm_id]
        current = winner.get(g.gis_key)
        if current is None or ratio > current[0]:
            winner[g.gis_key] = (ratio, o)  # osm_ok is sorted, so ties keep the smaller osm_id

    out: list[Building] = []
    for g in gis_ok:
        o = winner[g.gis_key][1] if g.gis_key in winner else None
        out.append(Building(
            building_id=f"gis:{g.gis_key}",
            cell_id=g.cell_id,
            source="gis",
            outline=g.outline,
            centroid=g.centroid,
            gis_key=g.gis_key,
            osm_id=o.osm_id if o else None,
            name=(_osm_name(o.tags) if o else "") or g.name,
            osm_tags=dict(o.tags) if o else None,
            floors_above=g.floors_above,
            floors_below=g.floors_below,
            height_m=g.height_m,
            usability_code=g.usability_code,
            approval_date=g.approval_date,
            building_area=g.building_area,
            osm_height_m=o.height_m if o else None,
            osm_levels=o.levels if o else None,
            status="ok",
        ))
    for o in osm_ok:
        if o.osm_id in best:
            continue  # covered by a V-World building: kept in osm_buildings only (BR-4.6)
        out.append(Building(
            building_id=f"osm:{o.osm_id}",
            cell_id=o.cell_id,
            source="osm",
            outline=o.outline,
            centroid=o.centroid,
            gis_key=None,
            osm_id=o.osm_id,
            name=_osm_name(o.tags),
            osm_tags=dict(o.tags),
            floors_above=None,
            floors_below=None,
            height_m=None,
            usability_code=None,
            approval_date=None,
            building_area=None,
            osm_height_m=o.height_m,
            osm_levels=o.levels,
            status="ok",
        ))
    out.sort(key=lambda b: b.building_id)
    return out
