"""U4 estimate.py with real image files: pending (blind list, sheets, order), record, report, plan, compose, and the command line."""
from __future__ import annotations

import json
import sys

import pytest
from PIL import Image

import common
from conftest import one_region
import db
import estimate as E
import layout
import review
from test_u4_db import CELL, T0, brow, vrow

HEIGHT_MARK, FLOORS_MARK = 987.65, 77  # register numbers that must never show up before judging


@pytest.fixture
def world(tmp_path):
    """A cell with five buildings and crop files: 1 has no register data, 2 and 3 are normal, 4 is a school building, 5 has no photos."""
    cfg = {**common.DEFAULTS, "captures_dir": str(tmp_path / "captures"), **one_region(tmp_path, CELL),
           "db_path": str(tmp_path / "map.db"), "log_dir": str(tmp_path / "logs"), "review_batch_size": 2}
    conn = db.connect(":memory:")
    rows = [brow(1, floors=None, height=None), brow(2, floors=FLOORS_MARK, height=HEIGHT_MARK), brow(3, floors=3, height=10.2),
            brow(4, floors=4, height=13.6), brow(5, floors=2, height=7.0)]
    db.replace_cell_rows(conn, CELL, {"buildings": rows})
    db.upsert_captures(conn, [{"pano_id": "p1", "cell_id": CELL, "lat": 37.5, "lon": 126.78, "heading_deg": 100.0, "captured_at": None,
                               "is_latest": 1, "zoom": 1, "width": 6144, "height": 1024, "file_path": None, "status": "downloaded",
                               "downloaded_at": None}])
    views = []
    for bid in ("gis:1", "gis:2", "gis:3", "gis:4"):
        for rank in (1, 2) if bid != "gis:3" else (1, 2, 3):
            v = vrow(bid, rank)
            if bid == "gis:4":
                v["face_deg"] = 90.0 * rank
            views.append(v)
            path = tmp_path / "captures" / v["crop_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (1024, 768), (40 * rank, 90, 160)).save(path, "JPEG")
    views.append(vrow("gis:5", 1, status="no_photo", pano=None))
    db.upsert_building_views(conn, views)
    return conn, cfg, tmp_path


# --- pending (BR-1) ---------------------------------------------------------------------------------------

def test_pending_lists_buildings_blind_in_the_judging_order_and_writes_sheet_images(world):
    conn, cfg, tmp = world
    items, left = E.pending_jobs(conn, cfg, CELL, 10)
    assert [i["building_id"] for i in items] == ["gis:1", "gis:4", "gis:2", "gis:3"]  # no register data, school, the rest
    assert left == {"remaining": 0, "no_photo": 1, "judged": 0}
    text = json.dumps(items)
    assert str(HEIGHT_MARK) not in text and str(FLOORS_MARK) not in text and "floors" not in text and "height" not in text
    assert E.write_sheets(conn, cfg, CELL, items) == []
    for item in items:
        with Image.open(tmp / "captures" / item["sheet"]) as sheet:
            assert sheet.width == 1024 and sheet.height == 384 * ((len(item["views"]) + 1) // 2)
    assert items[0]["sheet"] == f"{CELL}/sheets/gis_1.jpg"


def test_pending_limit_redo_and_judged_buildings(world):
    conn, cfg, _ = world
    first, left = E.pending_jobs(conn, cfg, CELL, 2)
    assert [i["building_id"] for i in first] == ["gis:1", "gis:4"] and left["remaining"] == 2
    db.record_judgements(conn, cfg, [{"building_id": "gis:1", "floors_seen": 2, "confidence": "high", "height_est_m": None,
                                      "wall_color": None, "roof_shape": None, "views_used": [1], "note": None}], T0)
    again, left = E.pending_jobs(conn, cfg, CELL, 10)
    assert [i["building_id"] for i in again] == ["gis:4", "gis:2", "gis:3"] and left["judged"] == 1
    redo, _ = E.pending_jobs(conn, cfg, CELL, 10, ["gis:1"])
    assert redo[0]["building_id"] == "gis:1"


def test_a_missing_crop_file_leaves_its_tile_out_and_no_readable_crop_means_no_sheet(world):
    conn, cfg, tmp = world
    for rank in (1, 2):
        (tmp / "captures" / vrow("gis:1", rank)["crop_path"]).unlink()
    (tmp / "captures" / vrow("gis:2", 2)["crop_path"]).unlink()
    items, _ = E.pending_jobs(conn, cfg, CELL, 10)
    warnings = E.write_sheets(conn, cfg, CELL, items)
    assert any("gis:1" in w and "no sheet" in w for w in warnings) and any("gis:2" in w and "missing" in w for w in warnings)
    assert not (tmp / "captures" / f"{CELL}/sheets/gis_1.jpg").exists()
    with Image.open(tmp / "captures" / f"{CELL}/sheets/gis_2.jpg") as sheet:
        assert sheet.height == 384  # one tile left


def test_an_image_with_too_many_pixels_is_refused_before_it_is_unpacked(tmp_path, monkeypatch):
    big = tmp_path / "big.png"
    Image.new("RGB", (20, 20)).save(big)
    monkeypatch.setattr(E, "MAX_PIXELS", 100)
    with pytest.raises(ValueError, match="pixels"):
        E.open_image(big)
    monkeypatch.setattr(E, "MAX_PIXELS", 400)
    with E.open_image(big) as im:
        assert im.size == (20, 20)


def test_a_crop_path_that_leaves_the_captures_folder_is_refused(world):
    conn, cfg, _ = world
    with conn:
        conn.execute("UPDATE building_views SET crop_path = '../../etc/passwd' WHERE building_id = 'gis:2' AND rank = 1")
    items, _ = E.pending_jobs(conn, cfg, CELL, 10)
    with pytest.raises(ValueError):
        E.write_sheets(conn, cfg, CELL, items)


def test_file_names_of_building_ids_never_hold_separators():
    assert E.safe_name("gis:1") == "gis_1" and E.safe_name("osm:12.3-4#5") == "osm_12.3-4#5"
    for bad in ("a/b", "..\\x", "", "x" * 101, "a b"):
        with pytest.raises(ValueError):
            E.safe_name(bad)


# --- record (BR-2) ------------------------------------------------------------------------------------------------

def good(bid="gis:2", **kw):
    return {"building_id": bid, "floors_seen": 3, "confidence": "high", "height_est_m": None, "wall_color": "cream", "roof_shape": "flat",
            "views_used": [1, 2], "note": None, **kw}


def test_record_stores_and_refreshes_the_export_file_and_one_bad_judgement_stops_all(world):
    conn, cfg, tmp = world
    assert E.record(conn, cfg, [good("gis:2"), good("gis:3", views_used=[1])]) == 2
    data = json.loads((tmp / "regions" / "r" / "cells" / CELL / "overrides.json").read_text(encoding="utf-8"))
    assert [e["building_id"] for e in data["estimates"]] == ["gis:2", "gis:3"]
    with pytest.raises(ValueError):
        E.record(conn, cfg, [good("gis:1"), good("gis:3", floors_seen=0)])
    assert [e["building_id"] for e in db.estimates_in_cell(conn, CELL)] == ["gis:2", "gis:3"]  # gis:1 was not stored either


def test_read_judgements_takes_a_list_from_a_file(tmp_path):
    f = tmp_path / "j.json"
    f.write_text(json.dumps([good()]), encoding="utf-8")
    assert E.read_judgements(str(f)) == [good()]
    for text in ("{}", "not json"):
        f.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            E.read_judgements(str(f))


# --- report ---------------------------------------------------------------------------------------------------------

def test_report_counts_statuses_agreement_and_lists_what_needs_a_look(world):
    conn, cfg, _ = world
    E.record(conn, cfg, [good("gis:2", floors_seen=FLOORS_MARK),                       # agrees with the register (verified)
                         good("gis:3", floors_seen=4, confidence="high"),               # register 3, photo 4 -> changed
                         good("gis:4", floors_seen=5, confidence="low"),               # register 4, photo 5, low -> conflict
                         good("gis:1", floors_seen=2, confidence="medium")])           # no register -> filled
    text = "\n".join(E.report_lines(conn, cfg, CELL))
    assert "5 buildings, 4 judged, 1 not judged yet, 1 without photos" in text
    assert "changed 1" in text and "conflict 1" in text and "filled 1" in text and "verified 1" in text
    assert "agrees with the register on 1 of 3 buildings" in text and "high 1/2" in text and "low 0/1" in text
    assert "gis:3  changed" in text and "gis:4  conflict" in text and "gis:1  filled" in text
    assert "gis:5" not in text.split("review list:")[1]  # not judged and nothing else to say: only `unjudged`


def test_report_leaves_blind_broken_buildings_out_of_the_agreement(world):
    conn, cfg, _ = world
    E.record(conn, cfg, [good("gis:2", floors_seen=FLOORS_MARK)])
    text = "\n".join(E.report_lines(conn, {**cfg, "blind_broken": ["gis:2"]}, CELL))
    assert "no building has both yet" in text


# --- plan and compose (BR-7) ------------------------------------------------------------------------------------------------

def judged_world(world):
    conn, cfg, tmp = world
    E.record(conn, cfg, [good("gis:2", floors_seen=FLOORS_MARK), good("gis:3", floors_seen=4), good("gis:4", floors_seen=4),
                         good("gis:1", floors_seen=2, confidence="medium")])
    return conn, cfg, tmp


def test_plan_makes_batches_pairs_and_camera_values(world):
    conn, cfg, tmp = judged_world(world)
    plan = E.plan_cell(conn, cfg, CELL)
    pairs = {p["key"]: p for b in plan["batches"] for p in b["pairs"]}
    assert sorted(pairs) == ["gis:1__1", "gis:2__1", "gis:3__1", "gis:4__1", "gis:4__2"]  # school building: a pair for every face view
    assert plan["pairs"] == 5 and plan["studio_fov_v_deg"] == 83.58
    assert [[p["building_id"] for p in b["pairs"]] for b in plan["batches"]] == [["gis:1", "gis:2"], ["gis:3", "gis:4", "gis:4"]]
    # flagged first (gis:1 filled, gis:2 register height 12.8 m a floor, gis:3 changed), then the school building; gis:5 has no photo
    p = pairs["gis:3__1"]
    cam = review.camera_for_view(layout.Frame.from_cfg(cfg), 37.5, 126.78, 100.0, 5.0, 10.0, cfg["camera_height_m"])
    assert p["camera"] == cam and p["crop_fov_h_deg"] == 90.0
    assert p["label"]["floors"] == 4 and p["label"]["floors_basis"] == "photo_count" and "changed" in p["label"]["flags"]
    assert E.plan_cell(conn, cfg, CELL) == plan  # same input, same plan
    assert json.dumps(plan, sort_keys=True) == json.dumps(E.plan_cell(conn, cfg, CELL), sort_keys=True)


def write_plan(cfg, plan, tmp, monkeypatch):
    monkeypatch.setattr(E, "BUILD_DIR", str(tmp / "build"))
    folder = tmp / "build" / CELL
    folder.mkdir(parents=True)
    (folder / "review.json").write_text(json.dumps(plan), encoding="utf-8")


def test_compose_puts_the_studio_capture_next_to_the_crop(world, monkeypatch):
    conn, cfg, tmp = judged_world(world)
    plan = E.plan_cell(conn, cfg, CELL)
    write_plan(cfg, plan, tmp, monkeypatch)
    shot = tmp / "shot.jpg"
    Image.new("RGB", (1437, 882), (200, 30, 30)).save(shot)
    mapping = tmp / "captures.json"
    mapping.write_text(json.dumps({"gis:3__1": str(shot), "gis:99__1": str(shot)}), encoding="utf-8")
    made, warnings = E.compose(cfg, CELL, str(mapping))
    assert made == [f"{CELL}/review/gis_3__1.jpg"] and len(warnings) == 1 and "not a pair" in warnings[0]
    with Image.open(tmp / "captures" / made[0]) as pair:
        assert pair.size == (1280, 480 + 56)
        assert pair.getpixel((100, 300))[0] > 150 and pair.getpixel((1000, 300)) != pair.getpixel((100, 300))  # left Studio, right crop


def test_compose_skips_captures_that_do_not_fit(world, monkeypatch):
    conn, cfg, tmp = judged_world(world)
    write_plan(cfg, E.plan_cell(conn, cfg, CELL), tmp, monkeypatch)
    narrow, text = tmp / "narrow.png", tmp / "text.png"
    Image.new("RGB", (800, 800)).save(narrow)
    text.write_text("not an image", encoding="utf-8")
    mapping = tmp / "captures.json"
    mapping.write_text(json.dumps({"gis:2__1": str(narrow), "gis:3__1": str(text), "gis:4__1": str(tmp / "missing.png")}), encoding="utf-8")
    made, warnings = E.compose(cfg, CELL, str(mapping))
    assert made == [] and len(warnings) == 3
    assert any("narrower than 4:3" in w for w in warnings)


def test_compose_refuses_a_plan_that_points_outside_the_captures_folder(world, monkeypatch):
    conn, cfg, tmp = judged_world(world)
    plan = E.plan_cell(conn, cfg, CELL)
    plan["batches"][0]["pairs"][0]["crop"] = "../../outside.jpg"
    key = plan["batches"][0]["pairs"][0]["key"]
    write_plan(cfg, plan, tmp, monkeypatch)
    shot = tmp / "shot.jpg"
    Image.new("RGB", (1437, 882)).save(shot)
    mapping = tmp / "captures.json"
    mapping.write_text(json.dumps({key: str(shot)}), encoding="utf-8")
    made, warnings = E.compose(cfg, CELL, str(mapping))
    assert made == [] and "leaves" in warnings[0]


# --- the command line ---------------------------------------------------------------------------------------------------------

def run_main(monkeypatch, cfg, *argv):
    monkeypatch.setattr(sys, "argv", ["estimate.py", *argv])
    return E.main(cfg)


def test_command_line_pending_record_report_plan_end_to_end(world, monkeypatch, capsys, tmp_path):
    conn, cfg, tmp = world
    disk = db.connect(cfg["db_path"])  # the same data on disk for main()
    conn.backup(disk)
    disk.close()
    assert run_main(monkeypatch, cfg, "pending", "--cells", CELL, "--limit", "2") == 0
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith("{")]
    assert [l["building_id"] for l in lines] == ["gis:1", "gis:4"] and (tmp / "captures" / lines[0]["sheet"]).is_file()
    f = tmp / "j.json"
    f.write_text(json.dumps([good("gis:2"), good("gis:3")]), encoding="utf-8")
    assert run_main(monkeypatch, cfg, "record", "--file", str(f)) == 0
    assert "recorded 2 judgements" in capsys.readouterr().out
    assert run_main(monkeypatch, cfg, "report", "--cells", CELL) == 0
    assert "2 judged" in capsys.readouterr().out
    monkeypatch.setattr(E, "BUILD_DIR", str(tmp / "build"))
    assert run_main(monkeypatch, cfg, "plan", "--cells", CELL) == 0
    out = capsys.readouterr().out
    assert "83.58" in out and (tmp / "build" / CELL / "review.json").is_file()
    runs = db.connect(cfg["db_path"]).execute("SELECT unit, status FROM collection_runs ORDER BY id").fetchall()
    assert runs == [("C4", "ok")] * 4


def test_command_line_refuses_bad_input_with_a_message_and_exit_code_one(world, monkeypatch, capsys):
    conn, cfg, tmp = world
    disk = db.connect(cfg["db_path"])
    conn.backup(disk)
    disk.close()
    f = tmp / "j.json"
    f.write_text(json.dumps([good("gis:2", floors_seen=0)]), encoding="utf-8")
    assert run_main(monkeypatch, cfg, "record", "--file", str(f)) == 1
    assert "refused" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        run_main(monkeypatch, cfg, "pending", "--cells", "not-a-cell")
    with pytest.raises(SystemExit):
        run_main(monkeypatch, cfg, "pending", "--cells", CELL, "--limit", "0")
    with pytest.raises(SystemExit):
        run_main(monkeypatch, cfg)
