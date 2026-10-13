# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""G: the detail tier (1, 2, 3) of each cell from OSM land use and facilities -> regions/<region>/tiers.json (U7 G, kept in git).

Usage (repo root; the cell must be in the cells list of its region.toml first):
  uv run src/tiers.py classify --cells 8930e0af13bffff [...]                    # Overpass, one call per cell
  uv run src/tiers.py set --cell 8930e0af13bffff --tier 2 --reason "..."        # hand-set: classify keeps it and only refreshes counts
  uv run src/tiers.py list --cells 8930e0af13bffff [...]

Tier 1: landmarks (school, station, park, hospital, market, public office ...), shopping streets, commercial land: street view,
judgement, interiors and signs in full. Tier 2: housing: rule defaults, light interiors. Tier 3: industry, farmland, forest:
boxes only. The thresholds are set so the first three cells are tier 1 (plan G). OSM buildings are not counted: in Korea OSM has
5 to 12 per cell where V-World has 85 to 223 (2026-10-14), so a count would call the town centre "edge of town".
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import h3
from shapely.geometry import Polygon

import common

OVERPASS = "https://overpass-api.de/api/interpreter"
LANDMARK_AREAS = {  # counted as landmarks only as areas (ways, relations): a clinic node is a shop-like point, not a landmark
    "amenity": {"school", "university", "college", "hospital", "townhall", "marketplace", "place_of_worship", "library",
                "community_centre", "police", "fire_station"},
    "leisure": {"park", "stadium", "sports_centre"},
}
STATION = (("railway", "station"), ("public_transport", "station"))
SHOP_AMENITY = {"restaurant", "cafe", "fast_food", "bar", "bank", "pharmacy", "clinic", "dentist", "doctors", "hospital",
                "fuel", "post_office"}
COMMERCIAL = {"commercial", "retail"}
INDUSTRIAL = {"industrial", "railway", "quarry", "landfill", "construction"}
RURAL = {"farmland", "farmyard", "forest", "meadow", "orchard", "grass", "greenhouse_horticulture"}
POI_MIN = 20             # shops and shop-like amenities that make a shopping street (tier 1)
COMMERCIAL_MIN = 0.25    # share of the cell that is commercial or retail land (tier 1)
INDUSTRIAL_MIN = 0.4     # share that is industrial land (tier 3)
RURAL_MIN = 0.5          # share that is farmland, forest or grass (tier 3)
LANDMARK_IN_MIN = 0.1    # a landmark area counts for the cell when this share of it lies in the cell (the school is 61/22/16 % in the
                         # first three cells: the origin vertex sits beside it); a sliver does not


def query(cell_id: str) -> str:
    poly = " ".join(f"{lat:.6f} {lon:.6f}" for lat, lon in h3.cell_to_boundary(cell_id))
    p = f'(poly:"{poly}")'
    return ("[out:json][timeout:90];"
            f'way["landuse"]{p};out geom;'
            f'(nwr["amenity"]{p};nwr["leisure"]{p};nwr["shop"]{p};nwr["railway"="station"]{p};nwr["public_transport"="station"]{p};);'
            "out geom;")


def classify(cell_id: str, elements: Sequence[Mapping[str, Any]]) -> tuple[int, str, dict[str, Any]]:
    """(tier, reason, counts) from the Overpass elements of one cell. Deterministic: the same elements give the same answer."""
    cell = Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(cell_id)])
    share = {"commercial": 0.0, "industrial": 0.0, "rural": 0.0, "residential": 0.0}
    landmarks: set[str] = set()
    pois = 0
    for e in elements:
        tags = e.get("tags") or {}
        area = _area(e)
        if "landuse" in tags:
            if area is None:
                continue  # an open landuse way (or a relation) is not counted
            lu = tags["landuse"]
            area = area.intersection(cell).area / cell.area
            group = "commercial" if lu in COMMERCIAL else "industrial" if lu in INDUSTRIAL else "rural" if lu in RURAL else \
                "residential" if lu == "residential" else None
            if group:
                share[group] += area
            continue
        name = tags.get("name") or e.get("type", "") + str(e.get("id", ""))
        landmark_area = e.get("type") in ("way", "relation") and any(tags.get(k) in vs for k, vs in LANDMARK_AREAS.items())
        if landmark_area and area is not None and area.area > 0 and area.intersection(cell).area / area.area < LANDMARK_IN_MIN:
            continue  # only a sliver of it is in this cell
        if any(tags.get(k) == v for k, v in STATION) or landmark_area:
            landmarks.add(f"{tags.get('amenity') or tags.get('leisure') or 'station'}:{name}")
        elif "shop" in tags or tags.get("amenity") in SHOP_AMENITY:
            pois += 1
    share = {k: round(min(v, 1.0), 3) for k, v in share.items()}  # overlapping ways may add past 1
    counts = {"landmarks": sorted(landmarks), "pois": pois, "share": share}
    if landmarks:
        return 1, f"landmarks: {', '.join(sorted(landmarks)[:4])}", counts
    if pois >= POI_MIN:
        return 1, f"shopping street: {pois} shops", counts
    if share["commercial"] >= COMMERCIAL_MIN:
        return 1, f"commercial land {share['commercial']:.0%}", counts
    if share["industrial"] >= INDUSTRIAL_MIN:
        return 3, f"industrial land {share['industrial']:.0%}", counts
    if share["rural"] >= RURAL_MIN:
        return 3, f"farmland, forest or grass {share['rural']:.0%}", counts
    return 2, "housing", counts


