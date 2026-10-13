# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""C6 (U5): facade details of every building, judged by Claude from the street-view sheet images and kept for the builder.

Usage:
  uv run src/details.py pending --cells 8930e0af13bffff [--limit 10] [--redo ID ...]   # bodies without a detail row + sheet paths
  uv run src/details.py record --file details.json                                     # or --file - for standard input
  uv run src/details.py list --cells 8930e0af13bffff
  uv run src/details.py export --cells 8930e0af13bffff        # rewrites regions/<region>/cells/<cell>/details.json (record and import do this by themselves)
  uv run src/details.py import --file details/8930e0af13bffff.json   # recovery: details back into the database
  uv run src/details.py --selftest                            # import check only

A detail row: building_id, finish (brick stone tile paint panel glass), ground_use (house shop garage), stair (none glass brick round),
bay 0/1, balcony 0/1, roof_color (dark red green brown blue pink), rooftop (none box railing tank), note. Unknown fields stay empty;
the builder fills them from the U4 note keywords, then from the defaults. Notes must not name people, plates or real shops.
Rules: aidlc-docs/construction/u5-details/functional-design/business-rules.md (BR-7)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

import common
import db
import details_rules

MAX_RECORD_BYTES = 2_000_000


def safe_name(building_id: str) -> str:
    """The sheet file name of a building id (same as estimate.py: `:` becomes `_`)."""
    if not details_rules.ID_RE.fullmatch(building_id):
        raise ValueError(f"not a usable building id: {building_id[:40]!r}")
    return building_id.replace(":", "_")


def pending_rows(conn, cfg, cell_id: str, limit: int, redo: Sequence[str] = ()) -> tuple[list[dict[str, Any]], int]:
    """Buildings of the cell without a detail row (or named in redo), by id, with their sheet path and the count left."""
    done = set(db.details_by_building(conn, cell_id))
    again = set(redo)
    rows = [b for b in db.rows_in_cells(conn, "buildings", [cell_id]) if b["status"] == "ok"
            and (b["building_id"] not in done or b["building_id"] in again)]
    items = [{"building_id": b["building_id"], "name": b.get("name") or "", "floors": b.get("floors_above"),
              "sheet": f"{cfg['captures_dir']}/{cell_id}/sheets/{safe_name(b['building_id'])}.jpg"} for b in rows[:limit]]
    return items, max(0, len(rows) - len(items))


def read_rows(path: str) -> list[Any]:
    raw = sys.stdin.read(MAX_RECORD_BYTES + 1) if path == "-" else Path(path).read_text(encoding="utf-8")
    if len(raw.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("detail file is too large")
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"detail file is not valid JSON: {e}") from None
    if not isinstance(data, list):
        raise ValueError("detail file must hold a list of detail rows")
    return data


def record(conn, cfg, rows: Sequence[Any]) -> int:
    """Store the rows (all or none) and refresh the export file of every cell they belong to."""
    count = db.record_details(conn, rows, common.now_iso())
    cells = {db.building_cell(conn, r["building_id"]) for r in rows}
    for cell in sorted(c for c in cells if c):
        db.export_details(conn, cell, common.cell_file(cfg, cell, "details"))
    return count


def cell_arg(text: str) -> str:
    if not details_rules.CELL_RE.fullmatch(text):
        raise argparse.ArgumentTypeError(f"not an H3 cell id: {text[:40]!r}")
    return text


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="details.py", description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true", help="check that the modules import; touches nothing")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("pending", help="buildings without a detail row and their sheet images")
    p.add_argument("--cells", nargs=1, required=True, type=cell_arg, metavar="ID")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--redo", nargs="*", default=[], metavar="ID", help="judge these buildings again")
    r = sub.add_parser("record", help="store detail rows from a JSON list")
    r.add_argument("--file", required=True, help="a file, or - for standard input")
    for name, text in (("list", "show the detail rows of cells"), ("export", "rewrite regions/<region>/cells/<cell>/details.json")):
        c = sub.add_parser(name, help=text)
        c.add_argument("--cells", nargs="+", required=True, type=cell_arg, metavar="ID")
    i = sub.add_parser("import", help="load an export file into the database")
    i.add_argument("--file", required=True)
    ns = parser.parse_args(list(argv))
    if not ns.selftest and not ns.command:
        parser.error("a command is required (pending, record, list, export, import) or --selftest")
    if ns.command == "pending":
        if not 1 <= ns.limit <= 500:
            parser.error("--limit must be from 1 to 500")
        bad = [x for x in ns.redo if not details_rules.ID_RE.fullmatch(x)]
        if bad:
            parser.error(f"--redo: not building ids: {bad}")
    return ns


def run_command(conn, cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, int]:
    if args.command == "pending":
        cell = args.cells[0]
        items, left = pending_rows(conn, cfg, cell, args.limit, args.redo)
        for item in items:
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
        print(f"# {len(items)} listed, {left} more without details")
        return {"listed": len(items), "remaining": left}
    if args.command == "record":
        n = record(conn, cfg, read_rows(args.file))
        print(f"recorded {n} details")
        return {"recorded": n}
    if args.command == "list":
        total = 0
        for cell in args.cells:
            rows = db.details_in_cell(conn, cell)
            total += len(rows)
            print(f"{cell}: {len(rows)} details")
            for d in rows:
                values = " ".join(f"{f}={d[f]}" for f in details_rules.DETAIL_FIELDS if d[f] is not None)
                print(f"  {d['building_id']} {values}  [{d['judged_at']}]")
        return {"listed": total}
    if args.command == "export":
        written = 0
        for cell in args.cells:
            path = db.export_details(conn, cell, common.cell_file(cfg, cell, "details"))
            written += path is not None
            print(f"{cell}: {path if path else 'nothing to export'}")
        return {"files": written}
    result = db.import_details(conn, args.file)
    db.export_details(conn, result["cell_id"], common.cell_file(cfg, result["cell_id"], "details"))
    print(f"imported {result['details']} details for {result['cell_id']}")
    for bid in result["orphans"]:
        print(f"orphan: {bid} (not a building in the database; kept)")
    return {"details": result["details"], "orphans": len(result["orphans"])}


def main(cfg: dict[str, Any]) -> int:
    args = parse_args(sys.argv[1:])
    if args.selftest:
        print("selftest ok: common, db and details_rules import")
        return 0
    conn = db.connect(common.resolve(cfg["db_path"]))
    started = common.now_iso()
    cell = args.cells[0] if getattr(args, "cells", None) else None
    try:
        counts = run_command(conn, cfg, args)
    except (ValueError, OSError) as e:  # a refused call: say why; nothing was changed
        message = common.mask(f"{type(e).__name__}: {e}")
        common.log(logging.ERROR, f"refused: {message}", cell)
        print(f"refused: {message}", file=sys.stderr)
        return 1
    db.record_run(conn, cell_id=cell, unit="C7", started_at=started, finished_at=common.now_iso(), status="ok",
                  counts={"command": args.command, **counts})
    common.log(logging.INFO, f"{args.command} done", cell, **counts)
    return 0


if __name__ == "__main__":
    common.run_cli(main, "details")
