"""Properties P-1..P-7 for src/geo.py plus example tests for the assembly rules."""
from __future__ import annotations

import h3
import pytest
from hypothesis import given, settings, strategies as st
from shapely.geometry import Point, Polygon

import geo
from generators import (BASE, RES, bowtie_outlines, convex_outlines, height_strings, level_strings,
                        offset, rect, scenarios, star_outlines)

THRESHOLD = 0.5


# --- P-1: cell assignment -------------------------------------------------------

@given(star_outlines())
def test_p1_building_belongs_to_the_cell_of_its_centroid(outline):
    b = geo.new_gis_building("1", outline, {}, RES)
    assert b.cell_id == h3.latlng_to_cell(*geo.centroid(outline), RES)
    assert b == geo.new_gis_building("1", outline, {}, RES)  # same input, same result


@given(scenarios(allow_invalid=False))
def test_p1_exactly_one_cell_per_building(sc):
    osm, gis = sc
    cells = {b.cell_id for b in (*osm, *gis)}
    cells |= {n for c in list(cells) for n in h3.grid_disk(c, 1)}
    for b in (*osm, *gis):
        assert sum(1 for c in cells if b.cell_id == c) == 1


# --- P-2: centroid ----------------------------------------------------------------

@given(star_outlines())
def test_p2_centroid_inside_bounding_box(outline):
    lat, lon = geo.centroid(outline)
    lats, lons = [p[0] for p in outline], [p[1] for p in outline]
    assert min(lats) - 1e-9 <= lat <= max(lats) + 1e-9
    assert min(lons) - 1e-9 <= lon <= max(lons) + 1e-9


@given(star_outlines(), st.floats(-50, 50), st.floats(-50, 50))
def test_p2_centroid_moves_with_the_outline(outline, dx, dy):
    moved = tuple(offset(p, dx, dy) for p in outline)
    c0, c1 = geo.centroid(outline), geo.centroid(moved)
    expected = offset(c0, dx, dy)
    assert c1[0] == pytest.approx(expected[0], abs=1e-6)
    assert c1[1] == pytest.approx(expected[1], abs=1e-6)


@given(convex_outlines())
def test_p2_centroid_inside_convex_outline(outline):
    lat, lon = geo.centroid(outline)
    assert Polygon([(p[1], p[0]) for p in outline]).contains(Point(lon, lat))


def test_p2_no_area_falls_back_to_vertex_mean():
    line = ((BASE[0], BASE[1]), (BASE[0] + 1e-4, BASE[1] + 1e-4), (BASE[0] + 2e-4, BASE[1] + 2e-4))
    assert geo.centroid(line) == pytest.approx((BASE[0] + 1e-4, BASE[1] + 1e-4))


# --- P-3: overlap ratio -------------------------------------------------------------

@given(star_outlines(), star_outlines())
def test_p3_overlap_ratio_bounds_and_symmetry(a, b):
    r = geo.overlap_ratio(a, b)
    assert 0.0 <= r <= 1.0
    assert r == pytest.approx(geo.overlap_ratio(b, a), abs=1e-6)


@given(star_outlines())
def test_p3_overlap_with_itself_is_one(a):
    assert geo.overlap_ratio(a, a) == pytest.approx(1.0, abs=1e-6)


def test_p3_disjoint_is_zero_and_contained_is_one():
    big, small = rect(BASE, 40, 40), rect(BASE, 10, 10)
    far = rect(offset(BASE, 500, 0), 10, 10)
    assert geo.overlap_ratio(big, far) == 0.0
    assert geo.overlap_ratio(big, small) == pytest.approx(1.0, abs=1e-6)


# --- P-4: assembly ------------------------------------------------------------------

def _overlaps(o, g):
    return geo.overlap_ratio(o.outline, g.outline) >= THRESHOLD


@settings(max_examples=60)
@given(scenarios())
def test_p4_assembly_rules(sc):
    osm, gis = sc
    result = geo.assemble(osm, gis, THRESHOLD)
    ids = [b.building_id for b in result]
    assert len(ids) == len(set(ids))
    valid_gis = [g for g in gis if g.valid]
    valid_osm = [o for o in osm if o.valid]
    # every valid V-World building is in the result
    assert {f"gis:{g.gis_key}" for g in valid_gis} <= set(ids)
    # an OSM building is attached to at most one result building
    attached = [b.osm_id for b in result if b.osm_id is not None]
    assert len(attached) == len(set(attached))
    # OSM-only buildings overlap no V-World building
    by_id = {o.osm_id: o for o in valid_osm}
    for b in result:
        if b.source == "osm":
            assert not any(_overlaps(by_id[b.osm_id], g) for g in valid_gis)
    # invalid outlines never appear
    assert not ({f"gis:{g.gis_key}" for g in gis if not g.valid} & set(ids))
    assert not ({f"osm:{o.osm_id}" for o in osm if not o.valid} & set(ids))


@settings(max_examples=40)
@given(scenarios(), st.data())
def test_p4_input_order_does_not_matter(sc, data):
    osm, gis = sc
    shuffled_osm = data.draw(st.permutations(osm))
    shuffled_gis = data.draw(st.permutations(gis))
    assert geo.assemble(osm, gis, THRESHOLD) == geo.assemble(shuffled_osm, shuffled_gis, THRESHOLD)


# --- P-5: assembling cell by cell gives the same result ------------------------------

@settings(max_examples=40)
@given(scenarios(allow_invalid=False))
def test_p5_cell_by_cell_equals_whole(sc):
    osm, gis = sc
    whole = geo.assemble(osm, gis, THRESHOLD)
    cells = {b.cell_id for b in (*osm, *gis)}
    merged = []
    for c in cells:
        near = set(h3.grid_disk(c, 1))
        part = geo.assemble([o for o in osm if o.cell_id in near],
                            [g for g in gis if g.cell_id in near], THRESHOLD)
        merged += [b for b in part if b.cell_id == c]
    assert sorted(merged, key=lambda b: b.building_id) == whole


