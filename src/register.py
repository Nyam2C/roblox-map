# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""C2: fetch V-World building data and assemble each cell's final buildings.

V-World footprints are the base; OSM buildings (collected by cells.py) only add names and tags.

Usage:
  uv run --env-file .env src/register.py --cells 8930e0af13bffff [...]
  uv run --env-file .env src/register.py --all        # every cell already collected by cells.py

Needs VWORLD_KEY in the environment (see .env.example).
Rules: aidlc-docs/construction/u1-data-foundation/functional-design/business-rules.md
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from typing import Any, Mapping, Sequence

import h3

import cells as cells_module
import common
import db
import geo

VWORLD = "https://api.vworld.kr/req/data"
LAYER = "LT_C_BLDGINFO"
FEATURE_ID = re.compile(r"^LT_C_BLDGINFO\.(\d+)$")


class VworldError(RuntimeError):
    pass


# --- parsing (BR-7.2, BR-7.4) -----------------------------------------------------------------

def parse_vworld_page(response: Any, res: int, cell_id: str) -> tuple[list[geo.GisBuilding], dict[str, int]]:
    """Validate one V-World GetFeature page and convert its features.

    Returns (buildings, info) where info has `total` (all records), `pages` (page count), `dropped`
    (malformed features) and `polygons_dropped` (extra polygons of MultiPolygon buildings).
    A non-OK status raises VworldError with V-World's own error code (never the key).
    """
    resp = response.get("response") if isinstance(response, Mapping) else None
    if not isinstance(resp, Mapping):
        raise VworldError("unexpected V-World response: no 'response'")
    status = resp.get("status")
    if status == "NOT_FOUND":  # V-World's answer for an empty area
        return [], {"total": 0, "pages": 0, "dropped": 0, "polygons_dropped": 0}
    if status != "OK":
        error = resp.get("error") if isinstance(resp.get("error"), Mapping) else {}
        code = error.get("code", "UNKNOWN") if isinstance(error.get("code", "UNKNOWN"), str) else "UNKNOWN"
        raise VworldError(f"V-World status {status!r}, error code {code}")
    try:
        total = int(resp["record"]["total"])
        pages = int(resp["page"]["total"])
        features = resp["result"]["featureCollection"]["features"]
    except (KeyError, TypeError, ValueError):
        raise VworldError("unexpected V-World response: missing record, page or features") from None
    if not isinstance(features, list):
        raise VworldError("unexpected V-World response: features is not a list")
    buildings: list[geo.GisBuilding] = []
    dropped = polygons_dropped = 0
    for f in features:
        try:
            if not isinstance(f, Mapping):
                raise ValueError("feature shape")
            m = FEATURE_ID.match(str(f.get("id", "")))
            props = f.get("properties")
            if not m or not isinstance(props, Mapping):
                raise ValueError("feature id or properties")
            outline, extra = geo.outline_from_geojson(f["geometry"])
            if not all(-90 <= p[0] <= 90 and -180 <= p[1] <= 180 for p in outline):
                raise ValueError("coordinates out of range")
            b = geo.new_gis_building(m.group(1), outline, props, res)
            if h3.grid_distance(cell_id, b.cell_id) > 2:
                raise ValueError("building far from the cell")
            buildings.append(b)
            polygons_dropped += extra
        except (ValueError, KeyError, TypeError, IndexError, h3.H3BaseException):
            dropped += 1
    return buildings, {"total": total, "pages": pages, "dropped": dropped, "polygons_dropped": polygons_dropped}


def merge_pages(pages: Sequence[tuple[list[geo.GisBuilding], dict[str, int]]]) -> tuple[list[geo.GisBuilding], dict[str, int]]:
    """Merge pages: one building per gis_key, and the count must match `total` (P-10)."""
    if not pages:
        return [], {"total": 0, "pages": 0, "dropped": 0, "polygons_dropped": 0}
    total = pages[0][1]["total"]
    by_key: dict[str, geo.GisBuilding] = {}
    dropped = polygons_dropped = 0
    for buildings, info in pages:
        if info["total"] != total:
            raise VworldError("V-World total changed while paging")
        dropped += info["dropped"]
        polygons_dropped += info["polygons_dropped"]
        for b in buildings:
            by_key[b.gis_key] = b
    if len(by_key) + dropped != total:
        raise VworldError(f"V-World returned {len(by_key) + dropped} of {total} records")
    return sorted(by_key.values(), key=lambda b: b.gis_key), {
        "total": total, "pages": pages[0][1]["pages"], "dropped": dropped, "polygons_dropped": polygons_dropped}


# --- fetching ----------------------------------------------------------------------------------

