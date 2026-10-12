"""SQLite data layer for U1 (C7): schema, per-cell replacement, orphan report, backup, run log.

Only U1 tables are created here. `overrides` and `estimates` belong to U4; this module never
writes them and reads them only to report orphans.
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

JSON_COLUMNS = {"outline", "centroid", "tags", "osm_tags", "boundary", "geometry", "counts"}
BOOL_COLUMNS = {"valid"}

# table -> (columns, primary key columns, rows are deleted by cell_id before inserting)
TABLES: dict[str, tuple[tuple[str, ...], tuple[str, ...], bool]] = {
    "cells": (("cell_id", "res", "center_lat", "center_lon", "boundary"), ("cell_id",), False),
    "osm_buildings": (
        ("osm_id", "cell_id", "outline", "centroid", "tags", "height_m", "levels", "valid"),
        ("osm_id",), True),
    "gis_buildings": (
        ("gis_key", "cell_id", "outline", "centroid", "floors_above", "floors_below", "height_m",
         "name", "usability_code", "approval_date", "building_area", "valid"),
        ("gis_key",), True),
    "buildings": (
        ("building_id", "cell_id", "source", "outline", "centroid", "gis_key", "osm_id", "name",
         "osm_tags", "floors_above", "floors_below", "height_m", "usability_code", "approval_date",
         "building_area", "osm_height_m", "osm_levels", "status"),
        ("building_id",), True),
    "street_features": (
        ("feature_id", "cell_id", "kind", "highway_class", "geometry", "tags"),
        ("feature_id", "cell_id"), True),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS cells (
    cell_id TEXT PRIMARY KEY, res INTEGER NOT NULL, center_lat REAL, center_lon REAL, boundary TEXT);
CREATE TABLE IF NOT EXISTS osm_buildings (
    osm_id INTEGER PRIMARY KEY, cell_id TEXT NOT NULL, outline TEXT NOT NULL, centroid TEXT NOT NULL,
    tags TEXT, height_m REAL, levels INTEGER, valid INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gis_buildings (
    gis_key TEXT PRIMARY KEY, cell_id TEXT NOT NULL, outline TEXT NOT NULL, centroid TEXT NOT NULL,
    floors_above INTEGER, floors_below INTEGER, height_m REAL, name TEXT, usability_code TEXT,
    approval_date TEXT, building_area REAL, valid INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS buildings (
    building_id TEXT PRIMARY KEY, cell_id TEXT NOT NULL, source TEXT NOT NULL, outline TEXT NOT NULL,
    centroid TEXT NOT NULL, gis_key TEXT, osm_id INTEGER, name TEXT, osm_tags TEXT,
    floors_above INTEGER, floors_below INTEGER, height_m REAL, usability_code TEXT, approval_date TEXT,
    building_area REAL, osm_height_m REAL, osm_levels INTEGER, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS street_features (
    feature_id TEXT NOT NULL, cell_id TEXT NOT NULL, kind TEXT NOT NULL, highway_class TEXT,
    geometry TEXT NOT NULL, tags TEXT, PRIMARY KEY (feature_id, cell_id));
CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cell_id TEXT, unit TEXT NOT NULL, started_at TEXT NOT NULL,
    finished_at TEXT, status TEXT NOT NULL, source_stamp TEXT, counts TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS idx_osm_buildings_cell ON osm_buildings(cell_id);
CREATE INDEX IF NOT EXISTS idx_gis_buildings_cell ON gis_buildings(cell_id);
CREATE INDEX IF NOT EXISTS idx_buildings_cell ON buildings(cell_id);
CREATE INDEX IF NOT EXISTS idx_street_features_cell ON street_features(cell_id);
"""

OWNED_BY_U4 = ("overrides", "estimates")


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the database (foreign keys on) and create missing tables."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def to_rows(items: Iterable[Any]) -> list[dict[str, Any]]:
    """Dataclass instances (geo.OsmBuilding, geo.GisBuilding, geo.Building) -> row dicts."""
    return [dataclasses.asdict(i) for i in items]


