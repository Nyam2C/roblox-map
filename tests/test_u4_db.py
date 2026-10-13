"""U4 database functions: judgements and overrides (P4-3 to P4-7, P4-9 atomicity, P4-16 orphans), export and import files."""
from __future__ import annotations

import json
import os

import pytest
from hypothesis import given, settings, strategies as st

import common
import db
import judgement as J
from generators import REASONS, judgements, override_pairs, override_sets

CFG = common.DEFAULTS
CELL = "8930e0af13bffff"
OTHER = "8930e0af123ffff"
T0, T1 = "2026-10-13T01:00:00+00:00", "2026-10-13T02:00:00+00:00"


def brow(i, cell=CELL, status="ok", floors=3, height=None):
    return {"building_id": f"gis:{i}", "cell_id": cell, "source": "gis", "outline": [[37.5, 126.78], [37.5, 126.7801], [37.5001, 126.7801]],
            "centroid": [37.5, 126.78], "gis_key": str(i), "osm_id": None, "name": "", "osm_tags": None, "floors_above": floors,
            "floors_below": None, "height_m": height, "usability_code": None, "approval_date": None, "building_area": None,
            "osm_height_m": None, "osm_levels": None, "status": status}


def vrow(bid, rank, status="cropped", pano="p1"):
    return {"building_id": bid, "rank": rank, "pano_id": pano, "distance_m": 10.0, "bearing_deg": 0.0, "yaw_deg": 5.0, "fov_deg": 90.0,
            "pitch_deg": 10.0, "crop_path": f"{CELL}/crops/{bid.replace(':', '_')}__{rank}.jpg", "status": status, "face_deg": None,
            "target_lat": None, "target_lon": None}


def make_db(n=3, cell=CELL):
    conn = db.connect(":memory:")
    db.replace_cell_rows(conn, cell, {"buildings": [brow(i, cell) for i in range(1, n + 1)]})
    db.upsert_captures(conn, [{"pano_id": "p1", "cell_id": cell, "lat": 37.5, "lon": 126.78, "heading_deg": 100.0, "captured_at": None,
                               "is_latest": 1, "zoom": 1, "width": 6144, "height": 1024, "file_path": None, "status": "downloaded",
                               "downloaded_at": None}])
    db.upsert_building_views(conn, [vrow(f"gis:{i}", r) for i in range(1, n + 1) for r in (1, 2, 3)])
    return conn


def judgement(bid="gis:1", **kw):
    return {"building_id": bid, "floors_seen": 3, "confidence": "high", "height_est_m": None, "wall_color": "cream", "roof_shape": "flat",
            "views_used": [1, 2], "note": "plain", **kw}


# --- judgements (BR-2) --------------------------------------------------------------------------------------

def test_a_judgement_is_stored_with_the_cell_of_its_building():
    conn = make_db()
    assert db.record_judgements(conn, CFG, [judgement()], T0) == 1
    (row,) = db.estimates_in_cell(conn, CELL)
    assert row == {**J.validate_judgement(judgement(), CFG, {1, 2, 3}), "judged_at": T0}


def test_the_same_judgement_again_changes_nothing_but_a_different_one_replaces_it_and_its_time():
    conn = make_db()
    db.record_judgements(conn, CFG, [judgement()], T0)
    db.record_judgements(conn, CFG, [judgement()], T1)
    assert db.estimates_in_cell(conn, CELL)[0]["judged_at"] == T0
    db.record_judgements(conn, CFG, [judgement(floors_seen=4)], T1)
    row = db.estimates_in_cell(conn, CELL)[0]
    assert (row["floors_seen"], row["judged_at"]) == (4, T1)


@pytest.mark.parametrize("bad", [
    judgement("gis:99"), judgement("../x"), judgement(floors_seen=0), judgement(views_used=[7]), judgement(wall_color="neon"),
])
def test_p4_9_one_bad_judgement_refuses_the_whole_call_and_changes_nothing(bad):
    conn = make_db()
    before = db.estimates_in_cell(conn, CELL)
    with pytest.raises(ValueError):
        db.record_judgements(conn, CFG, [judgement("gis:2"), bad], T0)
    assert db.estimates_in_cell(conn, CELL) == before == []