def fetch_vworld(cell_id: str, cfg: Mapping[str, Any]) -> tuple[list[geo.GisBuilding], dict[str, int]]:
    """Every V-World building in the buffered cell box, following the pages (BR-7.2)."""
    key = common.get_secret("VWORLD_KEY")
    south, west, north, east = cells_module.cell_bbox(cell_id, cfg["buffer_m"])
    pages = []
    page = 1
    while True:
        params = {
            "service": "data", "request": "GetFeature", "data": LAYER, "key": key, "crs": "EPSG:4326",
            "format": "json", "geometry": "true", "attribute": "true", "size": cfg["vworld_page_size"],
            "page": page, "geomFilter": f"BOX({west:.6f},{south:.6f},{east:.6f},{north:.6f})",
        }
        response = common.http_get_json(VWORLD, params, waits=cfg["retry_waits_s"], pause_s=cfg["vworld_pause_s"])
        parsed = parse_vworld_page(response, cfg["h3_res"], cell_id)
        pages.append(parsed)
        common.log(logging.INFO, f"V-World page {page}/{parsed[1]['pages']}", cell_id, received=len(parsed[0]))
        if page >= parsed[1]["pages"]:
            break
        page += 1
    return merge_pages(pages)


# --- assembly ------------------------------------------------------------------------------------

def _osm_from_row(row: Mapping[str, Any]) -> geo.OsmBuilding:
    return geo.OsmBuilding(
        osm_id=row["osm_id"], cell_id=row["cell_id"], outline=tuple(tuple(p) for p in row["outline"]),
        centroid=tuple(row["centroid"]), tags=row["tags"] or {}, height_m=row["height_m"], levels=row["levels"],
        valid=row["valid"])


def assemble_cell(conn, cfg: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    """Fetch V-World, combine it with the stored OSM buildings and replace this cell's buildings."""
    neighborhood = sorted(h3.grid_disk(cell_id, 1))
    osm = [_osm_from_row(r) for r in db.rows_in_cells(conn, "osm_buildings", neighborhood)]
    if not osm:
        common.log(logging.WARNING, "no OSM buildings stored near this cell (run cells.py first); "
                   "buildings will have no names or tags", cell_id)
    gis, info = fetch_vworld(cell_id, cfg)
    result = geo.assemble(osm, gis, cfg["overlap_threshold"])
    owned = [b for b in result if b.cell_id == cell_id]
    gis_rows = db.to_rows(gis)
    db.backup(conn, common.resolve(cfg["backup_dir"]), cfg["backup_keep"])
    db.replace_cell_rows(conn, cell_id, {"gis_buildings": gis_rows, "buildings": db.to_rows(owned)})
    for table, building_id in db.orphans(conn):
        common.log(logging.WARNING, f"orphan: {table} row for missing building {building_id}", cell_id)
    counts = {
        "vworld_total": info["total"], "vworld_dropped": info["dropped"], "multipolygon_extra_polygons": info["polygons_dropped"],
        "gis_invalid": sum(1 for g in gis if not g.valid),
        "buildings_owned": len(owned), "from_vworld": sum(1 for b in owned if b.source == "gis"),
        "osm_only": sum(1 for b in owned if b.source == "osm"), "with_osm_tags": sum(1 for b in owned if b.osm_tags),
        "floors_known": sum(1 for b in owned if b.floors_above), "height_known": sum(1 for b in owned if b.height_m),
    }
    common.log(logging.INFO, "buildings assembled", cell_id, **counts)
    return counts


def parse_args(argv: Sequence[str], res: int, known: Sequence[str]) -> list[str]:
    parser = argparse.ArgumentParser(prog="register.py", description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cells", nargs="+", metavar="ID", help="H3 cell IDs to assemble")
    group.add_argument("--all", action="store_true", help="every cell collected by cells.py")
    ns = parser.parse_args(list(argv))
    if ns.all:
        if not known:
            parser.error("no cells in the database yet: run cells.py first")
        return sorted(known)
    try:
        return cells_module.check_cells(ns.cells, res)
    except ValueError as e:
        parser.error(str(e))


def main(cfg: dict[str, Any]) -> int:
    conn = db.connect(common.resolve(cfg["db_path"]))
    cell_ids = parse_args(sys.argv[1:], cfg["h3_res"], db.all_cell_ids(conn))
    failures = 0
    for cell_id in cell_ids:
        started = common.now_iso()
        try:
            counts = assemble_cell(conn, cfg, cell_id)
            db.record_run(conn, cell_id=cell_id, unit="C2", started_at=started, finished_at=common.now_iso(),
                          status="ok", counts=counts)
        except Exception as e:  # keep the old buildings and carry on with the next cell (BR-7.1)
            failures += 1
            message = common.mask(f"{type(e).__name__}: {e}")
            common.log(logging.ERROR, f"cell failed, previous data kept: {message}", cell_id)
            db.record_run(conn, cell_id=cell_id, unit="C2", started_at=started, finished_at=common.now_iso(),
                          status="failed", error=message)
    common.log(logging.INFO, f"done: {len(cell_ids) - failures} ok, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    common.run_cli(main, "register")