def _encode(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in JSON_COLUMNS:
        return json.dumps(value, ensure_ascii=False)
    if column in BOOL_COLUMNS:
        return 1 if value else 0
    return value


def _decode(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in JSON_COLUMNS:
        return json.loads(value)
    if column in BOOL_COLUMNS:
        return bool(value)
    return value


def replace_cell_rows(conn: sqlite3.Connection, cell_id: str,
                      tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> int:
    """Replace what one cell owns in one transaction (BR-6.1) and return the rows written.

    For tables flagged as owned, rows with this cell_id are deleted first. Every given row is then
    written with INSERT OR REPLACE, so rows fetched through the buffer (owned by a neighbor cell)
    are overwritten by id. Any failure rolls back everything. overrides and estimates are untouched.
    """
    for name, rows in tables.items():
        if name not in TABLES:
            raise ValueError(f"unknown table: {name!r}")
        columns = TABLES[name][0]
        for row in rows:
            if set(row) != set(columns):
                raise ValueError(f"{name}: row columns {sorted(row)} do not match {sorted(columns)}")
    written = 0
    with conn:  # commits on success, rolls back on any exception
        for name, rows in tables.items():
            columns, _pk, owned = TABLES[name]
            if owned:
                conn.execute(f"DELETE FROM {name} WHERE cell_id = ?", (cell_id,))
            marks = ", ".join("?" for _ in columns)
            sql = f"INSERT OR REPLACE INTO {name} ({', '.join(columns)}) VALUES ({marks})"
            for row in rows:
                conn.execute(sql, [_encode(c, row[c]) for c in columns])
                written += 1
    return written


def rows_in_cells(conn: sqlite3.Connection, table: str, cell_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Decoded rows of an owned table whose cell_id is in cell_ids."""
    if table not in TABLES or not TABLES[table][2]:
        raise ValueError(f"not a cell-owned table: {table!r}")
    columns = TABLES[table][0]
    if not cell_ids:
        return []
    marks = ", ".join("?" for _ in cell_ids)
    cur = conn.execute(
        f"SELECT {', '.join(columns)} FROM {table} WHERE cell_id IN ({marks}) ORDER BY {', '.join(TABLES[table][1])}",
        list(cell_ids))
    return [{c: _decode(c, v) for c, v in zip(columns, r)} for r in cur.fetchall()]


def all_cell_ids(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT cell_id FROM cells ORDER BY cell_id")]


def orphans(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """(table, building_id) for overrides/estimates rows whose building no longer exists (BR-6.3).

    Tables that U4 has not created yet are skipped. Nothing is deleted.
    """
    found: list[tuple[str, str]] = []
    for table in OWNED_BY_U4:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
        if not exists:
            continue
        cur = conn.execute(
            f"SELECT DISTINCT building_id FROM {table} "
            "WHERE building_id NOT IN (SELECT building_id FROM buildings) ORDER BY building_id")
        found += [(table, r[0]) for r in cur.fetchall()]
    return found


def backup(conn: sqlite3.Connection, directory: str | Path, keep: int, stamp: str | None = None) -> Path:
    """Copy the database with sqlite's backup API, then keep only the newest `keep` copies (D-N6)."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest_path = d / f"map-{stamp}.db"
    dest = sqlite3.connect(dest_path)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    copies = sorted(d.glob("map-*.db"))
    for old in copies[:-keep] if keep > 0 else copies:
        old.unlink()
    return dest_path


def record_run(conn: sqlite3.Connection, *, cell_id: str | None, unit: str, started_at: str,
               finished_at: str | None, status: str, source_stamp: str | None = None,
               counts: Mapping[str, Any] | None = None, error: str | None = None) -> int:
    """Append one row to collection_runs and return its id."""
    with conn:
        cur = conn.execute(
            "INSERT INTO collection_runs (cell_id, unit, started_at, finished_at, status, source_stamp, counts, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cell_id, unit, started_at, finished_at, status, source_stamp,
             _encode("counts", dict(counts) if counts is not None else None), error))
    return int(cur.lastrowid)
