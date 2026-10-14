# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""C1: fill a zone with H3 cells and collect OSM data (building names/tags, roads, street furniture).

Usage:
  uv run --env-file .env src/cells.py RES lat,lon lat,lon lat,lon [lat,lon ...]
  uv run --env-file .env src/cells.py --cells 8930e0af13bffff [8930e0af123ffff ...]

Writes to the SQLite database (data/map.db). Finished V-World buildings are assembled by register.py.
Rules: aidlc-docs/construction/u1-data-foundation/functional-design/business-rules.md
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import h3

import common
import db
import geo

OVERPASS = "https://overpass-api.de/api/interpreter"
M_PER_DEG_LAT = 111_320.0
ROAD_CLASSES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service",
    "living_street", "road", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
PATH_CLASSES = {"pedestrian", "footway", "path", "steps", "cycleway", "track", "bridleway", "corridor"}
NODE_KINDS = (("highway", "crossing", "crossing"), ("natural", "tree", "tree"),
              ("highway", "street_lamp", "street_lamp"), ("amenity", "bench", "bench"),
              ("railway", "subway_entrance", "subway_entrance"))


# --- cells (BR-1) -----------------------------------------------------------------------

def fill_cells(points: Sequence[tuple[float, float]], res: int) -> list[str]:
    """H3 cells whose center is inside the polygon. An empty result is an error (BR-1.2)."""
    if len(points) < 3:
        raise ValueError("a zone needs at least 3 points")
    for lat, lon in points:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"point out of range: {lat},{lon}")
    cells = sorted(h3.polygon_to_cells(h3.LatLngPoly(list(points)), res))
    if not cells:
        raise ValueError("polygon too small for this resolution: use a higher RES or pass --cells")
    return cells


def check_cells(cell_ids: Sequence[str], res: int) -> list[str]:
    """Validate cell IDs: valid H3 and the configured resolution (BR-1.3)."""
    out = []
    for c in cell_ids:
        if not (isinstance(c, str) and h3.is_valid_cell(c)):
            raise ValueError(f"not a valid H3 cell: {c!r}")
        if h3.get_resolution(c) != res:
            raise ValueError(f"cell {c} has resolution {h3.get_resolution(c)}, expected {res}")
        out.append(c)
    return sorted(set(out))


def parse_args(argv: Sequence[str], res: int) -> list[str]:
    """Command line -> cell IDs. Accepts `RES lat,lon ...` or `--cells ID ...`."""
    parser = argparse.ArgumentParser(prog="cells.py", description=__doc__.split("\n")[0])
    parser.add_argument("--cells", nargs="+", metavar="ID", help="H3 cell IDs to collect")
    parser.add_argument("zone", nargs="*", help="RES lat,lon lat,lon lat,lon ...")
    ns = parser.parse_args(list(argv))
    if ns.cells:
        if ns.zone:
            parser.error("give either --cells or RES with points, not both")
        try:
            return check_cells(ns.cells, res)
        except ValueError as e:
            parser.error(str(e))
    if not ns.zone:
        parser.error("give RES with at least 3 lat,lon points, or --cells")
    try:
        zone_res = int(ns.zone[0])
        points = [tuple(float(x) for x in p.split(",")) for p in ns.zone[1:]]
        if any(len(p) != 2 for p in points):
            raise ValueError
    except ValueError:
        parser.error("zone must look like: 9 37.50,126.77 37.50,126.78 37.51,126.78")
    if zone_res != res:
        parser.error(f"RES must be {res} (config.toml h3_res)")
    try:
        return fill_cells(points, zone_res)
    except ValueError as e:
        parser.error(str(e))


# --- Overpass query and parsing (BR-7.4, BR-8) ----------------------------------------------