def test_a_building_is_judged_only_from_its_own_cropped_views_and_only_once_per_call():
    conn = make_db()
    db.upsert_building_views(conn, [vrow("gis:1", 3, status="failed")])
    with pytest.raises(ValueError):
        db.record_judgements(conn, CFG, [judgement(views_used=[3])], T0)  # rank 3 is not cropped
    with pytest.raises(ValueError):
        db.record_judgements(conn, CFG, [judgement(), judgement()], T0)
    db.replace_cell_rows(conn, CELL, {"buildings": [brow(1, status="skipped")]})
    with pytest.raises(ValueError):
        db.record_judgements(conn, CFG, [judgement()], T0)  # status is not ok


# --- overrides (BR-6) -------------------------------------------------------------------------------------

def test_an_override_is_stored_changed_and_removed_and_the_final_value_follows():
    conn = make_db()
    assert db.set_override(conn, CFG, "gis:1", "floors_above", 5, "user saw 5 floors", T0) is True
    assert db.set_override(conn, CFG, "gis:1", "floors_above", 5, "user saw 5 floors", T1) is False  # same: nothing changes
    assert db.overrides_in_cell(conn, CELL)[0]["set_at"] == T0
    eff = {e.building_id: e for e in db.effective_buildings(conn, CFG, CELL)}
    assert (eff["gis:1"].floors_above, eff["gis:1"].floors_basis) == (5, "override")
    assert db.set_override(conn, CFG, "gis:1", "floors_above", 6, "again", T1) is True
    assert db.overrides_by_building(conn, CELL) == {"gis:1": {"floors_above": 6}}
    assert db.unset_override(conn, "gis:1", "floors_above") == CELL
    assert db.unset_override(conn, "gis:1", "floors_above") is None  # nothing left: no error
    assert db.overrides_in_cell(conn, CELL) == []


@pytest.mark.parametrize("args", [
    ("gis:99", "floors_above", 3, "x"), ("gis:1", "floors_above", 0, "x"), ("gis:1", "colour", "cream", "x"), ("gis:1", "floors_above", 3, ""),
    ("../x", "floors_above", 3, "x"),
])
def test_p4_9_a_bad_override_changes_nothing(args):
    conn = make_db()
    with pytest.raises(ValueError):
        db.set_override(conn, CFG, *args, T0)
    assert db.overrides_in_cell(conn, CELL) == []


def final(conn):
    return db.effective_buildings(conn, CFG, CELL)


@given(override_pairs(), REASONS)
@settings(max_examples=40)
def test_p4_4_setting_then_unsetting_gives_back_the_final_values(pair, reason):
    conn = make_db()
    db.record_judgements(conn, CFG, [judgement("gis:1")], T0)
    before = final(conn)
    db.set_override(conn, CFG, "gis:1", pair[0], pair[1], reason, T1)
    db.unset_override(conn, "gis:1", pair[0])
    assert final(conn) == before


@given(override_sets(), st.randoms(use_true_random=False), REASONS)
@settings(max_examples=40)
def test_p4_5_overrides_on_different_fields_can_be_set_in_any_order(ov, rnd, reason):
    items = list(ov.items())
    shuffled = list(items)
    rnd.shuffle(shuffled)
    states = []
    for order in (items, shuffled):
        conn = make_db()
        for field, value in order:
            db.set_override(conn, CFG, "gis:1", field, value, reason, T0)
        states.append((db.overrides_in_cell(conn, CELL), final(conn)))
    assert states[0] == states[1]


@given(override_pairs(), REASONS)
@settings(max_examples=30)
def test_p4_3_an_override_on_one_building_does_not_change_another(pair, reason):
    conn = make_db()
    before = {e.building_id: e for e in final(conn)}
    db.set_override(conn, CFG, "gis:1", pair[0], pair[1], reason, T0)
    after = {e.building_id: e for e in final(conn)}
    assert after["gis:2"] == before["gis:2"] and after["gis:3"] == before["gis:3"]


@given(judgements("gis:1"), override_sets(), REASONS)
@settings(max_examples=40)
def test_p4_6_doing_the_same_thing_twice_is_the_same_as_once(j, ov, reason):
    once, twice = make_db(), make_db()
    for conn, times in ((once, 1), (twice, 2)):
        for k in range(times):
            db.record_judgements(conn, CFG, [j], T0 if k == 0 else T1)
            for field, value in ov.items():
                db.set_override(conn, CFG, "gis:1", field, value, reason, T0 if k == 0 else T1)
    assert db.estimates_in_cell(once, CELL) == db.estimates_in_cell(twice, CELL)
    assert db.overrides_in_cell(once, CELL) == db.overrides_in_cell(twice, CELL)


