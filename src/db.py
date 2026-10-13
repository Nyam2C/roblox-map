"""SQLite data layer (C7) for U1, U3 and U4: schema, per-cell replacement, orphan report, backup, run log.

U1 tables, U3's `captures` and `building_views`, and U4's `estimates` (photo judgements) and `overrides` (corrections).
Only the U4 functions below write `estimates` and `overrides`; `replace_cell_rows` never touches them (U1 BR-6.2).
"""
from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import judgement

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
CREATE TABLE IF NOT EXISTS captures (
    pano_id TEXT PRIMARY KEY, cell_id TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, heading_deg REAL,
    captured_at TEXT, is_latest INTEGER, zoom INTEGER, width INTEGER, height INTEGER, file_path TEXT,
    status TEXT NOT NULL, downloaded_at TEXT);
CREATE TABLE IF NOT EXISTS building_views (
    building_id TEXT NOT NULL, rank INTEGER NOT NULL, pano_id TEXT, distance_m REAL, bearing_deg REAL,
    yaw_deg REAL, fov_deg REAL, pitch_deg REAL, crop_path TEXT, status TEXT NOT NULL,
    face_deg REAL, target_lat REAL, target_lon REAL,
    PRIMARY KEY (building_id, rank));
CREATE TABLE IF NOT EXISTS estimates (
    building_id TEXT PRIMARY KEY, cell_id TEXT NOT NULL, floors_seen INTEGER, confidence TEXT, height_est_m REAL,
    wall_color TEXT, roof_shape TEXT, views_used TEXT NOT NULL, note TEXT, judged_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS overrides (
    building_id TEXT NOT NULL, field TEXT NOT NULL, value TEXT NOT NULL, cell_id TEXT NOT NULL, reason TEXT NOT NULL,
    set_at TEXT NOT NULL, PRIMARY KEY (building_id, field));
CREATE INDEX IF NOT EXISTS idx_estimates_cell ON estimates(cell_id);
CREATE INDEX IF NOT EXISTS idx_overrides_cell ON overrides(cell_id);
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
    have = {r[1] for r in conn.execute("PRAGMA table_info(building_views)")}
    for column in ("face_deg", "target_lat", "target_lon"):  # added for the school faces (BR-2.7); older databases lack them
        if column not in have:
            conn.execute(f"ALTER TABLE building_views ADD COLUMN {column} REAL")
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


# --- U3: street-view captures ---------------------------------------------------------------------

CAPTURE_COLUMNS = ("pano_id", "cell_id", "lat", "lon", "heading_deg", "captured_at", "is_latest", "zoom",
                   "width", "height", "file_path", "status", "downloaded_at")
VIEW_COLUMNS = ("building_id", "rank", "pano_id", "distance_m", "bearing_deg", "yaw_deg", "fov_deg",
                "pitch_deg", "crop_path", "status", "face_deg", "target_lat", "target_lon")


def _upsert(conn: sqlite3.Connection, table: str, columns: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> int:
    rows = list(rows)
    for row in rows:
        if set(row) != set(columns):
            raise ValueError(f"{table}: row columns {sorted(row)} do not match {sorted(columns)}")
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    with conn:
        for row in rows:
            conn.execute(sql, [row[c] for c in columns])
    return len(rows)


def upsert_captures(conn: sqlite3.Connection, rows: Iterable[Mapping[str, Any]]) -> int:
    return _upsert(conn, "captures", CAPTURE_COLUMNS, rows)


def upsert_building_views(conn: sqlite3.Connection, rows: Iterable[Mapping[str, Any]]) -> int:
    return _upsert(conn, "building_views", VIEW_COLUMNS, rows)


def all_captures(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(f"SELECT {', '.join(CAPTURE_COLUMNS)} FROM captures ORDER BY pano_id")
    return [dict(zip(CAPTURE_COLUMNS, r)) for r in cur.fetchall()]


_CELL_VIEWS = "building_id IN (SELECT building_id FROM buildings WHERE cell_id = ?)"


def views_for_cell(conn: sqlite3.Connection, cell_id: str) -> list[dict[str, Any]]:
    """building_views rows of the buildings that belong to this cell, ordered by building and rank."""
    cur = conn.execute(
        f"SELECT {', '.join(VIEW_COLUMNS)} FROM building_views WHERE {_CELL_VIEWS} ORDER BY building_id, rank",
        (cell_id,))
    return [dict(zip(VIEW_COLUMNS, r)) for r in cur.fetchall()]


def delete_views_for_cell(conn: sqlite3.Connection, cell_id: str) -> list[str]:
    """--replan (BR-6.2): delete this cell's building_views and return their crop paths. Nothing else is touched."""
    paths = [v["crop_path"] for v in views_for_cell(conn, cell_id) if v["crop_path"]]
    with conn:
        conn.execute(f"DELETE FROM building_views WHERE {_CELL_VIEWS}", (cell_id,))
    return paths


def delete_views_for_buildings(conn: sqlite3.Connection, building_ids: Sequence[str]) -> list[str]:
    """--replan-school: delete the views of these buildings only and return their crop paths."""
    ids = list(building_ids)
    if not ids:
        return []
    marks = ", ".join("?" for _ in ids)
    paths = [r[0] for r in conn.execute(
        f"SELECT crop_path FROM building_views WHERE crop_path IS NOT NULL AND building_id IN ({marks})", ids)]
    with conn:
        conn.execute(f"DELETE FROM building_views WHERE building_id IN ({marks})", ids)
    return paths


def orphan_views(conn: sqlite3.Connection) -> list[str]:
    """building_ids that have building_views but no longer exist in buildings (BR-6.3). Nothing is deleted."""
    cur = conn.execute("SELECT DISTINCT building_id FROM building_views "
                       "WHERE building_id NOT IN (SELECT building_id FROM buildings) ORDER BY building_id")
    return [r[0] for r in cur.fetchall()]


# --- U4: photo judgements and corrections ---------------------------------------------------------------

ESTIMATE_DATA = judgement.JUDGEMENT_KEYS  # the columns that make a judgement what it is (no time)


def _estimate_dict(row: Sequence[Any]) -> dict[str, Any]:
    d = dict(zip(judgement.ESTIMATE_KEYS, row))
    d["views_used"] = json.loads(d["views_used"])
    return d


def _estimate_select(where: str) -> str:
    return f"SELECT {', '.join(judgement.ESTIMATE_KEYS)} FROM estimates {where} ORDER BY building_id"


def building_cell(conn: sqlite3.Connection, building_id: str) -> str | None:
    row = conn.execute("SELECT cell_id FROM buildings WHERE building_id = ?", (building_id,)).fetchone()
    return row[0] if row else None


def record_judgements(conn: sqlite3.Connection, cfg: Mapping[str, Any], judgements: Sequence[Mapping[str, Any]], now: str) -> int:
    """Store photo judgements, all or none (BR-2.2). A judgement that equals the stored one changes nothing, not even its time."""
    rows: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for j in judgements:
        bid = j.get("building_id") if isinstance(j, Mapping) else None
        found = conn.execute("SELECT cell_id, status FROM buildings WHERE building_id = ?", (bid,)).fetchone() \
            if judgement.is_building_id(bid) else None
        if found is None or found[1] != "ok":
            raise ValueError(f"{str(bid)[:40]}: not a building with status ok in this database")
        if bid in seen:
            raise ValueError(f"{bid}: appears twice in one call")
        seen.add(bid)
        ranks = {r[0] for r in conn.execute(
            "SELECT rank FROM building_views WHERE building_id = ? AND status = 'cropped'", (bid,))}
        rows.append((found[0], judgement.validate_judgement(j, cfg, ranks)))
    with conn:
        for cell_id, row in rows:
            old = conn.execute(_estimate_select("WHERE building_id = ?"), (row["building_id"],)).fetchone()
            if old is not None:
                old_d = _estimate_dict(old)
                if {k: old_d[k] for k in ESTIMATE_DATA} == row:
                    continue
            conn.execute(
                "INSERT OR REPLACE INTO estimates (building_id, cell_id, floors_seen, confidence, height_est_m, wall_color, "
                "roof_shape, views_used, note, judged_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row["building_id"], cell_id, row["floors_seen"], row["confidence"], row["height_est_m"], row["wall_color"],
                 row["roof_shape"], json.dumps(row["views_used"]), row["note"], now))
    return len(rows)


def set_override(conn: sqlite3.Connection, cfg: Mapping[str, Any], building_id: str, field: str, value: Any, reason: Any,
                 now: str) -> bool:
    """Store one correction (BR-6.3). True when something changed; the same value and reason again changes nothing."""
    value, reason = judgement.validate_override(field, value, reason, cfg)
    cell_id = building_cell(conn, building_id) if judgement.is_building_id(building_id) else None
    if cell_id is None:
        raise ValueError(f"{str(building_id)[:40]}: not a building in this database")
    encoded = json.dumps(value)
    old = conn.execute("SELECT value, reason FROM overrides WHERE building_id = ? AND field = ?", (building_id, field)).fetchone()
    if old == (encoded, reason):
        return False
    with conn:
        conn.execute("INSERT OR REPLACE INTO overrides (building_id, field, value, cell_id, reason, set_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (building_id, field, encoded, cell_id, reason, now))
    return True


def unset_override(conn: sqlite3.Connection, building_id: str, field: str) -> str | None:
    """Remove one correction (BR-6.4). Returns the cell it belonged to, or None when there was none."""
    row = conn.execute("SELECT cell_id FROM overrides WHERE building_id = ? AND field = ?", (building_id, field)).fetchone()
    if row is None:
        return None
    with conn:
        conn.execute("DELETE FROM overrides WHERE building_id = ? AND field = ?", (building_id, field))
    return row[0]


def estimates_in_cell(conn: sqlite3.Connection, cell_id: str) -> list[dict[str, Any]]:
    return [_estimate_dict(r) for r in conn.execute(_estimate_select("WHERE cell_id = ?"), (cell_id,))]


def overrides_in_cell(conn: sqlite3.Connection, cell_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(f"SELECT {', '.join(judgement.OVERRIDE_KEYS)} FROM overrides WHERE cell_id = ? ORDER BY building_id, field", (cell_id,))
    out = []
    for r in cur.fetchall():
        d = dict(zip(judgement.OVERRIDE_KEYS, r))
        d["value"] = json.loads(d["value"])
        out.append(d)
    return out


def overrides_by_building(conn: sqlite3.Connection, cell_id: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for o in overrides_in_cell(conn, cell_id):
        out.setdefault(o["building_id"], {})[o["field"]] = o["value"]
    return out


def views_with_heading(conn: sqlite3.Connection, cell_id: str) -> list[dict[str, Any]]:
    """building_views of this cell's buildings with the panorama they use (position and front heading), by building and rank."""
    cols = ("building_id", "rank", "pano_id", "yaw_deg", "fov_deg", "pitch_deg", "crop_path", "status", "face_deg")
    cur = conn.execute(
        f"SELECT {', '.join('v.' + c for c in cols)}, c.heading_deg, c.lat, c.lon FROM building_views v "
        f"LEFT JOIN captures c ON c.pano_id = v.pano_id WHERE {_CELL_VIEWS.replace('building_id IN', 'v.building_id IN')} "
        "ORDER BY v.building_id, v.rank", (cell_id,))
    return [dict(zip(cols + ("heading_deg", "pano_lat", "pano_lon"), r)) for r in cur.fetchall()]


def effective_buildings(conn: sqlite3.Connection, cfg: Mapping[str, Any], cell_id: str) -> list[judgement.EffectiveBuilding]:
    """The final value of every building of the cell that has status ok, by building id (override > photo > register > default)."""
    estimates = {e["building_id"]: e for e in estimates_in_cell(conn, cell_id)}
    overrides = overrides_by_building(conn, cell_id)
    return [judgement.effective_building(b, estimates.get(b["building_id"]), overrides.get(b["building_id"]), cfg)
            for b in rows_in_cells(conn, "buildings", [cell_id]) if b["status"] == "ok"]


def export_cell(conn: sqlite3.Connection, cell_id: str, directory: str | Path) -> Path | None:
    """Write overrides/<cell>.json (BR-8.3). No file is made for a cell with nothing to keep; an old file is rewritten empty."""
    if not judgement.CELL_RE.fullmatch(cell_id):
        raise ValueError(f"not an H3 cell id: {cell_id[:40]!r}")
    overrides, estimates = overrides_in_cell(conn, cell_id), estimates_in_cell(conn, cell_id)
    path = Path(directory) / f"{cell_id}.json"
    if not overrides and not estimates and not path.exists():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(judgement.export_payload(cell_id, overrides, estimates), encoding="utf-8")
    os.replace(tmp, path)  # a half-written file never replaces a good one (BR-8.4)
    return path


def import_file(conn: sqlite3.Connection, cfg: Mapping[str, Any], path: str | Path) -> dict[str, Any]:
    """Load an export file into the database (BR-8.5): checked completely first, then written in one transaction.

    Rows are written by (building, field) and by building; rows the file does not mention stay. Rows of buildings that are
    not in the database are loaded too and reported as orphans.
    """
    p = Path(path)
    if p.stat().st_size > judgement.MAX_EXPORT_BYTES:
        raise ValueError("export file is too large")
    cell_id, overrides, estimates = judgement.parse_export(p.read_text(encoding="utf-8"), cfg)
    with conn:
        for o in overrides:
            conn.execute("INSERT OR REPLACE INTO overrides (building_id, field, value, cell_id, reason, set_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (o["building_id"], o["field"], json.dumps(o["value"]), cell_id, o["reason"], o["set_at"]))
        for e in estimates:
            conn.execute(
                "INSERT OR REPLACE INTO estimates (building_id, cell_id, floors_seen, confidence, height_est_m, wall_color, "
                "roof_shape, views_used, note, judged_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (e["building_id"], cell_id, e["floors_seen"], e["confidence"], e["height_est_m"], e["wall_color"],
                 e["roof_shape"], json.dumps(e["views_used"]), e["note"], e["judged_at"]))
    ids = {o["building_id"] for o in overrides} | {e["building_id"] for e in estimates}
    return {"cell_id": cell_id, "overrides": len(overrides), "estimates": len(estimates),
            "orphans": [(t, b) for t, b in orphans(conn) if b in ids]}