def cell_bbox(cell_id: str, buffer_m: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) of the cell boundary widened by buffer_m (BR-4.9)."""
    boundary = h3.cell_to_boundary(cell_id)
    lats = [p[0] for p in boundary]
    lons = [p[1] for p in boundary]
    dlat = buffer_m / M_PER_DEG_LAT
    dlon = buffer_m / (M_PER_DEG_LAT * math.cos(math.radians(sum(lats) / len(lats))))
    return (min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon)


def overpass_query(bbox: tuple[float, float, float, float]) -> str:
    box = ",".join(f"{v:.6f}" for v in bbox)
    return (
        "[out:json][timeout:60];("
        f'way["building"]({box});way["highway"]({box});'
        f'node["highway"="crossing"]({box});node["natural"="tree"]({box});'
        f'node["highway"="street_lamp"]({box});node["amenity"="bench"]({box});node["railway"="subway_entrance"]({box});'
        ");out geom tags;"
    )


def _is_point(p: Any) -> bool:
    return (isinstance(p, Mapping) and isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float))
            and -90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180)


def cells_touched(points: Sequence[tuple[float, float]], res: int, step_m: float = 25.0) -> set[str]:
    """Cells a polyline passes through, sampled every step_m so no cell on the way is skipped."""
    cells = {geo.assign_cell(p, res) for p in points}
    for (la1, lo1), (la2, lo2) in zip(points, points[1:]):
        dy = (la2 - la1) * M_PER_DEG_LAT
        dx = (lo2 - lo1) * M_PER_DEG_LAT * math.cos(math.radians((la1 + la2) / 2))
        n = int(math.hypot(dx, dy) // step_m)
        for i in range(1, n + 1):
            t = i / (n + 1)
            cells.add(geo.assign_cell((la1 + (la2 - la1) * t, lo1 + (lo2 - lo1) * t), res))
    return cells


def _street_kind(tags: Mapping[str, str], is_node: bool) -> tuple[str, str | None] | None:
    if is_node:
        for key, value, kind in NODE_KINDS:
            if tags.get(key) == value:
                return kind, value if kind == "crossing" else None
        return None
    highway = tags.get("highway")
    if highway == "footway" and tags.get("footway") == "crossing":
        return "crossing", "footway"
    if highway in ROAD_CLASSES:
        return "road", highway
    if highway in PATH_CLASSES:
        return "path", highway
    return None


@dataclass
class OsmParse:
    buildings: list[geo.OsmBuilding] = field(default_factory=list)
    features: list[dict[str, Any]] = field(default_factory=list)  # street_features rows without cell_id
    dropped: int = 0


def parse_osm(response: Any, res: int, cell_id: str) -> OsmParse:
    """Validate an Overpass response and turn it into buildings and street features.

    Malformed elements are dropped and counted. A response that is not an Overpass result is an error.
    """
    if not isinstance(response, Mapping) or not isinstance(response.get("elements"), list):
        raise ValueError("unexpected Overpass response: no 'elements' list")
    out = OsmParse()
    for el in response["elements"]:
        try:
            if not isinstance(el, Mapping) or el.get("type") not in ("way", "node") or not isinstance(el.get("id"), int):
                raise ValueError("element shape")
            tags = el.get("tags", {})
            if not isinstance(tags, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in tags.items()):
                raise ValueError("tags")
            if el["type"] == "node":
                if not _is_point(el):
                    raise ValueError("node point")
                kind = _street_kind(tags, True)
                if kind is None:
                    continue
                out.features.append({"feature_id": f"node:{el['id']}", "kind": kind[0], "highway_class": kind[1],
                                     "geometry": [[el["lat"], el["lon"]]], "tags": tags})
                continue
            geometry = el.get("geometry")
            if not isinstance(geometry, list) or not geometry or not all(_is_point(p) for p in geometry):
                raise ValueError("way geometry")
            points = [(float(p["lat"]), float(p["lon"])) for p in geometry]
            if "building" in tags:
                b = geo.new_osm_building(el["id"], points, tags, res)
                if h3.grid_distance(cell_id, b.cell_id) > 2:
                    raise ValueError("building far from the cell")
                out.buildings.append(b)
            elif "highway" in tags:
                kind = _street_kind(tags, False)
                if kind is None:
                    continue
                out.features.append({"feature_id": f"way:{el['id']}", "kind": kind[0], "highway_class": kind[1],
                                     "geometry": [list(p) for p in points], "tags": tags})
        except (ValueError, h3.H3BaseException):
            out.dropped += 1
    return out


def street_rows_for_cell(features: Sequence[Mapping[str, Any]], cell_id: str, res: int) -> list[dict[str, Any]]:
    """Street features that touch the cell, as street_features rows (BR-2.3). Subway entrances of the whole query box are kept so a
    cell can find its station's middle from its neighbours' entrances; the build makes only the cell's own (2026-10-14)."""
    rows = []
    for f in features:
        pts = [tuple(p) for p in f["geometry"]]
        if f["kind"] == "subway_entrance" or cell_id in cells_touched(pts, res):
            rows.append({**f, "cell_id": cell_id})
    return rows


