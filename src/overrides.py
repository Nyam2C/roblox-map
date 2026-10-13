# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""C5: corrections the user and Claude agree on while looking at the built cell (values only, always with a reason).

Usage:
  uv run src/overrides.py set --building gis:11081057 --field floors_above --value 4 --reason "user and Claude counted 4 floors on the photo"
  uv run src/overrides.py unset --building gis:11081057 --field floors_above
  uv run src/overrides.py list --cells 8930e0af13bffff
  uv run src/overrides.py export --cells 8930e0af13bffff       # rewrites regions/<region>/cells/<cell>/overrides.json (set and unset do this by themselves)
  uv run src/overrides.py import --file overrides/8930e0af13bffff.json   # recovery: corrections and judgements back into the database
  uv run src/overrides.py --selftest                           # import check only

Fields: floors_above, height_m, wall_color, roof_shape. Nothing re-collects or rebuilds ever deletes a correction.
Rules: aidlc-docs/construction/u4-judgement-corrections/functional-design/business-rules.md (BR-6, BR-8)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Sequence

import common
import db
import judgement


def parse_value(text: str) -> Any:
    """`4` and `10.5` are numbers, `cream` and `"cream"` are text."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def cell_arg(text: str) -> str:
    if not judgement.CELL_RE.fullmatch(text):
        raise argparse.ArgumentTypeError(f"not an H3 cell id: {text[:40]!r}")
    return text


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="overrides.py", description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true", help="check that the modules import; touches nothing")
    sub = parser.add_subparsers(dest="command")
    s = sub.add_parser("set", help="set a correction")
    s.add_argument("--building", required=True, metavar="ID")
    s.add_argument("--field", required=True, choices=judgement.FIELDS)
    s.add_argument("--value", required=True, type=parse_value)
    s.add_argument("--reason", required=True, help="who looked at what and decided this (it goes to the public repository: no personal data)")
    u = sub.add_parser("unset", help="remove a correction")
    u.add_argument("--building", required=True, metavar="ID")
    u.add_argument("--field", required=True, choices=judgement.FIELDS)
    for name, text in (("list", "show the corrections of cells"), ("export", "rewrite regions/<region>/cells/<cell>/overrides.json")):
        c = sub.add_parser(name, help=text)
        c.add_argument("--cells", nargs="+", required=True, type=cell_arg, metavar="ID")
    i = sub.add_parser("import", help="load an export file into the database")
    i.add_argument("--file", required=True)
    ns = parser.parse_args(list(argv))
    if not ns.selftest and not ns.command:
        parser.error("a command is required (set, unset, list, export, import) or --selftest")
    return ns


def run_command(conn, cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, int]:
    """Do one command. Returns the counts for the run record. A refused call raises ValueError and changes nothing."""
    if args.command == "set":
        changed = db.set_override(conn, cfg, args.building, args.field, args.value, args.reason, common.now_iso())
        cell = db.building_cell(conn, args.building)
        path = db.export_cell(conn, cell, common.cell_file(cfg, cell, "overrides"))
        print(f"{'set' if changed else 'unchanged'}: {args.building} {args.field} (file {path})")
        return {"set": int(changed)}
    if args.command == "unset":
        cell = db.unset_override(conn, args.building, args.field)
        if cell is None:
            print(f"nothing to remove: {args.building} {args.field}")
            return {"unset": 0}
        print(f"removed: {args.building} {args.field} (file {db.export_cell(conn, cell, common.cell_file(cfg, cell, 'overrides'))})")
        return {"unset": 1}
    if args.command == "list":
        total = 0
        for cell in args.cells:
            rows = db.overrides_in_cell(conn, cell)
            total += len(rows)
            print(f"{cell}: {len(rows)} overrides")
            for o in rows:
                print(f"  {o['building_id']} {o['field']} = {json.dumps(o['value'], ensure_ascii=False)}  [{o['set_at']}] {o['reason']}")
        return {"listed": total}
    if args.command == "export":
        written = 0
        for cell in args.cells:
            path = db.export_cell(conn, cell, common.cell_file(cfg, cell, "overrides"))
            written += path is not None
            print(f"{cell}: {path if path else 'nothing to export'}")
        return {"files": written}
    result = db.import_file(conn, cfg, args.file)
    print(f"imported {result['overrides']} overrides and {result['estimates']} judgements for {result['cell_id']}")
    for table, bid in result["orphans"]:
        print(f"orphan: {table} {bid} (not a building in the database; kept)")
    return {"overrides": result["overrides"], "estimates": result["estimates"], "orphans": len(result["orphans"])}


def main(cfg: dict[str, Any]) -> int:
    args = parse_args(sys.argv[1:])
    if args.selftest:
        print("selftest ok: common, db and judgement import")
        return 0
    conn = db.connect(common.resolve(cfg["db_path"]))
    started = common.now_iso()
    try:
        counts = run_command(conn, cfg, args)
    except ValueError as e:  # a refused call: say why, nothing was changed
        message = common.mask(str(e))
        common.log(logging.ERROR, f"refused: {message}")
        print(f"refused: {message}", file=sys.stderr)
        return 1
    db.record_run(conn, cell_id=None, unit="C5", started_at=started, finished_at=common.now_iso(), status="ok",
                  counts={"command": args.command, **counts})
    common.log(logging.INFO, f"{args.command} done", **counts)
    return 0


if __name__ == "__main__":
    common.run_cli(main, "overrides")
