"""U4 overrides.py command line: set, unset, list, export, import (the recovery drill), refused calls."""
from __future__ import annotations

import json
import sys

import pytest

import common
import db
import overrides as O
from test_u4_db import CELL, brow


@pytest.fixture
def world(tmp_path):
    cfg = {**common.DEFAULTS, "db_path": str(tmp_path / "map.db"), "overrides_dir": str(tmp_path / "overrides"), "log_dir": str(tmp_path / "logs")}
    conn = db.connect(cfg["db_path"])
    db.replace_cell_rows(conn, CELL, {"buildings": [brow(1), brow(2, floors=4, height=13.6)]})
    conn.close()
    return cfg, tmp_path


def run_main(monkeypatch, cfg, *argv):
    monkeypatch.setattr(sys, "argv", ["overrides.py", *argv])
    return O.main(cfg)


def test_parse_value_reads_numbers_and_words():
    assert [O.parse_value(t) for t in ("4", "10.5", "cream", '"cream"', "[1]")] == [4, 10.5, "cream", "cream", [1]]


def test_set_unset_list_and_export_through_the_command_line(world, monkeypatch, capsys):
    cfg, tmp = world
    assert run_main(monkeypatch, cfg, "set", "--building", "gis:1", "--field", "floors_above", "--value", "5", "--reason", "user and Claude counted 5") == 0
    assert "set: gis:1 floors_above" in capsys.readouterr().out
    file = tmp / "overrides" / f"{CELL}.json"
    assert json.loads(file.read_text(encoding="utf-8"))["overrides"][0]["value"] == 5
    assert run_main(monkeypatch, cfg, "set", "--building", "gis:1", "--field", "floors_above", "--value", "5", "--reason", "user and Claude counted 5") == 0
    assert "unchanged" in capsys.readouterr().out
    assert run_main(monkeypatch, cfg, "list", "--cells", CELL) == 0
    out = capsys.readouterr().out
    assert "1 overrides" in out and "gis:1 floors_above = 5" in out and "user and Claude counted 5" in out
    assert run_main(monkeypatch, cfg, "unset", "--building", "gis:1", "--field", "floors_above") == 0
    assert "removed" in capsys.readouterr().out
    assert json.loads(file.read_text(encoding="utf-8"))["overrides"] == []  # the file is rewritten empty, not left stale
    assert run_main(monkeypatch, cfg, "unset", "--building", "gis:1", "--field", "floors_above") == 0
    assert "nothing to remove" in capsys.readouterr().out
    file.unlink()
    assert run_main(monkeypatch, cfg, "export", "--cells", CELL) == 0
    assert "nothing to export" in capsys.readouterr().out and not file.exists()
    runs = db.connect(cfg["db_path"]).execute("SELECT unit FROM collection_runs").fetchall()
    assert set(runs) == {("C5",)}


def test_the_recovery_drill_a_new_database_plus_the_export_gives_the_same_final_values(world, monkeypatch, capsys):
    cfg, tmp = world
    for args in (("gis:1", "floors_above", "5"), ("gis:1", "wall_color", "cream"), ("gis:2", "height_m", "14.5")):
        assert run_main(monkeypatch, cfg, "set", "--building", args[0], "--field", args[1], "--value", args[2], "--reason", "checked on Studio") == 0
    capsys.readouterr()
    before = db.effective_buildings(db.connect(cfg["db_path"]), cfg, CELL)
    export = tmp / "overrides" / f"{CELL}.json"
    # the database is lost: a new one gets the buildings again (S1) and the file is imported
    fresh_cfg = {**cfg, "db_path": str(tmp / "new.db")}
    fresh = db.connect(fresh_cfg["db_path"])
    db.replace_cell_rows(fresh, CELL, {"buildings": [brow(1), brow(2, floors=4, height=13.6)]})
    fresh.close()
    assert run_main(monkeypatch, fresh_cfg, "import", "--file", str(export)) == 0
    assert "imported 3 overrides and 0 judgements" in capsys.readouterr().out
    assert db.effective_buildings(db.connect(fresh_cfg["db_path"]), fresh_cfg, CELL) == before


def test_import_reports_orphans(world, monkeypatch, capsys):
    cfg, tmp = world
    file = tmp / "in.json"
    file.write_text(json.dumps({"version": 1, "cell_id": CELL, "estimates": [], "overrides": [
        {"building_id": "gis:404", "field": "wall_color", "value": "pink", "reason": "kept", "set_at": "2026-10-13T01:00:00+00:00"}]}),
        encoding="utf-8")
    assert run_main(monkeypatch, cfg, "import", "--file", str(file)) == 0
    assert "orphan: overrides gis:404" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [
    ("set", "--building", "gis:1", "--field", "floors_above", "--value", "0", "--reason", "x"),
    ("set", "--building", "gis:1", "--field", "floors_above", "--value", "3", "--reason", " "),
    ("set", "--building", "gis:404", "--field", "floors_above", "--value", "3", "--reason", "x"),
    ("set", "--building", "gis:1", "--field", "wall_color", "--value", "neon", "--reason", "x"),
])
def test_a_refused_call_says_why_exits_with_one_and_changes_nothing(world, monkeypatch, capsys, argv):
    cfg, tmp = world
    assert run_main(monkeypatch, cfg, *argv) == 1
    assert "refused" in capsys.readouterr().err
    assert db.overrides_in_cell(db.connect(cfg["db_path"]), CELL) == [] and not (tmp / "overrides").exists()


def test_bad_arguments_are_usage_errors(world, monkeypatch):
    cfg, _ = world
    for argv in (("set", "--building", "gis:1", "--field", "color", "--value", "1", "--reason", "x"), ("list", "--cells", "nope"), ()):
        with pytest.raises(SystemExit):
            run_main(monkeypatch, cfg, *argv)


def test_a_bad_import_file_is_refused_whole(world, monkeypatch, capsys):
    cfg, tmp = world
    bad = tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert run_main(monkeypatch, cfg, "import", "--file", str(bad)) == 1
    assert "refused" in capsys.readouterr().err
