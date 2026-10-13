"""P-8 (re-collection is idempotent and leaves overrides alone), P-9 (orphan report), rollback, backup."""
from __future__ import annotations

import sqlite3

import pytest
from hypothesis import given, settings, strategies as st

import db
import geo
from generators import RES, scenarios

THRESHOLD = 0.5


def _tables_for(cell_id, osm, gis):
    buildings = geo.assemble(osm, gis, THRESHOLD)
    return {
        "osm_buildings": db.to_rows(osm),
        "gis_buildings": db.to_rows(gis),
        "buildings": db.to_rows(b for b in buildings if b.cell_id == cell_id),
    }


def _snapshot(conn):
    return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()
            for t in ("osm_buildings", "gis_buildings", "buildings", "street_features", "cells")}


def _make_overrides(conn, ids):
    with conn:
        conn.executemany("INSERT INTO overrides (building_id, field, value, cell_id, reason, set_at) "
                         "VALUES (?, 'height_m', '10', 'c', 'test', '2026-10-13T00:00:00+00:00')", [(i,) for i in ids])


@settings(max_examples=25, deadline=None)
@given(scenarios(allow_invalid=False))
def test_p8_replacing_twice_gives_the_same_state_and_keeps_overrides(sc):
    osm, gis = sc
    cells = sorted({b.cell_id for b in (*osm, *gis)}) or ["8930e0af13bffff"]
    conn = db.connect(":memory:")
    _make_overrides(conn, ["gis:1000", "osm:5000"])
    before_overrides = conn.execute("SELECT * FROM overrides ORDER BY building_id").fetchall()
    for c in cells:
        db.replace_cell_rows(conn, c, _tables_for(c, osm, gis))
    first = _snapshot(conn)
    for c in cells:
        db.replace_cell_rows(conn, c, _tables_for(c, osm, gis))
    assert _snapshot(conn) == first
    assert conn.execute("SELECT * FROM overrides ORDER BY building_id").fetchall() == before_overrides


@settings(max_examples=25, deadline=None)
@given(st.sets(st.sampled_from([f"gis:{i}" for i in range(6)] + [f"osm:{i}" for i in range(4)])),
       st.sets(st.sampled_from([f"gis:{i}" for i in range(6)] + [f"osm:{i}" for i in range(4)])))
def test_p9_orphans_are_override_ids_minus_building_ids(override_ids, building_ids):
    conn = db.connect(":memory:")
    with conn:
        for bid in building_ids:
            conn.execute(
                "INSERT INTO buildings (building_id, cell_id, source, outline, centroid, status) "
                "VALUES (?, 'c', 'gis', '[]', '[0,0]', 'ok')", (bid,))
    _make_overrides(conn, sorted(override_ids))
    assert db.orphans(conn) == [("overrides", i) for i in sorted(override_ids - building_ids)]


def test_orphans_ignores_tables_that_do_not_exist_yet():
    assert db.orphans(db.connect(":memory:")) == []


def test_failed_replacement_rolls_everything_back():
    conn = db.connect(":memory:")
    good = {"street_features": [dict(feature_id="way:1", cell_id="c1", kind="road", highway_class="residential",
                                     geometry=[[1, 2], [3, 4]], tags={})]}
    db.replace_cell_rows(conn, "c1", good)
    before = _snapshot(conn)
    # the second row has a null in a NOT NULL column, so the whole call must fail and change nothing
    bad = {"street_features": [
        dict(feature_id="way:2", cell_id="c1", kind="road", highway_class=None, geometry=[[0, 0]], tags=None),
        dict(feature_id="way:3", cell_id="c1", kind=None, highway_class=None, geometry=[[0, 0]], tags=None),
    ]}
    with pytest.raises(sqlite3.IntegrityError):
        db.replace_cell_rows(conn, "c1", bad)
    assert _snapshot(conn) == before


def test_unknown_table_or_mismatched_columns_are_rejected():
    conn = db.connect(":memory:")
    with pytest.raises(ValueError):
        db.replace_cell_rows(conn, "c", {"overrides": []})
    with pytest.raises(ValueError):
        db.replace_cell_rows(conn, "c", {"cells": [{"cell_id": "c"}]})


def test_neighbor_rows_are_overwritten_by_id_but_not_deleted():
    conn = db.connect(":memory:")
    def row(osm_id, cell):
        return dict(osm_id=osm_id, cell_id=cell, outline=[[0, 0], [0, 1], [1, 1]], centroid=[0.3, 0.6],
                    tags={"name": "a"}, height_m=None, levels=None, valid=True)
    db.replace_cell_rows(conn, "A", {"osm_buildings": [row(1, "A"), row(2, "B")]})
    db.replace_cell_rows(conn, "B", {"osm_buildings": [row(2, "B"), row(3, "B")]})
    ids = {r["osm_id"]: r["cell_id"] for r in db.rows_in_cells(conn, "osm_buildings", ["A", "B"])}
    assert ids == {1: "A", 2: "B", 3: "B"}  # A's building 1 survives B's run


def test_rows_round_trip_json_and_bool_columns():
    conn = db.connect(":memory:")
    r = dict(osm_id=7, cell_id="A", outline=[[1.5, 2.5], [3.5, 4.5], [5.5, 6.5]], centroid=[3.5, 4.5],
             tags={"name": "한글"}, height_m=12.5, levels=3, valid=False)
    db.replace_cell_rows(conn, "A", {"osm_buildings": [r]})
    assert db.rows_in_cells(conn, "osm_buildings", ["A"]) == [r]


