"""U5 database functions: detail rows (BR-7.4 atomicity and idempotence), export and import (P5-16), orphans, re-collection safety."""
from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, strategies as st

import common
import db
import details_rules as R
from generators import detail_rows
from test_u4_db import CELL, OTHER, brow

CFG = common.DEFAULTS
T0, T1 = "2026-10-13T01:00:00+00:00", "2026-10-13T02:00:00+00:00"


def make_db(n=3, cell=CELL):
    conn = db.connect(":memory:")
    db.replace_cell_rows(conn, cell, {"buildings": [brow(i, cell) for i in range(1, n + 1)]})
    return conn


def row(bid="gis:1", **kw):
    return {"building_id": bid, "finish": "brick", "ground_use": "shop", "stair": "glass", "bay": 1, "balcony": 0, "roof_color": "dark",
            "rooftop": "none", "note": "dark brick shop house", **kw}


def test_a_detail_row_is_stored_with_the_cell_of_its_building():
    conn = make_db()
    assert db.record_details(conn, [row()], T0) == 1
    (d,) = db.details_in_cell(conn, CELL)
    assert d["building_id"] == "gis:1" and d["finish"] == "brick" and d["bay"] == 1 and d["judged_at"] == T0
    assert db.details_by_building(conn, CELL)["gis:1"]["stair"] == "glass" and db.details_in_cell(conn, OTHER) == []


def test_the_same_row_again_changes_nothing_but_a_different_one_replaces_it_and_its_time():
    conn = make_db()
    db.record_details(conn, [row()], T0)
    db.record_details(conn, [row()], T1)
    assert db.details_in_cell(conn, CELL)[0]["judged_at"] == T0
    db.record_details(conn, [row(bay=0)], T1)
    (d,) = db.details_in_cell(conn, CELL)
    assert d["bay"] == 0 and d["judged_at"] == T1


@pytest.mark.parametrize("bad", [row("gis:99"), row(finish="wood"), row(bay=True), {"building_id": "gis:1", "mystery": 1}, "x",
                                 row("gis:1", note="a" * 301)])
def test_one_bad_row_refuses_the_whole_call_and_changes_nothing(bad):
    conn = make_db()
    with pytest.raises(ValueError):
        db.record_details(conn, [row("gis:2"), bad], T0)
    assert db.details_in_cell(conn, CELL) == []


def test_a_building_twice_in_one_call_or_not_ok_is_refused():
    conn = make_db()
    db.replace_cell_rows(conn, OTHER, {"buildings": [brow(9, OTHER, status="invalid")]})
    with pytest.raises(ValueError, match="twice"):
        db.record_details(conn, [row("gis:1"), row("gis:1")], T0)
    with pytest.raises(ValueError, match="status ok"):
        db.record_details(conn, [row("gis:9")], T0)


@settings(max_examples=30)
@given(st.lists(detail_rows(), min_size=1, max_size=3))
def test_p5_16_recording_the_same_rows_twice_is_the_same_as_once(rows):
    conn = make_db()
    rows = [{**r, "building_id": f"gis:{i + 1}"} for i, r in enumerate(rows)]
    db.record_details(conn, rows, T0)
    first = db.details_in_cell(conn, CELL)
    db.record_details(conn, rows, T1)
    assert db.details_in_cell(conn, CELL) == first


def test_export_writes_one_sorted_file_and_import_into_a_fresh_database_gives_the_same_rows(tmp_path):
    conn = make_db()
    db.record_details(conn, [row("gis:2", note=None), row("gis:1")], T0)
    assert db.export_details(conn, OTHER, tmp_path) is None
    path = db.export_details(conn, CELL, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert [d["building_id"] for d in data["details"]] == ["gis:1", "gis:2"] and data["version"] == 1 and list(data) == sorted(data)
    fresh = make_db()
    result = db.import_details(fresh, path)
    assert result == {"cell_id": CELL, "details": 2, "orphans": []}
    assert db.details_in_cell(fresh, CELL) == db.details_in_cell(conn, CELL)
    assert db.export_details(fresh, CELL, tmp_path / "again").read_text(encoding="utf-8") == path.read_text(encoding="utf-8")


def test_import_keeps_unknown_buildings_as_orphans_and_the_orphan_report_sees_them(tmp_path):
    conn = make_db(1)
    text = R.export_details_payload(CELL, [{**R.validate_detail(row("gis:7")), "judged_at": T0}, {**R.validate_detail(row("gis:1")), "judged_at": T0}])
    path = tmp_path / f"{CELL}.json"
    path.write_text(text, encoding="utf-8")
    assert db.import_details(conn, path)["orphans"] == ["gis:7"]
    assert ("details", "gis:7") in db.orphans(conn)


def test_a_bad_file_is_refused_and_the_database_stays(tmp_path):
    conn = make_db()
    db.record_details(conn, [row()], T0)
    path = tmp_path / f"{CELL}.json"
    path.write_text('{"version": 1, "cell_id": "8930e0af13bffff", "details": [{"building_id": "gis:2"}]}', encoding="utf-8")
    with pytest.raises(ValueError):
        db.import_details(conn, path)
    assert [d["building_id"] for d in db.details_in_cell(conn, CELL)] == ["gis:1"]


def test_re_collecting_a_cell_leaves_the_details_alone():
    conn = make_db()
    db.record_details(conn, [row()], T0)
    db.replace_cell_rows(conn, CELL, {"buildings": [brow(1), brow(5)]})
    assert [d["building_id"] for d in db.details_in_cell(conn, CELL)] == ["gis:1"]
    assert "details" not in db.TABLES
