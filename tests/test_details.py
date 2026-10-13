"""U5 details.py command line: pending, record, list, export, import, refused calls."""
from __future__ import annotations

import json
import sys

import pytest

import common
import db
import details as Dt
from test_u4_db import CELL, brow


@pytest.fixture
def world(tmp_path):
    cfg = {**common.DEFAULTS, "db_path": str(tmp_path / "map.db"), "details_dir": str(tmp_path / "details"), "log_dir": str(tmp_path / "logs"),
           "captures_dir": "captures"}
    conn = db.connect(cfg["db_path"])
    db.replace_cell_rows(conn, CELL, {"buildings": [brow(1), brow(2, floors=4, height=13.6)]})
    conn.close()
    return cfg, tmp_path


def run_main(monkeypatch, cfg, *argv):
    monkeypatch.setattr(sys, "argv", ["details.py", *argv])
    return Dt.main(cfg)


def test_pending_record_list_export_and_import_through_the_command_line(world, monkeypatch, capsys):
    cfg, tmp = world
    assert run_main(monkeypatch, cfg, "pending", "--cells", CELL) == 0
    out = capsys.readouterr().out
    assert "gis:1" in out and "sheets/gis_1.jpg" in out and "2 listed, 0 more" in out
    rows = [{"building_id": "gis:1", "finish": "brick", "ground_use": "shop", "stair": None, "bay": 1, "balcony": 0, "roof_color": None,
             "rooftop": None, "note": "dark brick shop house"}]
    (tmp / "d.json").write_text(json.dumps(rows), encoding="utf-8")
    assert run_main(monkeypatch, cfg, "record", "--file", str(tmp / "d.json")) == 0
    assert "recorded 1" in capsys.readouterr().out
    file = tmp / "details" / f"{CELL}.json"
    assert json.loads(file.read_text(encoding="utf-8"))["details"][0]["finish"] == "brick"
    assert run_main(monkeypatch, cfg, "pending", "--cells", CELL) == 0
    out = capsys.readouterr().out
    assert "gis:2" in out and "gis:1" not in out
    assert run_main(monkeypatch, cfg, "pending", "--cells", CELL, "--redo", "gis:1") == 0
    assert "gis:1" in capsys.readouterr().out
    assert run_main(monkeypatch, cfg, "list", "--cells", CELL) == 0
    out = capsys.readouterr().out
    assert "1 details" in out and "gis:1 finish=brick ground_use=shop bay=1 balcony=0" in out
    file.unlink()
    assert run_main(monkeypatch, cfg, "export", "--cells", CELL) == 0
    assert file.exists()
    fresh = {**cfg, "db_path": str(tmp / "fresh.db")}
    conn = db.connect(fresh["db_path"])
    db.replace_cell_rows(conn, CELL, {"buildings": [brow(1)]})
    conn.close()
    assert run_main(monkeypatch, fresh, "import", "--file", str(file)) == 0
    assert "imported 1 details" in capsys.readouterr().out
    assert db.details_in_cell(db.connect(fresh["db_path"]), CELL)[0]["ground_use"] == "shop"
    runs = db.connect(cfg["db_path"]).execute("SELECT unit FROM collection_runs").fetchall()
    assert set(runs) == {("C7",)}


def test_a_refused_record_prints_why_and_changes_nothing(world, monkeypatch, capsys):
    cfg, tmp = world
    (tmp / "bad.json").write_text(json.dumps([{"building_id": "gis:1", "finish": "brick"}, {"building_id": "gis:1", "finish": "wood"}]), encoding="utf-8")
    assert run_main(monkeypatch, cfg, "record", "--file", str(tmp / "bad.json")) == 1
    assert "refused" in capsys.readouterr().err
    assert db.details_in_cell(db.connect(cfg["db_path"]), CELL) == []
    (tmp / "big.json").write_text("[" + " " * Dt.MAX_RECORD_BYTES + "]", encoding="utf-8")
    assert run_main(monkeypatch, cfg, "record", "--file", str(tmp / "big.json")) == 1


def test_the_command_line_checks_its_arguments():
    for argv in (["pending", "--cells", "nothex"], [], ["pending", "--cells", CELL, "--limit", "0"], ["pending", "--cells", CELL, "--redo", 'a"b']):
        with pytest.raises(SystemExit):
            Dt.parse_args(argv)
    assert Dt.parse_args(["--selftest"]).selftest and Dt.parse_args(["list", "--cells", CELL]).cells == [CELL]
    assert Dt.safe_name("gis:11081057") == "gis_11081057"
    with pytest.raises(ValueError):
        Dt.safe_name("a/b")
