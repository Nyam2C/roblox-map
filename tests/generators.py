"""Shared Hypothesis generators for domain objects (PBT-07).

Everything is placed around a vertex shared by three H3 cells near Simwon High School, so
generated buildings straddle several cells and exercise the cell-assignment rules.
"""
from __future__ import annotations

import math

import h3
from hypothesis import strategies as st

import common
import geo
import judgement as J
import panorama_source as ps

RES = 9
BASE: geo.LatLon = h3.cell_to_boundary("8930e0af13bffff")[0]
M_PER_DEG_LAT = 111_320.0


def offset(point: geo.LatLon, dx_m: float, dy_m: float) -> geo.LatLon:
    """Move a point by meters east (dx) and north (dy)."""
    lat, lon = point
    return (lat + dy_m / M_PER_DEG_LAT, lon + dx_m / (M_PER_DEG_LAT * math.cos(math.radians(lat))))


def rect(center: geo.LatLon, w_m: float, h_m: float) -> geo.Outline:
    return tuple(
        offset(center, sx * w_m / 2, sy * h_m / 2)
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    )


@st.composite
def star_outlines(draw, around: geo.LatLon = BASE, spread_m: float = 300.0,
                  min_r: float = 8.0, max_r: float = 40.0) -> geo.Outline:
    """A simple (never self-intersecting) polygon: star-shaped around its center."""
    cx = draw(st.floats(-spread_m, spread_m))
    cy = draw(st.floats(-spread_m, spread_m))
    n = draw(st.integers(3, 8))
    r = draw(st.floats(min_r, max_r))
    pts = []
    for i in range(n):
        jitter = draw(st.floats(-0.25, 0.25)) * (2 * math.pi / n)
        radius = r * draw(st.floats(0.6, 1.0))
        a = 2 * math.pi * i / n + jitter
        pts.append(offset(around, cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return tuple(pts)


@st.composite
def convex_outlines(draw, around: geo.LatLon = BASE, spread_m: float = 300.0,
                    min_r: float = 8.0, max_r: float = 40.0) -> geo.Outline:
    """A convex polygon: points on a circle (the centroid must then lie inside it)."""
    cx = draw(st.floats(-spread_m, spread_m))
    cy = draw(st.floats(-spread_m, spread_m))
    n = draw(st.integers(3, 8))
    r = draw(st.floats(min_r, max_r))
    return tuple(
        offset(around, cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    )


@st.composite
def bowtie_outlines(draw) -> geo.Outline:
    """A self-intersecting outline (an hourglass)."""
    c = draw(star_outlines())[0]
    w = draw(st.floats(5, 30))
    return (offset(c, 0, 0), offset(c, w, w), offset(c, w, 0), offset(c, 0, w))


def height_strings(allow_none: bool = True):
    options = [
        st.sampled_from(["", "0", "-3", "abc", "12 m", "  7 m ", "12", "12.5", "18.15", "NaN", "1e3"]),
        st.integers(1, 200).map(str),
        st.floats(0.1, 200, allow_nan=False).map(lambda v: f"{v:.2f}"),
    ]
    return st.one_of(st.none(), *options) if allow_none else st.one_of(*options)


def level_strings(allow_none: bool = True):
    options = [
        st.sampled_from(["", "0", "-1", "abc", "5.0", " 7 ", "3"]),
        st.integers(1, 60).map(str),
    ]
    return st.one_of(st.none(), *options) if allow_none else st.one_of(*options)


def osm_tags():
    return st.fixed_dictionaries(
        {},
        optional={
            "name": st.sampled_from(["심원고등학교", "로얄프라자", "한신빌라"]),
            "name:ko": st.sampled_from(["심원고", "한신빌라(한글)"]),
            "height": height_strings(allow_none=False),
            "building:levels": level_strings(allow_none=False),
            "roof:shape": st.sampled_from(["flat", "gabled", "hipped"]),
        },
    )


def vworld_props():
    return st.fixed_dictionaries(
        {},
        optional={
            "bld_nm": st.sampled_from(["", "부흥중학교", "중동대림아파트"]),
            "grnd_flr": level_strings(allow_none=False),
            "ugrnd_flr": st.sampled_from(["", "0", "1", "2", "x"]),
            "height": height_strings(allow_none=False),
            "usability": st.sampled_from(["10000", "02000", ""]),
            "useapr_day": st.sampled_from(["19950901", "20010203", ""]),
            "archarea": st.one_of(st.floats(1, 5000, allow_nan=False), st.sampled_from(["", "x", "2014.47"])),
        },
    )


@st.composite
def scenarios(draw, max_gis: int = 8, max_osm: int = 6, allow_invalid: bool = True):
    """(osm_buildings, gis_buildings): some OSM outlines are near-copies of V-World ones."""
    n_gis = draw(st.integers(0, max_gis))
    gis_outlines = [draw(star_outlines()) for _ in range(n_gis)]
    if allow_invalid and draw(st.booleans()):
        gis_outlines.append(draw(bowtie_outlines()))
    gis = [
        geo.new_gis_building(f"{1000 + i}", ol, draw(vworld_props()), RES)
        for i, ol in enumerate(gis_outlines)
    ]
    osm_outlines = []
    for _ in range(draw(st.integers(0, max_osm))):
        if gis_outlines and draw(st.booleans()):
            base = draw(st.sampled_from(gis_outlines))
            dx, dy = draw(st.floats(-6, 6)), draw(st.floats(-6, 6))
            osm_outlines.append(tuple(offset(p, dx, dy) for p in base))
        else:
            osm_outlines.append(draw(star_outlines()))
    if allow_invalid and draw(st.booleans()):
        osm_outlines.append(draw(bowtie_outlines()))
    osm = [
        geo.new_osm_building(5000 + i, ol, draw(osm_tags()), RES)
        for i, ol in enumerate(osm_outlines)
    ]
    return osm, gis


# --- U3 street view ------------------------------------------------------------------

def positions(spread_m: float = 300.0):
    """A point within spread_m meters of BASE."""
    return st.builds(lambda dx, dy: offset(BASE, dx, dy), st.floats(-spread_m, spread_m), st.floats(-spread_m, spread_m))


def position_pairs(spread_m: float = 300.0):
    return st.tuples(positions(spread_m), positions(spread_m))


compass_degrees = st.floats(0.0, 360.0, exclude_max=True)  # headings and bearings
extents_deg = st.floats(0.0, 200.0)
distances_m = st.floats(0.0, 150.0)
heights_m = st.floats(0.5, 200.0)


def candidates(origin: geo.LatLon = BASE, spread_m: float = 200.0, max_size: int = 25):
    """Panorama candidates around `origin` with unique ids (BR-2.1)."""
    one = st.builds(lambda i, dx, dy: ps.Candidate(f"p{i}", *offset(origin, dx, dy)),
                    st.integers(0, 10**6), st.floats(-spread_m, spread_m), st.floats(-spread_m, spread_m))
    return st.lists(one, max_size=max_size, unique_by=lambda c: c.pano_id)


# --- U2 Studio builder ------------------------------------------------------------------------

ROAD_CLASSES_U2 = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service",
                   "living_street", "road", "tertiary_link", "primary_link"]
PATH_CLASSES_U2 = ["pedestrian", "footway", "path", "cycleway", "steps", "track"]


@st.composite
def road_features(draw, max_points: int = 8, spread_m: float = 250.0):
    """A street_features row: a polyline of 2..max_points points (steps of 2 to 120 m) with class and tags, near BASE."""
    n = draw(st.integers(2, max_points))
    x, y = draw(st.floats(-spread_m, spread_m)), draw(st.floats(-spread_m, spread_m))
    pts = [offset(BASE, x, y)]
    for _ in range(n - 1):
        step, angle = draw(st.floats(2, 120)), draw(st.floats(0, 2 * math.pi))
        x, y = x + step * math.cos(angle), y + step * math.sin(angle)
        pts.append(offset(BASE, x, y))
    cls = draw(st.sampled_from(ROAD_CLASSES_U2 + PATH_CLASSES_U2))
    tags = draw(st.fixed_dictionaries({}, optional={
        "width": st.sampled_from(["3", "6.5", "8 m", "100", "0.2", "abc", ""]),
        "sidewalk": st.sampled_from(["both", "left", "right", "no", "none", "separate", "yes", "BOTH", " Both "]),
    }))
    return {"feature_id": f"way:{draw(st.integers(1, 10**6))}", "kind": "road" if cls in ROAD_CLASSES_U2 else "path",
            "highway_class": cls, "geometry": [list(p) for p in pts], "tags": tags}


# --- U4 judgement and corrections ---------------------------------------------------------------------

COLOR_NAMES = sorted(common.DEFAULTS["wall_colors"]) + [J.OTHER_COLOR]
TIMES = st.builds("2026-10-{:02d}T{:02d}:{:02d}:{:02d}+00:00".format, st.integers(1, 28), st.integers(0, 23), st.integers(0, 59),
                  st.integers(0, 59))
REASONS = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=0x2FFF, blacklist_categories=("Cc", "Cs")),
                  min_size=1, max_size=60).filter(lambda t: t == t.strip())  # no space at the ends: the stored reason is trimmed


