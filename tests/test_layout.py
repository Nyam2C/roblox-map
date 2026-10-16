"""U2 layout: coordinates (P2-1), building boxes (P2-2, P2-3), road pieces and ownership (P2-4, P2-9), sidewalks (P2-5),
ground (P2-6), chunks and order (P2-7, P2-8), spawn. The expected values are worked out here, not by calling layout."""
from __future__ import annotations

import itertools
import math
import random
import re

import h3
import pytest
from hypothesis import assume, given, settings, strategies as st
from shapely.geometry import Polygon

import common
import judgement
import layout
import projection
from generators import BASE, convex_outlines, offset, rect, road_features, star_outlines

CFG = common.DEFAULTS
FRAME = layout.Frame.from_cfg(CFG)
S = FRAME.studs_per_m
RES = CFG["h3_res"]
CELL = "8930e0af13bffff"
BIG = {"trunk", "primary", "secondary", "tertiary"}


def to_latlon(east_m: float, north_m: float, frame: layout.Frame = FRAME):
    r = layout.EARTH_R
    return (frame.origin_lat + math.degrees(north_m / r),
            frame.origin_lon + math.degrees(east_m / (r * math.cos(math.radians(frame.origin_lat)))))


def gap180(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def local(item: layout.Item, x: float, z: float) -> tuple[float, float]:
    """(u, w): a stud point in the box's own axes (local +X is (cos, -sin) in x/z, local +Z is (sin, cos))."""
    t = math.radians(item.yaw_deg)
    dx, dz = x - item.cx, z - item.cz
    return dx * math.cos(t) - dz * math.sin(t), dx * math.sin(t) + dz * math.cos(t)


def row(outline, **kw):
    return {"building_id": "gis:1", "cell_id": CELL, "source": "gis", "outline": [list(p) for p in outline],
            "floors_above": None, "height_m": None, **kw}


def studs(outline):
    return [layout.to_studs(FRAME, lat, lon) for lat, lon in outline]


# --- P2-1 coordinates ---------------------------------------------------------------------------

near = st.builds(lambda a, b: (FRAME.origin_lat + a, FRAME.origin_lon + b), st.floats(-0.04, 0.04), st.floats(-0.05, 0.05))
close = st.builds(lambda a, b: (FRAME.origin_lat + a, FRAME.origin_lon + b), st.floats(-0.005, 0.005), st.floats(-0.006, 0.006))


def test_origin_is_zero_and_east_is_plus_x_north_is_minus_z():
    assert layout.to_studs(FRAME, FRAME.origin_lat, FRAME.origin_lon) == (0.0, 0.0)
    x, z = layout.to_studs(FRAME, *offset((FRAME.origin_lat, FRAME.origin_lon), 100, 0))
    assert x == pytest.approx(100 * S, rel=3e-3) and z == pytest.approx(0, abs=1e-6)
    x, z = layout.to_studs(FRAME, *offset((FRAME.origin_lat, FRAME.origin_lon), 0, 100))
    assert x == pytest.approx(0, abs=1e-6) and z == pytest.approx(-100 * S, rel=3e-3)


@given(near)
def test_p2_1_coordinates_round_trip(p):
    lat, lon = layout.from_studs(FRAME, *layout.to_studs(FRAME, *p))
    assert lat == pytest.approx(p[0], abs=1e-9) and lon == pytest.approx(p[1], abs=1e-9)


@given(close, close)
def test_p2_1_stud_distance_is_meter_distance_times_the_scale(a, b):
    (xa, za), (xb, zb) = layout.to_studs(FRAME, *a), layout.to_studs(FRAME, *b)
    meters = projection.distance_m(a, b)
    assert math.hypot(xb - xa, zb - za) == pytest.approx(meters * S, rel=5e-3, abs=1e-3)


@given(near, st.floats(0.5, 10))
def test_p2_1_doubling_the_scale_doubles_every_coordinate(p, scale):
    other = layout.Frame(FRAME.origin_lat, FRAME.origin_lon, S * scale)
    x1, z1 = layout.to_studs(FRAME, *p)
    x2, z2 = layout.to_studs(other, *p)
    assert x2 == pytest.approx(x1 * scale, rel=1e-12, abs=1e-9) and z2 == pytest.approx(z1 * scale, rel=1e-12, abs=1e-9)


# --- P2-2, P2-3 building boxes -------------------------------------------------------------------

@given(st.one_of(star_outlines(spread_m=300), convex_outlines(spread_m=300)))
def test_p2_2_the_box_covers_the_outline_and_is_snug(outline):
    item, warning = layout.building_item(row(outline), FRAME, CFG)
    assert item is not None and warning is None
    pts = studs(outline)
    for x, z in pts:
        u, w = local(item, x, z)
        assert abs(u) <= item.sx / 2 + 0.02 and abs(w) <= item.sz / 2 + 0.02
    area, box_area = Polygon(pts).area, item.sx * item.sz
    slack = (item.sx + item.sz) * 0.001  # sizes are rounded to three decimals
    assert box_area >= area * (1 - 1e-6) - slack
    aligned = (max(p[0] for p in pts) - min(p[0] for p in pts)) * (max(p[1] for p in pts) - min(p[1] for p in pts))
    assert box_area <= aligned * (1 + 1e-6) + slack  # the best rotation is never worse than not rotating
    fit = item.attrs["FitRatio"]
    assert 0 < fit <= 1 and fit == pytest.approx(area / box_area, abs=0.01)
    assert item.sx >= item.sz and 0 <= item.yaw_deg < 180


@given(st.floats(10, 60), st.floats(10, 60))
def test_p2_2_a_rectangle_gives_back_the_rectangle(w, h):
    assume(abs(w - h) > 0.05 * max(w, h))
    item, _ = layout.building_item(row(rect(BASE, w, h)), FRAME, CFG)
    assert item.attrs["FitRatio"] >= 0.999
    assert item.sx == pytest.approx(max(w, h) * S, rel=5e-3) and item.sz == pytest.approx(min(w, h) * S, rel=5e-3)
    assert gap180(item.yaw_deg, 0.0 if w > h else 90.0) < 0.5  # rect() puts w east-west


@given(star_outlines(spread_m=300), st.integers(0, 7), st.booleans())
def test_p2_2_start_vertex_and_direction_do_not_matter(outline, shift, reverse):
    assume(len(outline) >= 4)  # a triangle has three equally good boxes, so which one is picked is not fixed
    base, _ = layout.building_item(row(outline), FRAME, CFG)
    assume(abs(base.sx - base.sz) > 0.5)
    pts = list(outline[shift % len(outline):] + outline[:shift % len(outline)])
    other, _ = layout.building_item(row(list(reversed(pts)) if reverse else pts), FRAME, CFG)
    assert (other.sx, other.sz) == pytest.approx((base.sx, base.sz), abs=0.02)
    assert gap180(other.yaw_deg, base.yaw_deg) < 0.05


def turned(points, alpha_deg):
    c, s_ = math.cos(math.radians(alpha_deg)), math.sin(math.radians(alpha_deg))
    out = []
    for lat, lon in points:
        e, n = layout.to_meters(FRAME, lat, lon)
        out.append(to_latlon(e * c - n * s_, e * s_ + n * c))
    return out


@given(star_outlines(spread_m=300), st.floats(1, 179))
def test_p2_2_turning_the_shape_keeps_the_box_area_and_the_fit(outline, alpha):
    # the box itself can jump between equally good ones (a rhombus has two), but its area and the fit cannot
    base, _ = layout.building_item(row(outline), FRAME, CFG)
    other, _ = layout.building_item(row(turned(outline, alpha)), FRAME, CFG)
    assert other.sx * other.sz == pytest.approx(base.sx * base.sz, rel=1e-4, abs=0.5)
    assert other.attrs["FitRatio"] == pytest.approx(base.attrs["FitRatio"], abs=2e-3)


@pytest.mark.parametrize("alpha", [0, 30, 60, 90, 120, 150])
def test_p2_2_a_rectangle_turned_by_an_angle_gets_that_yaw(alpha):
    item, _ = layout.building_item(row(turned(rect(BASE, 40, 20), alpha)), FRAME, CFG)
    assert gap180(item.yaw_deg, alpha) < 0.2  # rect() has its long side east-west, which is yaw 0
    assert item.sx == pytest.approx(40 * S, rel=5e-3) and item.sz == pytest.approx(20 * S, rel=5e-3)


@given(st.one_of(st.none(), st.floats(0.1, 200)), st.one_of(st.none(), st.integers(0, 60)))
def test_p2_3_height_follows_the_priority_and_the_box_stands_on_the_ground(height, floors):
    item, _ = layout.building_item(row(rect(BASE, 20, 15), height_m=height, floors_above=floors), FRAME, CFG)
    expected = height if height else (floors * CFG["floor_height_m"] if floors else CFG["default_height_m"])
    assert item.attrs["HeightM"] == pytest.approx(expected, abs=1e-3)
    assert item.sy == pytest.approx(expected * S, abs=2e-3)
    assert item.cy - item.sy / 2 == pytest.approx(0, abs=1e-3)  # the bottom is Y = 0
    assert ("Floors" in item.attrs) == bool(floors)


def test_a_triangle_gets_one_of_its_equally_good_boxes_and_always_the_same_one():
    triangle = [offset(BASE, 0, 0), offset(BASE, 30, 0), offset(BASE, 0, 20)]
    a, _ = layout.building_item(row(triangle), FRAME, CFG)
    b, _ = layout.building_item(row(triangle), FRAME, CFG)
    assert a == b and a.attrs["FitRatio"] == pytest.approx(0.5, abs=1e-3)


def test_a_building_item_carries_what_u4_needs_to_find_it():
    item, _ = layout.building_item(row(rect(BASE, 20, 15), floors_above=3, building_id="osm:77", source="osm"), FRAME, CFG)
    assert (item.kind, item.name, item.material) == ("building", "osm:77", "Concrete")
    assert item.attrs["BuildingId"] == "osm:77" and item.attrs["Source"] == "osm" and item.attrs["CellId"] == CELL
    assert item.attrs["Floors"] == 3


@pytest.mark.parametrize("outline", [[], [[37.5, 126.78]], [[37.5, 126.78], [37.6, 126.8]],
                                     [[37.5, 126.78], [float("nan"), 126.8], [37.4, 126.7]],
                                     [[37.5, 126.78], [37.5, 126.79], [37.5, 126.80]]])  # the last one is a straight line
def test_a_building_that_cannot_be_boxed_is_skipped_with_its_id_in_the_reason(outline):
    item, reason = layout.building_item(row(outline, building_id="gis:99"), FRAME, CFG)
    assert item is None and "gis:99" in reason


@given(st.one_of(star_outlines(spread_m=300), convex_outlines(spread_m=300)), st.floats(0.5, 12))
def test_every_number_in_an_item_has_three_decimals_and_no_negative_zero(outline, scale):
    frame = layout.Frame(FRAME.origin_lat, FRAME.origin_lon, S * scale / 3)
    item, _ = layout.building_item(row(outline), frame, CFG)
    for v in (item.cx, item.cy, item.cz, item.sx, item.sy, item.sz, item.yaw_deg):
        assert math.isfinite(v) and layout.fmt(v) == v
        if v == 0:
            assert math.copysign(1, v) > 0


# --- P2-4, P2-9 road pieces -------------------------------------------------------------------------------

def segments_of(feature):
    pts = feature["geometry"]
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        (ae, an), (be, bn) = layout.to_meters(FRAME, *a), layout.to_meters(FRAME, *b)
        yield i, (ae, an), (be, bn), ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def owner_cells(feature):
    return {h3.latlng_to_cell(*mid, RES) for _, _, _, mid in segments_of(feature)}


def all_pieces(feature, fn):
    return [it for cell in sorted(owner_cells(feature)) for it in fn(feature, FRAME, cell, RES, CFG)]


def expected_width(feature):
    tag = (feature["tags"] or {}).get("width", "")
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[mM]?\s*", tag)
    if m and float(m.group(1)) > 0:
        return min(40.0, max(1.0, float(m.group(1))))
    cls = feature["highway_class"]
    return float(CFG["road_widths_m"]["link" if cls.endswith("_link") else cls])


@settings(max_examples=60)
@given(road_features())
def test_p2_4_each_segment_becomes_one_box_that_covers_it(feature):
    pieces = all_pieces(feature, layout.road_items)
    width = expected_width(feature)
    top = 0.2 if feature["kind"] == "road" else 0.3
    segs = {f"{feature['feature_id']}#{i}": (p, q) for i, p, q, _ in segments_of(feature)}
    assert sorted(p.name for p in pieces) == sorted(segs)  # one piece per segment, none twice (P2-9 as well)
    last = len(feature["geometry"]) - 2
    for piece in pieces:
        (pe, pn), (qe, qn) = segs[piece.name]
        length = math.hypot(qe - pe, qn - pn)
        i = int(piece.name.rsplit("#", 1)[1])
        a, b = (0 if i == 0 else width / 2), (0 if i == last else width / 2)  # past interior joints only (2026-10-16)
        ue, un = (qe - pe) / length, (qn - pn) / length
        assert piece.kind == feature["kind"] and piece.sy == top and piece.cy == pytest.approx(top / 2, abs=1e-3)
        assert piece.sx == pytest.approx((length + a + b) * S, abs=2e-3) and piece.sz == pytest.approx(width * S, abs=2e-3)
        assert piece.cx == pytest.approx(((pe + qe) / 2 + ue * (b - a) / 2) * S, abs=2e-3)
        assert piece.cz == pytest.approx(-((pn + qn) / 2 + un * (b - a) / 2) * S, abs=2e-3)
        assert gap180(piece.yaw_deg, math.degrees(math.atan2(qn - pn, qe - pe))) < 0.01
        for e, n in ((pe, pn), (qe, qn)):
            u, w = local(piece, e * S, -n * S)
            assert abs(u) <= piece.sx / 2 + 0.01 and abs(w) <= piece.sz / 2 + 0.01


@settings(max_examples=40)
@given(road_features())
def test_p2_9_a_cell_that_owns_no_segment_builds_nothing(feature):
    far = h3.latlng_to_cell(FRAME.origin_lat + 0.5, FRAME.origin_lon, RES)
    assert layout.road_items(feature, FRAME, far, RES, CFG) == [] and layout.sidewalk_items(feature, FRAME, far, RES, CFG) == []


def test_a_road_through_two_cells_is_split_by_segment_midpoint():
    nb = next(c for c in h3.grid_disk(CELL, 1) if c != CELL)
    a, n = h3.cell_to_latlng(CELL), h3.cell_to_latlng(nb)
    b = (a[0] + 0.7 * (n[0] - a[0]), a[1] + 0.7 * (n[1] - a[1]))  # the first segment's middle is well inside CELL, the second's inside nb
    feature = {"feature_id": "way:1", "kind": "road", "highway_class": "residential", "tags": {},
               "geometry": [list(a), list(b), list(n)]}
    per_cell = {c: layout.road_items(feature, FRAME, c, RES, CFG) for c in h3.grid_disk(CELL, 1)}
    assert [i.name for i in per_cell[CELL]] == ["way:1#0"] and [i.name for i in per_cell[nb]] == ["way:1#1"]
    assert sum(len(v) for v in per_cell.values()) == 2


def test_zero_length_segments_and_other_kinds_are_not_built():
    p, q = list(BASE), list(offset(BASE, 20, 0))
    feature = {"feature_id": "way:2", "kind": "road", "highway_class": "service", "tags": {}, "geometry": [p, p, q]}
    owner = h3.latlng_to_cell((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, RES)
    assert [i.name for i in layout.road_items(feature, FRAME, owner, RES, CFG)] == ["way:2#1"]
    assert layout.road_items({**feature, "kind": "crossing"}, FRAME, owner, RES, CFG) == []


@pytest.mark.parametrize("tag, cls, kind, expected", [
    ("8", "residential", "road", 8), ("6.5 m", "service", "road", 6.5), ("100", "residential", "road", 40), ("0.2", "tertiary", "road", 1),
    ("abc", "tertiary", "road", 10), (None, "tertiary_link", "road", 6), (None, "footway", "path", 2), (None, "pedestrian", "path", 2.5),
    (None, "mystery", "road", 6), (None, "mystery", "path", 2)])
def test_road_width_comes_from_the_tag_or_the_class_table(tag, cls, kind, expected):
    feature = {"kind": kind, "highway_class": cls, "tags": {"width": tag} if tag else {}}
    assert layout.road_width_m(feature, CFG) == expected


def test_lanes_set_the_width_and_a_named_big_road_without_lanes_uses_the_table():
    cfg = {**CFG, "lane_width_m": 3.25, "road_lanes_by_name": {"길주로": 10}}
    assert layout.road_width_m({"kind": "road", "highway_class": "tertiary", "tags": {"lanes": "4"}}, cfg) == 13.0
    assert layout.road_width_m({"kind": "road", "highway_class": "tertiary", "tags": {"name": "길주로"}}, cfg) == 32.5
    assert layout.road_width_m({"kind": "road", "highway_class": "tertiary", "tags": {"name": "길주로", "oneway": "yes"}}, cfg) == 16.25
    assert layout.road_width_m({"kind": "road", "highway_class": "tertiary", "tags": {"name": "옥산로"}}, cfg) == 10


def test_a_lane_count_by_name_applies_to_big_roads_only():
    """2026-10-16 (45b): an alley also named 부천로 took the big road's 4 lanes."""
    cfg = {**CFG, "lane_width_m": 3.25, "road_lanes_by_name": {"부천로": 4}}
    assert layout.road_width_m({"kind": "road", "highway_class": "primary", "tags": {"name": "부천로"}}, cfg) == 13.0
    assert layout.road_width_m({"kind": "road", "highway_class": "residential", "tags": {"name": "부천로"}}, cfg) == 6


def test_a_road_narrows_to_stop_at_the_buildings_beside_it_but_keeps_a_floor():
    """2026-10-16 (원미동·춘의동): 6 m alleys ran into houses 2.2 m from the centre line; a record across the road keeps 60 %."""
    road = {"feature_id": "way:1", "kind": "road", "highway_class": "residential", "tags": {},
            "geometry": [list(offset(BASE, 0, -40)), list(offset(BASE, 0, 40))]}
    def house(e0, e1):
        return {"status": "ok", "outline": [list(offset(BASE, e, n)) for e, n in ((e0, -5), (e1, -5), (e1, 5), (e0, 5))]}
    fits = layout.fit_road_widths([road], [house(2.2, 12)], FRAME, CFG)
    assert abs(fits["way:1"] - 2 * (2.2 - layout.FIT_MARGIN_M)) < 0.05
    assert layout.road_width_m(road, {**CFG, "road_width_fit": fits}) == fits["way:1"]
    assert layout.fit_road_widths([road], [house(-1, 1)], FRAME, CFG)["way:1"] == 3.6
    assert layout.fit_road_widths([road], [house(1.0, 12)], FRAME, CFG)["way:1"] == layout.FIT_MIN_M
    assert layout.fit_road_widths([road], [house(4, 12)], FRAME, CFG) == {}


def test_a_driveway_loses_the_part_inside_a_building():
    """2026-10-16 (1ab, 1c7): OSM service ways ran through buildings into their car parks."""
    road = {"feature_id": "way:2", "kind": "road", "highway_class": "service", "tags": {},
            "geometry": [list(offset(BASE, -30, 0)), list(offset(BASE, 30, 0))]}
    block = {"status": "ok", "outline": [list(offset(BASE, e, n)) for e, n in ((-5, -8), (5, -8), (5, 8), (-5, 8))]}
    out = layout.driveways_off_buildings([road], [block], FRAME)
    assert [f["feature_id"] for f in out] == ["way:2.0", "way:2.1"]
    big = {**road, "highway_class": "tertiary"}
    assert layout.driveways_off_buildings([big], [block], FRAME) == [big]
    ramp = {**road, "feature_id": "way:3", "tags": {"tunnel": "yes"}}
    assert layout.driveways_off_buildings([ramp], [], FRAME) == []


def test_segment_names_sort_by_number_not_by_text():
    pts = [list(offset(BASE, 10 * i, 0)) for i in range(14)]
    feature = {"feature_id": "way:3", "kind": "road", "highway_class": "residential", "tags": {}, "geometry": pts}
    items = layout.order_items(all_pieces(feature, layout.road_items))
    assert [i.seq for i in items] == list(range(13))


# --- P2-5 sidewalks -----------------------------------------------------------------------------------------------

def expected_sides(feature):
    if feature["kind"] != "road":
        return set()
    tag = feature["tags"].get("sidewalk")
    if tag is not None:
        return {"both": {"L", "R"}, "left": {"L"}, "right": {"R"}}.get(tag.strip().lower(), set())
    tags = feature["tags"]
    if isinstance(tags.get("sidewalk:both"), str):
        return {"L", "R"} if tags["sidewalk:both"].strip().lower() in ("yes", "separate") else set()
    return {"L", "R"} if feature["highway_class"].replace("_link", "") in BIG or feature["highway_class"] == "residential" else set()


@settings(max_examples=60)
@given(road_features())
def test_p2_5_sidewalks_follow_the_tag_then_the_class_and_sit_beside_the_road(feature):
    pieces = {p.name: p for p in all_pieces(feature, layout.sidewalk_items)}
    sides = expected_sides(feature)
    segs = list(segments_of(feature))
    assert set(pieces) == {f"{feature['feature_id']}#{i}{s}" for i, *_ in segs for s in sides}
    sw, offset_m = CFG["sidewalk_width_m"], expected_width(feature) / 2 + CFG["sidewalk_width_m"] / 2
    for i, (pe, pn), (qe, qn), _ in segs:
        length = math.hypot(qe - pe, qn - pn)
        ux, uy = (qe - pe) / length, (qn - pn) / length
        mid = ((pe + qe) / 2, (pn + qn) / 2)
        for side in sides:
            piece = pieces[f"{feature['feature_id']}#{i}{side}"]
            ce, cn = piece.cx / S, -piece.cz / S
            de, dn = ce - mid[0], cn - mid[1]
            assert math.hypot(de, dn) == pytest.approx(offset_m, abs=2e-3)
            assert (de * -uy + dn * ux) * (1 if side == "L" else -1) > 0  # left of the drawn direction is L
            assert abs(de * ux + dn * uy) < 2e-3  # straight out from the center line, no sliding along it
            assert piece.sx == pytest.approx((length + sw) * S, abs=2e-3) and piece.sz == pytest.approx(sw * S, abs=2e-3)
            assert piece.sy == 0.4 and gap180(piece.yaw_deg, math.degrees(math.atan2(uy, ux))) < 0.01


def test_sidewalks_stay_off_paths_small_roads_and_no_tags():
    line = [list(offset(BASE, 0, 0)), list(offset(BASE, 30, 0))]
    cell = h3.latlng_to_cell(*[(line[0][0] + line[1][0]) / 2, (line[0][1] + line[1][1]) / 2], RES)
    make = lambda cls, kind="road", **tags: layout.sidewalk_items({"feature_id": "way:5", "kind": kind, "highway_class": cls, "tags": tags, "geometry": line}, FRAME, cell, RES, CFG)
    assert make("tertiary") and len(make("tertiary")) == 2 and len(make("tertiary_link")) == 2
    assert len(make("residential")) == 2 and make("living_street") == [] and make("footway", "path") == []  # U5 BR-11.13: residential both sides
    assert make("tertiary", sidewalk="no") == [] and make("tertiary", sidewalk="none") == []
    assert len(make("residential", sidewalk="both")) == 2  # the OSM tag wins over the class default
    assert len(make("tertiary", sidewalk="left")) == 1 and len(make("tertiary", sidewalk="right")) == 1
    assert make("tertiary", sidewalk="separate") == []


# --- P2-6 ground -----------------------------------------------------------------------------------------------

cells_near = st.builds(lambda a, b: h3.latlng_to_cell(FRAME.origin_lat + a, FRAME.origin_lon + b, RES), st.floats(-0.01, 0.01), st.floats(-0.012, 0.012))


@given(cells_near)
def test_p2_6_the_ground_covers_the_cell_with_a_margin_and_its_top_is_y_zero(cell):
    g = layout.ground_item(cell, FRAME, CFG)
    margin = CFG["ground_margin_m"] * S
    for lat, lon in h3.cell_to_boundary(cell):
        x, z = layout.to_studs(FRAME, lat, lon)
        assert g.cx - g.sx / 2 + margin - 0.01 <= x <= g.cx + g.sx / 2 - margin + 0.01
        assert g.cz - g.sz / 2 + margin - 0.01 <= z <= g.cz + g.sz / 2 - margin + 0.01
    assert g.cy + g.sy / 2 == pytest.approx(0, abs=1e-3) and g.sy == 4 and max(g.sx, g.sz) <= 2048
    assert (g.kind, g.material, g.name) == ("ground", "Concrete", "Ground")  # U5 BR-11.14: paved ground


def test_p2_6_a_cell_too_big_for_one_part_is_an_error():
    with pytest.raises(ValueError, match="2048"):
        layout.ground_item(h3.latlng_to_cell(FRAME.origin_lat, FRAME.origin_lon, 6), FRAME, CFG)


# --- P2-7 chunks, P2-8 order -----------------------------------------------------------------------------------------

@given(st.lists(st.integers(), max_size=200), st.integers(1, 80))
def test_p2_7_chunks_join_back_to_the_list_and_none_is_too_big_or_empty(items, size):
    chunks = layout.chunk_items(items, size)
    assert list(itertools.chain.from_iterable(chunks)) == items
    assert all(0 < len(c) <= size for c in chunks) and len(chunks) == math.ceil(len(items) / size)
    assert layout.chunk_items(items, size) == chunks


def test_a_chunk_size_below_one_is_refused():
    with pytest.raises(ValueError):
        layout.chunk_items([1, 2], 0)


@settings(max_examples=40)
@given(st.lists(road_features(max_points=4), max_size=4, unique_by=lambda f: f["feature_id"]), st.integers(0, 10**6))
def test_p2_8_the_order_does_not_depend_on_the_order_of_the_input(features, seed):
    items = [layout.ground_item(CELL, FRAME, CFG)]
    for f in features:
        items += all_pieces(f, layout.road_items) + all_pieces(f, layout.sidewalk_items)
    for i in range(3):
        items.append(layout.building_item(row(rect(offset(BASE, 40 * i, 0), 20, 15), building_id=f"gis:{i}"), FRAME, CFG)[0])
    ordered = layout.order_items(items)
    shuffled = list(items)
    random.Random(seed).shuffle(shuffled)
    assert layout.order_items(shuffled) == ordered
    kinds = [layout.ORDER[i.kind] for i in ordered]
    assert kinds == sorted(kinds) and ordered[0].kind == "ground"


# --- spawn (BR-5) -------------------------------------------------------------------------------------------------------

def road_through(point, length_m=60):
    a, b = offset(point, -length_m / 2, 0), offset(point, length_m / 2, 0)
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    feature = {"feature_id": "way:9", "kind": "road", "highway_class": "residential", "tags": {}, "geometry": [list(a), list(b)]}
    cell = h3.latlng_to_cell(*mid, RES)
    return cell, layout.road_items(feature, FRAME, cell, RES, CFG)


def test_no_spawn_without_a_configured_point_or_in_another_cell():
    cell, pieces = road_through(BASE)
    assert layout.spawn_item(cell, FRAME, CFG, pieces) == (None, [])
    cfg = {**CFG, "spawn_lat": BASE[0], "spawn_lon": BASE[1]}
    other = next(c for c in h3.grid_disk(cell, 1) if c != h3.latlng_to_cell(BASE[0], BASE[1], RES))
    assert layout.spawn_item(other, FRAME, cfg, pieces) == (None, [])


def test_spawn_on_a_road_has_no_warning_and_sits_just_above_the_road():
    cell, pieces = road_through(BASE)
    cfg = {**CFG, "spawn_lat": BASE[0], "spawn_lon": BASE[1], "spawn_yaw_deg": 90}
    cell = h3.latlng_to_cell(BASE[0], BASE[1], RES)
    item, warnings = layout.spawn_item(cell, FRAME, cfg, pieces)
    assert warnings == [] and (item.kind, item.name, item.yaw_deg) == ("spawn", "Spawn", 90.0)
    assert item.cy + item.sy / 2 == pytest.approx(0.25, abs=1e-3) and (item.sx, item.sz) == (6.0, 6.0)
    x, z = layout.to_studs(FRAME, *BASE)
    assert (item.cx, item.cz) == (layout.fmt(x), layout.fmt(z))


def test_spawn_off_the_road_is_built_with_a_warning():
    _, pieces = road_through(BASE)
    off = offset(BASE, 0, 40)  # 40 m north of an east-west road
    cfg = {**CFG, "spawn_lat": off[0], "spawn_lon": off[1]}
    item, warnings = layout.spawn_item(h3.latlng_to_cell(*off, RES), FRAME, cfg, pieces)
    assert item is not None and warnings == ["spawn point is not on a road or path"]


# --- U4: a building item from its final value (BR-9) ----------------------------------------------------------------------------

def test_u4_a_building_item_takes_height_floors_color_and_attributes_from_the_final_value():
    b = {**row(rect(BASE, 20, 12)), "building_id": "gis:1", "cell_id": "8930e0af13bffff", "source": "gis", "floors_above": 3, "height_m": 10.2}
    est = {"floors_seen": 4, "confidence": "high", "height_est_m": None, "wall_color": "red_brick", "roof_shape": None}
    eff = judgement.effective_building(b, est, None, CFG)
    item, _ = layout.building_item(b, FRAME, CFG, eff)
    assert item.sy == pytest.approx(4 * 3.4 * 3.6, abs=1e-3) and item.cy == pytest.approx(item.sy / 2, abs=1e-3)
    assert item.color == tuple(CFG["wall_colors"]["red_brick"]) and item.material == "Concrete"
    assert item.attrs["Floors"] == 4 and item.attrs["HeightBasis"] == "from_floors" and item.attrs["FloorsBasis"] == "photo_count"
    assert item.attrs["WallColor"] == "red_brick" and item.attrs["Review"] == "changed"
    old, _ = layout.building_item(b, FRAME, CFG)
    assert old.color == (200, 200, 205) and "WallColor" not in old.attrs and old.attrs["HeightM"] == 10.2  # without eff: U2 as before


def test_u4_an_other_color_is_painted_light_gray_but_keeps_its_name():
    b = {**row(rect(BASE, 20, 12)), "building_id": "gis:1", "cell_id": "8930e0af13bffff", "source": "gis", "floors_above": 3, "height_m": None}
    eff = judgement.effective_building(b, None, {"wall_color": "other"}, CFG)
    item, _ = layout.building_item(b, FRAME, CFG, eff)
    assert item.color == (200, 200, 205) and item.attrs["WallColor"] == "other"


def test_road_overlaps_counts_a_building_box_on_a_road_box():
    import road_overlaps as RO
    road = {"k": "road", "n": "way:1#0", "x": 0, "z": 0, "w": 100, "d": 20, "r": 0}
    on = {"k": "building", "n": "gis:1#b0", "x": 0, "z": 15, "w": 20, "d": 20, "r": 0}
    off = {"k": "building", "n": "gis:2", "x": 0, "z": 40, "w": 20, "d": 20, "r": 0}
    assert RO.overlaps({"chunks": [{"items": [road, on, off]}]}) == {"gis:1": 100.0}