def test_effective_buildings_are_those_with_status_ok_by_id():
    conn = make_db(3)
    db.replace_cell_rows(conn, CELL, {"buildings": [brow(1), brow(2, status="skipped"), brow(10), brow(3)]})
    assert [e.building_id for e in final(conn)] == ["gis:1", "gis:10", "gis:3"]


# --- P4-16: orphans and re-collection ----------------------------------------------------------------------------

def test_p4_16_re_collecting_a_cell_leaves_the_u4_tables_alone_and_the_orphans_are_reported():
    conn = make_db(3)
    db.record_judgements(conn, CFG, [judgement("gis:1"), judgement("gis:2")], T0)
    db.set_override(conn, CFG, "gis:3", "floors_above", 4, "seen", T0)
    before = (db.estimates_in_cell(conn, CELL), db.overrides_in_cell(conn, CELL))
    db.replace_cell_rows(conn, CELL, {"buildings": [brow(1)]})  # buildings 2 and 3 are gone
    assert (db.estimates_in_cell(conn, CELL), db.overrides_in_cell(conn, CELL)) == before
    assert db.orphans(conn) == [("overrides", "gis:3"), ("estimates", "gis:2")]


# --- views with the panorama heading -------------------------------------------------------------------------------

def test_views_come_with_the_front_heading_and_position_of_their_panorama():
    conn = make_db(1)
    db.upsert_building_views(conn, [vrow("gis:1", 4, status="no_photo", pano=None)])
    views = db.views_with_heading(conn, CELL)
    assert [v["rank"] for v in views] == [1, 2, 3, 4]
    assert (views[0]["heading_deg"], views[0]["pano_lat"], views[0]["yaw_deg"]) == (100.0, 37.5, 5.0)
    assert views[3]["heading_deg"] is None and views[3]["status"] == "no_photo"


# --- export and import (BR-8) ------------------------------------------------------------------------------------------

def fill(conn):
    db.record_judgements(conn, CFG, [judgement("gis:1"), judgement("gis:2", floors_seen=None, height_est_m=14.5, confidence="low")], T0)
    db.set_override(conn, CFG, "gis:1", "floors_above", 4, "seen with the user", T0)
    db.set_override(conn, CFG, "gis:3", "wall_color", "blue", "looks blue on the photo", T1)


def test_export_writes_one_sorted_file_per_cell_and_no_file_for_an_empty_cell(tmp_path):
    conn = make_db()
    assert db.export_cell(conn, CELL, tmp_path / f"{CELL}.json") is None and list(tmp_path.iterdir()) == []
    fill(conn)
    path = db.export_cell(conn, CELL, tmp_path / f"{CELL}.json")
    assert path == tmp_path / f"{CELL}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert [o["building_id"] for o in data["overrides"]] == ["gis:1", "gis:3"] and [e["building_id"] for e in data["estimates"]] == ["gis:1", "gis:2"]
    assert db.export_cell(conn, CELL, tmp_path / f"{CELL}.json") == path and path.read_text(encoding="utf-8") == J.export_payload(
        CELL, db.overrides_in_cell(conn, CELL), db.estimates_in_cell(conn, CELL))
    assert not list(tmp_path.glob("*.tmp"))


def test_an_old_file_is_rewritten_empty_when_everything_was_removed(tmp_path):
    conn = make_db()
    fill(conn)
    db.export_cell(conn, CELL, tmp_path / f"{CELL}.json")
    for b, f in (("gis:1", "floors_above"), ("gis:3", "wall_color")):
        db.unset_override(conn, b, f)
    with conn:
        conn.execute("DELETE FROM estimates")
    db.export_cell(conn, CELL, tmp_path / f"{CELL}.json")
    data = json.loads((tmp_path / f"{CELL}.json").read_text(encoding="utf-8"))
    assert (data["overrides"], data["estimates"]) == ([], [])


def test_export_refuses_a_cell_id_that_could_leave_the_folder(tmp_path):
    with pytest.raises(ValueError):
        db.export_cell(make_db(), "../evil", tmp_path)