# --- P-6: normalization ----------------------------------------------------------------

@given(st.floats(0.1, 500, allow_nan=False))
def test_p6_height_forms_agree(v):
    plain = geo.normalize_height(repr(v))
    assert plain == pytest.approx(v)
    assert geo.normalize_height(f"{v!r} m") == plain
    assert geo.normalize_height(f"  {v!r}  ") == plain


@given(height_strings())
def test_p6_height_is_none_or_positive(raw):
    value = geo.normalize_height(raw)
    assert value is None or value > 0


@given(level_strings())
def test_p6_levels_is_none_or_at_least_one(raw):
    value = geo.normalize_levels(raw)
    assert value is None or (isinstance(value, int) and value >= 1)


@pytest.mark.parametrize("raw,expected", [
    ("18.15", 18.15), ("12 m", 12.0), ("12", 12.0), ("0", None), ("", None), ("-3", None),
    ("abc", None), (None, None), ("1e3", None),
])
def test_p6_height_examples(raw, expected):
    assert geo.normalize_height(raw) == expected


@pytest.mark.parametrize("raw,above,below", [
    ("5", 5, 5), ("0", None, 0), ("", None, None), ("x", None, None), (None, None, None),
])
def test_p6_floor_examples(raw, above, below):
    assert geo.normalize_floors_above(raw) == above
    assert geo.normalize_floors_below(raw) == below


# --- P-7: validity -----------------------------------------------------------------------

@given(star_outlines())
def test_p7_simple_polygons_are_valid(outline):
    assert geo.is_valid_outline(outline)
    assert geo.is_valid_outline(outline + (outline[0],))  # closing point repeated


@given(bowtie_outlines())
def test_p7_self_intersection_is_invalid(outline):
    assert not geo.is_valid_outline(outline)


def test_p7_too_few_points_or_no_area_is_invalid():
    a, b = BASE, offset(BASE, 10, 0)
    assert not geo.is_valid_outline((a, b))
    assert not geo.is_valid_outline((a, a, a, b))
    assert not geo.is_valid_outline((a, b, offset(BASE, 20, 0)))  # collinear


# --- GeoJSON outline ---------------------------------------------------------------------

def _geojson_ring(outline):
    ring = [[p[1], p[0]] for p in outline]
    return ring + [ring[0]]


def test_outline_from_geojson_picks_the_largest_polygon():
    small, big = rect(BASE, 5, 5), rect(offset(BASE, 100, 0), 30, 30)
    geometry = {"type": "MultiPolygon", "coordinates": [[_geojson_ring(small)], [_geojson_ring(big)]]}
    outline, dropped = geo.outline_from_geojson(geometry)
    assert dropped == 1
    assert outline == tuple((p[0], p[1]) for p in big)


def test_outline_from_geojson_accepts_polygon_and_rejects_other_types():
    ring = rect(BASE, 10, 10)
    outline, dropped = geo.outline_from_geojson({"type": "Polygon", "coordinates": [_geojson_ring(ring)]})
    assert dropped == 0 and len(outline) == 4
    with pytest.raises(ValueError):
        geo.outline_from_geojson({"type": "Point", "coordinates": [0, 0]})


# --- assembly examples (business-logic-model.md) -----------------------------------------

def _gis(key, outline, **props):
    return geo.new_gis_building(key, outline, {"grnd_flr": "5", "height": "15", **props}, RES)


def _osm(osm_id, outline, **tags):
    return geo.new_osm_building(osm_id, outline, tags, RES)


def test_example_matching_osm_adds_name_and_tags_but_not_outline():
    g = _gis("1", rect(BASE, 30, 20), bld_nm="V이름")
    o = _osm(7, rect(offset(BASE, 2, 1), 30, 20), name="학교", **{"roof:shape": "flat"})
    [b] = geo.assemble([o], [g], THRESHOLD)
    assert (b.building_id, b.source, b.osm_id, b.name) == ("gis:1", "gis", 7, "학교")
    assert b.outline == g.outline and b.floors_above == 5 and b.osm_tags["roof:shape"] == "flat"


def test_example_osm_overlapping_two_gis_attaches_to_the_better_one():
    a = _gis("1", rect(offset(BASE, -10, 0), 20, 20))
    c = _gis("2", rect(offset(BASE, 12, 0), 12, 20))
    o = _osm(7, rect(BASE, 40, 20), name="큰건물")
    result = {b.building_id: b for b in geo.assemble([o], [a, c], THRESHOLD)}
    assert set(result) == {"gis:1", "gis:2"}
    assert result["gis:1"].osm_id == 7 and result["gis:2"].osm_id is None


def test_example_osm_without_vworld_overlap_stays_as_osm_building():
    g = _gis("1", rect(BASE, 20, 20))
    o = _osm(9, rect(offset(BASE, 200, 0), 20, 20), name="새건물")
    result = {b.building_id: b for b in geo.assemble([o], [g], THRESHOLD)}
    assert set(result) == {"gis:1", "osm:9"}
    assert result["osm:9"].source == "osm" and result["osm:9"].floors_above is None


def test_example_osm_covered_by_a_better_matched_osm_is_dropped():
    g = _gis("1", rect(BASE, 30, 20))
    best = _osm(7, rect(BASE, 30, 20))
    worse = _osm(8, rect(offset(BASE, 3, 0), 25, 20))
    result = {b.building_id for b in geo.assemble([best, worse], [g], THRESHOLD)}
    assert result == {"gis:1"}  # no osm:8, its box would overlap the V-World building