# --- collection ------------------------------------------------------------------------------

def collect_cell(conn, cfg: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    """Fetch OSM data for one cell and replace what the cell owns. Returns the counts."""
    res = cfg["h3_res"]
    bbox = cell_bbox(cell_id, cfg["buffer_m"])
    common.log(logging.INFO, "fetching OSM (buildings, roads, street furniture)", cell_id)
    response = common.http_get_json(OVERPASS, {"data": overpass_query(bbox)}, waits=cfg["retry_waits_s"],
                                    pause_s=cfg["overpass_pause_s"])
    parsed = parse_osm(response, res, cell_id)
    lat, lon = h3.cell_to_latlng(cell_id)
    tables = {
        "cells": [{"cell_id": cell_id, "res": res, "center_lat": lat, "center_lon": lon,
                   "boundary": [list(p) for p in h3.cell_to_boundary(cell_id)]}],
        "osm_buildings": db.to_rows(parsed.buildings),
        "street_features": street_rows_for_cell(parsed.features, cell_id, res),
    }
    db.backup(conn, common.resolve(cfg["backup_dir"]), cfg["backup_keep"])
    db.replace_cell_rows(conn, cell_id, tables)
    owned = sum(1 for b in parsed.buildings if b.cell_id == cell_id)
    counts = {
        "osm_buildings_fetched": len(parsed.buildings), "osm_buildings_owned": owned,
        "osm_buildings_invalid": sum(1 for b in parsed.buildings if not b.valid),
        "street_features": len(tables["street_features"]), "dropped_elements": parsed.dropped,
    }
    for table, building_id in db.orphans(conn):
        common.log(logging.WARNING, f"orphan: {table} row for missing building {building_id}", cell_id)
    common.log(logging.INFO, "OSM data saved", cell_id, **counts)
    return counts


def main(cfg: dict[str, Any]) -> int:
    cells = parse_args(sys.argv[1:], cfg["h3_res"])
    conn = db.connect(common.resolve(cfg["db_path"]))
    failures = 0
    for cell_id in cells:
        started = common.now_iso()
        try:
            counts = collect_cell(conn, cfg, cell_id)
            db.record_run(conn, cell_id=cell_id, unit="C1", started_at=started, finished_at=common.now_iso(),
                          status="ok", counts=counts)
        except Exception as e:  # one failed cell must not stop the others; its old data stays (BR-7.1)
            failures += 1
            message = common.mask(f"{type(e).__name__}: {e}")
            common.log(logging.ERROR, f"cell failed, previous data kept: {message}", cell_id)
            db.record_run(conn, cell_id=cell_id, unit="C1", started_at=started, finished_at=common.now_iso(),
                          status="failed", error=message)
    common.log(logging.INFO, f"done: {len(cells) - failures} ok, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    common.run_cli(main, "cells")