def _area(e: Mapping[str, Any]) -> Polygon | None:
    """The polygon of a closed way with `out geom`; None for nodes, open ways and relations (a relation landmark counts whole)."""
    ring = [(p["lon"], p["lat"]) for p in e.get("geometry") or [] if p]
    if e.get("type") != "way" or len(ring) < 4 or ring[0] != ring[-1]:
        return None
    return Polygon(ring).buffer(0)


# --- tiers.json ------------------------------------------------------------------------------------------------------------

def tiers_path(cfg: Mapping[str, Any], cell_id: str) -> Path:
    folder, _ = common.region_of(cfg, cell_id)
    return folder / "tiers.json"


def read_tiers(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("cells") if isinstance(data, dict) else None
    if not isinstance(rows, dict) or not all(isinstance(r, dict) and r.get("tier") in (1, 2, 3) for r in rows.values()):
        raise ValueError(f"{path}: not a tiers file")
    return rows


def write_tiers(path: Path, rows: Mapping[str, Mapping[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"cells": dict(sorted(rows.items()))}, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def merge(old: Mapping[str, Any] | None, tier: int, reason: str, counts: Mapping[str, Any]) -> dict[str, Any]:
    """A hand-set tier stays (only the counts are refreshed); otherwise the classified one."""
    if old and old.get("manual"):
        return {**old, "counts": dict(counts)}
    return {"tier": tier, "reason": reason, "counts": dict(counts), "manual": False}


def tier_of(cfg: Mapping[str, Any], cell_id: str) -> int | None:
    """The cell's tier, or None when it was never classified (then the cycle treats it as tier 1)."""
    row = read_tiers(tiers_path(cfg, cell_id)).get(cell_id)
    return row["tier"] if row else None


# --- command line ------------------------------------------------------------------------------------------------------------

def parse_args(argv: Sequence[str], res: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tiers.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("classify", "list"):
        sub.add_parser(name).add_argument("--cells", nargs="+", required=True, metavar="ID")
    s = sub.add_parser("set")
    s.add_argument("--cell", required=True, metavar="ID")
    s.add_argument("--tier", required=True, type=int, choices=(1, 2, 3))
    s.add_argument("--reason", required=True)
    ns = parser.parse_args(list(argv))
    cells = ns.cells if ns.command != "set" else [ns.cell]
    bad = [c for c in cells if not (h3.is_valid_cell(c) and h3.get_resolution(c) == res)]
    if bad:
        parser.error(f"not valid resolution-{res} H3 cell IDs: {bad}")
    if ns.command == "set" and not ns.reason.strip():
        parser.error("--reason must say who decided and why")
    return ns


def main(cfg: dict[str, Any]) -> int:
    args = parse_args(sys.argv[1:], cfg["h3_res"])
    if args.command == "set":
        path = tiers_path(cfg, args.cell)
        rows = read_tiers(path)
        rows[args.cell] = {**rows.get(args.cell, {"counts": {}}), "tier": args.tier, "reason": args.reason.strip(), "manual": True}
        write_tiers(path, rows)
        print(f"{args.cell}: tier {args.tier} (hand-set) -> {path}")
        return 0
    if args.command == "list":
        for cell in args.cells:
            row = read_tiers(tiers_path(cfg, cell)).get(cell)
            print(f"{cell}: " + (f"tier {row['tier']}{' (hand-set)' if row.get('manual') else ''}: {row['reason']}" if row else "not classified"))
        return 0
    failed = 0
    for cell in args.cells:
        try:
            path = tiers_path(cfg, cell)
            response = common.http_get_json(OVERPASS, {"data": query(cell)}, waits=cfg["retry_waits_s"], pause_s=cfg["overpass_pause_s"])
            tier, reason, counts = classify(cell, response.get("elements") or [])
            rows = read_tiers(path)
            rows[cell] = merge(rows.get(cell), tier, reason, counts)
            write_tiers(path, rows)
            common.log(logging.INFO, f"tier {rows[cell]['tier']}: {rows[cell]['reason']}", cell)
        except Exception as e:  # carry on with the next cell; its old row stays
            failed += 1
            common.log(logging.ERROR, common.mask(f"cell failed: {type(e).__name__}: {e}"), cell)
    return 1 if failed else 0


if __name__ == "__main__":
    common.run_cli(main, "tiers")