def test_backup_copies_the_database_and_keeps_only_the_newest(tmp_path):
    conn = db.connect(tmp_path / "map.db")
    db.replace_cell_rows(conn, "A", {"cells": [dict(cell_id="A", res=9, center_lat=1.0, center_lon=2.0, boundary=[])]})
    paths = [db.backup(conn, tmp_path / "backups", keep=3, stamp=f"2026101{i}-000000-000000") for i in range(5)]
    kept = sorted(p.name for p in (tmp_path / "backups").glob("map-*.db"))
    assert kept == [p.name for p in paths[-3:]]
    restored = sqlite3.connect(paths[-1])
    assert restored.execute("SELECT cell_id FROM cells").fetchall() == [("A",)]
    restored.close()


def test_record_run_stores_counts_and_error(tmp_path):
    conn = db.connect(tmp_path / "map.db")
    rid = db.record_run(conn, cell_id="A", unit="C1", started_at="2026-10-13T00:00:00Z",
                        finished_at="2026-10-13T00:01:00Z", status="failed", counts={"osm": 8}, error="boom")
    row = conn.execute("SELECT unit, status, counts, error FROM collection_runs WHERE id = ?", (rid,)).fetchone()
    assert row == ("C1", "failed", '{"osm": 8}', "boom")


def test_foreign_keys_pragma_is_on():
    assert db.connect(":memory:").execute("PRAGMA foreign_keys").fetchone() == (1,)


# --- U3: captures and building_views ---------------------------------------------------------------

def _view(building_id, rank=1, pano_id="p1", status="planned", crop_path=None):
    return {"building_id": building_id, "rank": rank, "pano_id": pano_id, "distance_m": 12.5, "bearing_deg": 90.0,
            "yaw_deg": -30.0, "fov_deg": 60.0, "pitch_deg": 5.0, "crop_path": crop_path, "status": status,
            "face_deg": None, "target_lat": None, "target_lon": None}


def _capture(pano_id, **kw):
    return {"pano_id": pano_id, "cell_id": "8930e0af13bffff", "lat": 37.5, "lon": 126.77, "heading_deg": 10.0,
            "captured_at": "2026-05-27T14:28:00", "is_latest": 1, "zoom": None, "width": None, "height": None,
            "file_path": None, "status": "found", "downloaded_at": None, **kw}


def test_views_and_captures_are_replaced_by_key_and_wrong_columns_are_rejected():
    conn = db.connect(":memory:")
    db.upsert_captures(conn, [_capture("p1"), _capture("p2")])
    db.upsert_captures(conn, [_capture("p1", status="downloaded", file_path="c/p1/zoom1.jpg")])
    assert [(c["pano_id"], c["status"]) for c in db.all_captures(conn)] == [("p1", "downloaded"), ("p2", "found")]
    with conn:
        conn.execute("INSERT INTO buildings (building_id, cell_id, source, outline, centroid, status) "
                     "VALUES ('gis:1', 'c1', 'gis', '[]', '[0,0]', 'ok')")
    db.upsert_building_views(conn, [_view("gis:1"), _view("gis:1", rank=2, pano_id="p2")])
    db.upsert_building_views(conn, [_view("gis:1", status="cropped", crop_path="c1/crops/x.jpg")])
    assert [(v["rank"], v["status"]) for v in db.views_for_cell(conn, "c1")] == [(1, "cropped"), (2, "planned")]
    with pytest.raises(ValueError):
        db.upsert_building_views(conn, [{"building_id": "gis:1"}])


@settings(max_examples=25, deadline=None)
@given(scenarios(allow_invalid=False))
def test_deleting_a_cells_views_leaves_other_cells_views_u1_tables_and_overrides_alone(sc):
    osm, gis = sc
    cells = sorted({b.cell_id for b in (*osm, *gis)}) or ["8930e0af13bffff"]
    conn = db.connect(":memory:")
    for c in cells:
        db.replace_cell_rows(conn, c, _tables_for(c, osm, gis))
    owned = {c: [b["building_id"] for b in db.rows_in_cells(conn, "buildings", [c])] for c in cells}
    _make_overrides(conn, [i for ids in owned.values() for i in ids])
    db.upsert_building_views(conn, [_view(i, crop_path=f"{c}/crops/{i}.jpg") for c, ids in owned.items() for i in ids]
                             + [_view(i, rank=2) for ids in owned.values() for i in ids])
    before, overrides = _snapshot(conn), conn.execute("SELECT * FROM overrides ORDER BY building_id").fetchall()
    target = cells[0]
    removed = db.delete_views_for_cell(conn, target)
    assert sorted(removed) == sorted(f"{target}/crops/{i}.jpg" for i in owned[target])
    assert db.views_for_cell(conn, target) == []
    for c in cells[1:]:
        assert len(db.views_for_cell(conn, c)) == 2 * len(owned[c])
    assert _snapshot(conn) == before
    assert conn.execute("SELECT * FROM overrides ORDER BY building_id").fetchall() == overrides


def test_orphan_views_are_listed_and_nothing_is_deleted():
    conn = db.connect(":memory:")
    with conn:
        conn.execute("INSERT INTO buildings (building_id, cell_id, source, outline, centroid, status) "
                     "VALUES ('gis:1', 'c1', 'gis', '[]', '[0,0]', 'ok')")
    db.upsert_building_views(conn, [_view("gis:1"), _view("gis:2"), _view("osm:9", pano_id=None, status="no_photo")])
    assert db.orphan_views(conn) == ["gis:2", "osm:9"]
    assert conn.execute("SELECT COUNT(*) FROM building_views").fetchone()[0] == 3
