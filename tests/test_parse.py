"""Parsing and paging (P-10) plus end-to-end checks of cells.py and register.py with fake HTTP.

Fixtures in tests/fixtures are trimmed real responses captured on 2026-10-13 (no keys inside).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import h3
import pytest
from hypothesis import given, settings, strategies as st

import cells
import common
import db
import geo
import register
from generators import BASE, RES, offset, star_outlines

FIX = Path(__file__).parent / "fixtures"
CELL = "8930e0af13bffff"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clear_secrets():
    common._SECRETS.clear()
    yield
    common._SECRETS.clear()


# --- parse_osm ----------------------------------------------------------------------------

def _way(osm_id, tags, points):
    return {"type": "way", "id": osm_id, "tags": tags, "geometry": [{"lat": a, "lon": b} for a, b in points]}


def test_parse_osm_real_sample_gives_buildings_and_roads():
    sample = load("overpass_sample.json")
    parsed = cells.parse_osm(sample, RES, CELL)
    n_buildings = sum(1 for e in sample["elements"] if "building" in e.get("tags", {}))
    assert len(parsed.buildings) == n_buildings == 3 and parsed.dropped == 0
    assert all(isinstance(b, geo.OsmBuilding) for b in parsed.buildings)
    assert 1 <= len(parsed.features) <= 5
    assert {f["kind"] for f in parsed.features} <= {"road", "path", "crossing"}
    assert all(f["feature_id"].startswith("way:") for f in parsed.features)


def test_parse_osm_nodes_and_classes():
    nodes = [
        {"type": "node", "id": 1, "lat": BASE[0], "lon": BASE[1], "tags": {"natural": "tree"}},
        {"type": "node", "id": 2, "lat": BASE[0], "lon": BASE[1], "tags": {"highway": "street_lamp"}},
        {"type": "node", "id": 3, "lat": BASE[0], "lon": BASE[1], "tags": {"amenity": "bench"}},
        {"type": "node", "id": 4, "lat": BASE[0], "lon": BASE[1], "tags": {"highway": "crossing"}},
        {"type": "node", "id": 5, "lat": BASE[0], "lon": BASE[1], "tags": {"shop": "kiosk"}},  # ignored, not an error
        _way(10, {"highway": "footway", "footway": "crossing"}, [BASE, offset(BASE, 5, 0)]),
        _way(11, {"highway": "residential"}, [BASE, offset(BASE, 50, 0)]),
        _way(12, {"highway": "steps"}, [BASE, offset(BASE, 5, 5)]),
        _way(13, {"highway": "proposed"}, [BASE, offset(BASE, 5, 5)]),  # not a usable class
    ]
    parsed = cells.parse_osm({"elements": nodes}, RES, CELL)
    kinds = {f["feature_id"]: (f["kind"], f["highway_class"]) for f in parsed.features}
    assert kinds == {"node:1": ("tree", None), "node:2": ("street_lamp", None), "node:3": ("bench", None),
                     "node:4": ("crossing", "crossing"), "way:10": ("crossing", "footway"),
                     "way:11": ("road", "residential"), "way:12": ("path", "steps")}
    assert parsed.dropped == 0


def test_parse_osm_drops_malformed_elements_and_counts_them():
    far = [(37.56, 126.97), (37.5601, 126.97), (37.5601, 126.9701)]  # Seoul City Hall, far from the cell
    elements = [
        {"type": "way", "id": 1, "tags": {"building": "yes"}},                              # no geometry
        {"type": "way", "id": "x", "tags": {"building": "yes"}, "geometry": []},            # bad id
        _way(3, {"building": "yes", "height": 5}, [BASE, offset(BASE, 5, 0), offset(BASE, 5, 5)]),  # non-string tag
        {"type": "node", "id": 4, "lat": 999, "lon": 0, "tags": {"natural": "tree"}},       # out of range
        _way(5, {"building": "yes"}, far),                                                  # not near the cell
        "not an element",
        _way(6, {"building": "yes"}, [BASE, offset(BASE, 20, 0), offset(BASE, 20, 20), offset(BASE, 0, 20)]),  # fine
    ]
    parsed = cells.parse_osm({"elements": elements}, RES, CELL)
    assert [b.osm_id for b in parsed.buildings] == [6] and parsed.dropped == 6


def test_parse_osm_rejects_a_response_that_is_not_overpass():
    for bad in ({}, {"elements": "x"}, [], None, {"remark": "runtime error: Query timed out"}):
        with pytest.raises(ValueError):
            cells.parse_osm(bad, RES, CELL)


# --- street features per cell ------------------------------------------------------------------

def test_a_long_road_is_stored_for_every_cell_it_crosses():
    a, b = offset(BASE, -400, 0), offset(BASE, 400, 0)
    touched = cells.cells_touched([a, b], RES)
    assert {geo.assign_cell(a, RES), geo.assign_cell(b, RES), geo.assign_cell(offset(BASE, 0, 0), RES)} <= touched
    assert len(touched) >= 2
    feature = {"feature_id": "way:1", "kind": "road", "highway_class": "residential",
               "geometry": [list(a), list(b)], "tags": {}}
    for c in touched:
        assert [r["cell_id"] for r in cells.street_rows_for_cell([feature], c, RES)] == [c]
    far_cell = h3.latlng_to_cell(37.56, 126.97, RES)
    assert cells.street_rows_for_cell([feature], far_cell, RES) == []


@given(st.lists(st.tuples(st.floats(-300, 300), st.floats(-300, 300)), min_size=1, max_size=6))
def test_cells_touched_includes_every_vertex_cell(offsets):
    pts = [offset(BASE, dx, dy) for dx, dy in offsets]
    assert {geo.assign_cell(p, RES) for p in pts} <= cells.cells_touched(pts, RES)


# --- cells.py arguments -----------------------------------------------------------------------------

def test_fill_cells_and_cell_validation():
    ring = [offset(BASE, -800, -800), offset(BASE, 800, -800), offset(BASE, 800, 800), offset(BASE, -800, 800)]
    assert cells.fill_cells(ring, RES)
    with pytest.raises(ValueError):
        cells.fill_cells([offset(BASE, -5, -5), offset(BASE, 5, -5), offset(BASE, 5, 5)], RES)  # no cell center inside
    with pytest.raises(ValueError):
        cells.fill_cells(ring[:2], RES)
    assert cells.check_cells([CELL, CELL], RES) == [CELL]
    for bad in ("zzz", h3.latlng_to_cell(37.5, 126.7, 8)):
        with pytest.raises(ValueError):
            cells.check_cells([bad], RES)


def test_parse_args_accepts_both_forms_and_rejects_mixed_or_incomplete_input():
    assert cells.parse_args(["--cells", CELL], RES) == [CELL]
    zone = ["9", "37.5,126.77", "37.5,126.79", "37.51,126.79", "37.51,126.77"]
    assert cells.parse_args(zone, RES)
    for argv in ([], ["--cells", CELL, "9", "1,2", "3,4", "5,6"], ["8", "1,2", "3,4", "5,6"], ["9", "a,b", "3,4", "5,6"]):
        with pytest.raises(SystemExit):
            cells.parse_args(argv, RES)


@given(st.sampled_from(["8930e0af13bffff", "8930e0af123ffff"]), st.floats(1, 500))
def test_cell_bbox_contains_the_cell_and_grows_with_the_buffer(cell, buffer_m):
    s, w, n, e = cells.cell_bbox(cell, buffer_m)
    for lat, lon in h3.cell_to_boundary(cell):
        assert s < lat < n and w < lon < e
    s0, w0, n0, e0 = cells.cell_bbox(cell, 1)
    assert s <= s0 and w <= w0 and n >= n0 and e >= e0


# --- parse_vworld_page ----------------------------------------------------------------------------------

def test_parse_vworld_real_page():
    buildings, info = register.parse_vworld_page(load("vworld_page1.json"), RES, CELL)
    assert len(buildings) == 2 and info["total"] == 37 and info["pages"] == 19 and info["dropped"] == 0
    for b in buildings:
        assert b.gis_key.isdigit() and b.valid
        assert b.floors_above is None or b.floors_above >= 1
        assert h3.is_valid_cell(b.cell_id)


def test_parse_vworld_empty_area_and_error_codes():
    assert register.parse_vworld_page(load("vworld_empty.json"), RES, CELL)[0] == []
    with pytest.raises(register.VworldError) as err:
        register.parse_vworld_page(load("vworld_invalid_key.json"), RES, CELL)
    assert "INVALID_KEY" in str(err.value)
    for bad in ({}, [], None, {"response": {"status": "OK"}}, {"response": {"status": "OK", "record": {"total": "x"}}}):
        with pytest.raises(register.VworldError):
            register.parse_vworld_page(bad, RES, CELL)


def test_parse_vworld_drops_malformed_features_and_counts_extra_polygons():
    page = load("vworld_page1.json")
    feats = page["response"]["result"]["featureCollection"]["features"]
    broken = copy.deepcopy(page)
    bf = broken["response"]["result"]["featureCollection"]["features"]
    bf[0]["id"] = "something.else"
    bf[1]["geometry"] = {"type": "Point", "coordinates": [126.77, 37.5]}
    _, info = register.parse_vworld_page(broken, RES, CELL)
    assert info["dropped"] == 2
    multi = copy.deepcopy(page)
    extra = [[[p[0] + 0.0001, p[1]] for p in feats[0]["geometry"]["coordinates"][0][0]]]
    multi["response"]["result"]["featureCollection"]["features"][0]["geometry"]["coordinates"].append(extra)
    _, info = register.parse_vworld_page(multi, RES, CELL)
    assert info["polygons_dropped"] == 1


# --- merge_pages (P-10) ------------------------------------------------------------------------------------

def _gis_list(outlines):
    return [geo.new_gis_building(str(1000 + i), ol, {"grnd_flr": "3"}, RES) for i, ol in enumerate(outlines)]


def _pages(buildings, cuts):
    bounds = [0, *sorted(set(c for c in cuts if 0 < c < len(buildings))), len(buildings)]
    chunks = [buildings[a:b] for a, b in zip(bounds, bounds[1:])]
    total = len(buildings)
    return [(c, {"total": total, "pages": len(chunks), "dropped": 0, "polygons_dropped": 0}) for c in chunks]


@settings(max_examples=40)
@given(st.lists(star_outlines(), min_size=0, max_size=8), st.lists(st.integers(0, 8)), st.data())
def test_p10_any_page_split_merges_to_the_same_result(outlines, cuts, data):
    buildings = _gis_list(outlines)
    merged, info = register.merge_pages(_pages(buildings, cuts))
    assert merged == sorted(buildings, key=lambda b: b.gis_key) and info["total"] == len(buildings)
    shuffled = data.draw(st.permutations(_pages(buildings, cuts)))
    assert register.merge_pages(shuffled)[0] == merged


@given(st.lists(star_outlines(), min_size=2, max_size=8))
def test_p10_missing_or_duplicated_records_and_changed_totals_are_errors(outlines):
    buildings = _gis_list(outlines)
    short = _pages(buildings[:-1], [1])
    short = [(b, {**i, "total": len(buildings)}) for b, i in short]
    with pytest.raises(register.VworldError):
        register.merge_pages(short)                                    # one record never arrived
    dup = _pages(buildings[:-1] + [buildings[0]], [1])
    dup = [(b, {**i, "total": len(buildings)}) for b, i in dup]
    with pytest.raises(register.VworldError):
        register.merge_pages(dup)                                      # a duplicate hides a missing one
    changed = _pages(buildings, [1])
    changed[0][1]["total"] += 1
    with pytest.raises(register.VworldError):
        register.merge_pages(changed)


# --- fetch_vworld and the two scripts end to end with fake HTTP -----------------------------------------------

def _page_response(features, total, page, pages):
    return {"response": {"status": "OK", "record": {"total": str(total), "current": str(len(features))},
                         "page": {"total": str(pages), "current": str(page), "size": "2"},
                         "result": {"featureCollection": {"type": "FeatureCollection", "features": features}}}}


def _cloned_features(n):
    base = load("vworld_page1.json")["response"]["result"]["featureCollection"]["features"][0]
    out = []
    for i in range(n):
        f = copy.deepcopy(base)
        f["id"] = f"LT_C_BLDGINFO.{9000 + i}"
        f["geometry"]["coordinates"] = [[[[p[0] + 0.0002 * i, p[1]] for p in ring] for ring in base["geometry"]["coordinates"][0]]]
        out.append(f)
    return out


def test_fetch_vworld_follows_every_page_and_never_leaks_the_key(monkeypatch):
    monkeypatch.setenv("VWORLD_KEY", "  secret-test-key \n")
    feats = _cloned_features(5)
    seen = []

    def fake_get(url, params=None, **kw):
        seen.append(dict(params))
        page = params["page"]
        chunk = feats[(page - 1) * 2: page * 2]
        return _page_response(chunk, 5, page, 3)

    monkeypatch.setattr(common, "http_get_json", fake_get)
    cfg = {**common.DEFAULTS, "vworld_page_size": 2}
    merged, info = register.fetch_vworld(CELL, cfg)
    assert [p["page"] for p in seen] == [1, 2, 3] and all(p["size"] == 2 for p in seen)
    assert all(p["key"] == "secret-test-key" for p in seen)             # surrounding whitespace trimmed
    assert all(p["geomFilter"].startswith("BOX(") for p in seen)
    assert len(merged) == 5 and info["total"] == 5


def test_fetch_vworld_reports_the_error_code_and_stops(monkeypatch):
    monkeypatch.setenv("VWORLD_KEY", "secret-test-key")
    monkeypatch.setattr(common, "http_get_json", lambda *a, **k: load("vworld_invalid_key.json"))
    with pytest.raises(register.VworldError) as err:
        register.fetch_vworld(CELL, common.DEFAULTS)
    assert "INVALID_KEY" in str(err.value) and "secret-test-key" not in str(err.value)


def test_fetch_vworld_without_a_key_names_the_variable(monkeypatch):
    monkeypatch.delenv("VWORLD_KEY", raising=False)
    with pytest.raises(common.MissingSecretError) as err:
        register.fetch_vworld(CELL, common.DEFAULTS)
    assert "VWORLD_KEY" in str(err.value)


def _cfg(tmp_path):
    return {**common.DEFAULTS, "backup_dir": str(tmp_path / "backups"), "log_dir": str(tmp_path / "logs")}


def _snapshot(conn):
    return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()
            for t in ("cells", "osm_buildings", "gis_buildings", "buildings", "street_features")}


def test_collect_cell_end_to_end_is_idempotent_and_backs_up(monkeypatch, tmp_path):
    sample = load("overpass_sample.json")
    monkeypatch.setattr(common, "http_get_json", lambda *a, **k: sample)
    conn = db.connect(tmp_path / "map.db")
    cfg = _cfg(tmp_path)
    counts = cells.collect_cell(conn, cfg, CELL)
    first = _snapshot(conn)
    assert first["cells"] and counts["osm_buildings_fetched"] == len(first["osm_buildings"])
    assert counts["street_features"] == len(first["street_features"])
    cells.collect_cell(conn, cfg, CELL)
    assert _snapshot(conn) == first                                    # P-8 end to end
    assert list((tmp_path / "backups").glob("map-*.db"))


def test_assemble_cell_end_to_end_writes_only_cell_owned_buildings(monkeypatch, tmp_path):
    conn = db.connect(tmp_path / "map.db")
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(common, "http_get_json", lambda *a, **k: load("overpass_sample.json"))
    cells.collect_cell(conn, cfg, CELL)
    gis = register.parse_vworld_page(
        _page_response(_cloned_features(6), 6, 1, 1), RES, CELL)[0]
    monkeypatch.setattr(register, "fetch_vworld", lambda cell, c: (gis, {"total": 6, "pages": 1, "dropped": 0, "polygons_dropped": 0}))
    counts = register.assemble_cell(conn, cfg, CELL)
    rows = db.rows_in_cells(conn, "buildings", [CELL])
    assert rows and all(r["cell_id"] == CELL for r in rows)
    assert counts["buildings_owned"] == len(rows)
    first = _snapshot(conn)
    register.assemble_cell(conn, cfg, CELL)
    assert _snapshot(conn) == first


def test_register_parse_args(monkeypatch):
    assert register.parse_args(["--cells", CELL], RES, []) == [CELL]
    assert register.parse_args(["--all"], RES, ["b", "a"]) == ["a", "b"]
    for argv, known in (([], []), (["--all"], []), (["--all", "--cells", CELL], [CELL])):
        with pytest.raises(SystemExit):
            register.parse_args(argv, RES, known)