def test_a_failed_file_swap_keeps_the_old_file_and_the_database_change(tmp_path, monkeypatch):
    conn = make_db()
    fill(conn)
    path = db.export_cell(conn, CELL, tmp_path / f"{CELL}.json")
    old = path.read_text(encoding="utf-8")
    db.set_override(conn, CFG, "gis:2", "roof_shape", "gable", "seen", T1)

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        db.export_cell(conn, CELL, tmp_path / f"{CELL}.json")
    assert path.read_text(encoding="utf-8") == old  # no half-written file
    assert any(o["field"] == "roof_shape" for o in db.overrides_in_cell(conn, CELL))  # the database change stays


def test_p4_7_an_export_loaded_into_a_fresh_database_gives_the_same_rows_and_the_same_file(tmp_path):
    conn = make_db()
    fill(conn)
    path = db.export_cell(conn, CELL, tmp_path / "a" / f"{CELL}.json")
    fresh = make_db()
    result = db.import_file(fresh, CFG, path)
    assert (result["cell_id"], result["overrides"], result["estimates"], result["orphans"]) == (CELL, 2, 2, [])
    assert db.estimates_in_cell(fresh, CELL) == db.estimates_in_cell(conn, CELL)
    assert db.overrides_in_cell(fresh, CELL) == db.overrides_in_cell(conn, CELL)
    assert [e for e in final(fresh)] == [e for e in final(conn)]  # the recovery drill gives the same final values
    again = db.export_cell(fresh, CELL, tmp_path / "b" / f"{CELL}.json")
    assert again.read_text(encoding="utf-8") == path.read_text(encoding="utf-8")


@given(js=st.lists(judgements("gis:1"), max_size=1), ov=override_sets(), reason=REASONS)
@settings(max_examples=30)
def test_p4_7_the_round_trip_holds_for_any_content(js, ov, reason, tmp_path_factory):
    conn = make_db()
    db.record_judgements(conn, CFG, js, T0)
    for field, value in ov.items():
        db.set_override(conn, CFG, "gis:1", field, value, reason, T1)
    folder = tmp_path_factory.mktemp("rt")
    path = db.export_cell(conn, CELL, folder / f"{CELL}.json")
    fresh = make_db()
    if path is None:
        assert not js and not ov
        return
    db.import_file(fresh, CFG, path)
    assert db.estimates_in_cell(fresh, CELL) == db.estimates_in_cell(conn, CELL)
    assert db.overrides_in_cell(fresh, CELL) == db.overrides_in_cell(conn, CELL)


def test_import_loads_rows_of_unknown_buildings_as_orphans_and_keeps_rows_the_file_does_not_mention(tmp_path):
    conn = make_db()
    db.set_override(conn, CFG, "gis:1", "floors_above", 4, "seen", T0)
    db.set_override(conn, CFG, "gis:2", "floors_above", 5, "seen", T0)
    path = db.export_cell(conn, CELL, tmp_path / f"{CELL}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["overrides"] = [o for o in data["overrides"] if o["building_id"] == "gis:1"] + [
        {"building_id": "gis:777", "field": "wall_color", "value": "pink", "reason": "kept", "set_at": T1}]
    data["overrides"][0]["value"] = 9
    path.write_text(json.dumps(data), encoding="utf-8")
    result = db.import_file(conn, CFG, path)
    assert result["orphans"] == [("overrides", "gis:777")]
    by = db.overrides_by_building(conn, CELL)
    assert by["gis:1"] == {"floors_above": 9} and by["gis:2"] == {"floors_above": 5} and by["gis:777"] == {"wall_color": "pink"}


def test_p4_9_a_bad_or_oversized_file_is_refused_and_the_database_stays(tmp_path):
    conn = make_db()
    db.set_override(conn, CFG, "gis:1", "floors_above", 4, "seen", T0)
    before = db.overrides_in_cell(conn, CELL)
    good = json.loads(J.export_payload(CELL, [{"building_id": "gis:1", "field": "floors_above", "value": 7, "reason": "r", "set_at": T1},
                                              {"building_id": "gis:2", "field": "floors_above", "value": 8, "reason": "r", "set_at": T1}], []))
    good["overrides"][1]["value"] = 0  # the second row is bad: nothing at all may be written
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(good), encoding="utf-8")
    with pytest.raises(ValueError):
        db.import_file(conn, CFG, bad)
    big = tmp_path / "big.json"
    big.write_text(" " * (J.MAX_EXPORT_BYTES + 1), encoding="utf-8")
    with pytest.raises(ValueError):
        db.import_file(conn, CFG, big)
    assert db.overrides_in_cell(conn, CELL) == before