@st.composite
def register_buildings(draw, building_id: str = "gis:1"):
    """A buildings row as far as U4 reads it: register floors and height (missing, zero or real) and OSM reference values."""
    return {"building_id": building_id,
            "floors_above": draw(st.one_of(st.none(), st.just(0), st.integers(1, 30))),
            "height_m": draw(st.one_of(st.none(), st.just(0.0), st.floats(2, 120).map(lambda x: round(x, 1)))),
            "osm_height_m": draw(st.one_of(st.none(), st.floats(2, 100).map(lambda x: round(x, 1)))),
            "osm_levels": draw(st.one_of(st.none(), st.integers(1, 20)))}


@st.composite
def judgements(draw, building_id: str = "gis:1", ranks=(1, 2, 3)):
    """A valid judgement (what `record` takes): floors or a geometry height, confidence, color, roof, views, note."""
    floors = draw(st.one_of(st.none(), st.integers(1, 30)))
    height = draw(st.one_of(st.none(), st.floats(2, 200))) if floors is None else None
    counted = floors is not None or height is not None
    return {"building_id": building_id, "floors_seen": floors, "height_est_m": height,
            "confidence": draw(st.sampled_from(J.CONFIDENCES)) if counted else draw(st.one_of(st.none(), st.sampled_from(J.CONFIDENCES))),
            "wall_color": draw(st.one_of(st.none(), st.sampled_from(COLOR_NAMES))),
            "roof_shape": draw(st.one_of(st.none(), st.sampled_from(J.ROOF_SHAPES))),
            "views_used": draw(st.lists(st.sampled_from(ranks), min_size=1, max_size=len(ranks), unique=True)),
            "note": draw(st.one_of(st.none(), st.text(alphabet="abc def.", max_size=40)))}


@st.composite
def override_pairs(draw):
    """(field, valid value) of one correction."""
    field = draw(st.sampled_from(J.FIELDS))
    value = {"floors_above": st.integers(1, 100), "height_m": st.floats(2, 500), "wall_color": st.sampled_from(COLOR_NAMES),
             "roof_shape": st.sampled_from(J.ROOF_SHAPES)}[field]
    return field, draw(value)


@st.composite
def override_sets(draw):
    """{field: value} for one building, at most one value per field."""
    pairs = draw(st.lists(override_pairs(), max_size=4))
    return dict(pairs)


@st.composite
def building_cases(draw, building_id: str = "gis:1"):
    """(buildings row, judgement or None, overrides dict) for one building."""
    return (draw(register_buildings(building_id)), draw(st.one_of(st.none(), judgements(building_id))), draw(override_sets()))
