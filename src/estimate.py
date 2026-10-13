# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow==12.3.0", "h3==4.5.0", "shapely==2.2.0"]
# ///
"""C4: floors, height and look of every building, judged from street-view photos by Claude and checked against the register.

Usage (Claude runs these; the judging itself is Claude looking at the sheet images):
  uv run src/estimate.py pending --cells 8930e0af13bffff [--limit 10] [--redo ID ...]   # blind list + sheet images to judge next
  uv run src/estimate.py record --file judgements.json                                  # or --file - for standard input
  uv run src/estimate.py report --cells 8930e0af13bffff                                 # AFTER judging: statuses, agreement, review list
  uv run src/estimate.py plan --cells 8930e0af13bffff                                   # Studio camera values -> data/build/<cell>/review.json
  uv run src/estimate.py compose --cells 8930e0af13bffff --captures captures.json       # Studio capture + crop side by side
  uv run src/estimate.py --selftest                                                     # import check only

`pending` shows no register or OSM numbers (blind judgement); `record` never reads them either. Sheets and pairs are written under
captures/<cell>/ (git ignored: street-view photos may show faces and plates) and are never sent anywhere but this session.
Rules: aidlc-docs/construction/u4-judgement-corrections/functional-design/business-rules.md (BR-1, BR-2, BR-7, BR-8.3)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

import common
import db
import judgement
import layout
import review

MAX_PIXELS = 50_000_000  # N-U4-7: a bigger image is refused before it is unpacked (checked here: Pillow's own limit is a global other scripts set)
MAX_CAPTURE_BYTES = 20_000_000
MAX_RECORD_BYTES = 2_000_000
PAIR_TILE = (640, 480)
PAIR_HEADER = 56
BUILD_DIR = "data/build"


def safe_name(building_id: str) -> str:
    """A file name for a building id (the allowed characters never contain a path separator; `:` is not good in file names)."""
    if not judgement.is_building_id(building_id):
        raise ValueError(f"not a usable building id: {building_id[:40]!r}")
    return building_id.replace(":", "_")


def inside(base: Path, relative: str) -> Path:
    """base/relative, refused when it leads out of base."""
    path = (base / relative).resolve()
    if base.resolve() not in path.parents:
        raise ValueError(f"path leaves {base}: {relative[:60]!r}")
    return path


def open_image(path: Path) -> Image.Image:
    """Open an image after looking at its size only; refuse one with too many pixels."""
    im = Image.open(path)
    if im.width * im.height > MAX_PIXELS:
        im.close()
        raise ValueError(f"image has more than {MAX_PIXELS} pixels")
    return im


def font(size: int):
    return ImageFont.load_default(size=size)


# --- what is known about a cell ----------------------------------------------------------------------------

def cell_views(conn, cell_id: str) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    """Cropped views per building (with their panorama) and the ids of school buildings (those pictured face by face)."""
    by: dict[str, list[dict[str, Any]]] = {}
    school: set[str] = set()
    for v in db.views_with_heading(conn, cell_id):
        if v["status"] == "cropped" and v["crop_path"] and v["heading_deg"] is not None:
            by.setdefault(v["building_id"], []).append(v)
            if v["face_deg"] is not None:
                school.add(v["building_id"])
    return by, school


def ok_buildings(conn, cell_id: str) -> list[dict[str, Any]]:
    return [b for b in db.rows_in_cells(conn, "buildings", [cell_id]) if b["status"] == "ok"]


# --- pending: the blind list and the sheet images (BR-1) -----------------------------------------------------------

def pending_jobs(conn, cfg: Mapping[str, Any], cell_id: str, limit: int, redo: Sequence[str] = ()) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The next buildings to judge as blind items (no register or OSM numbers) and the counts of what is left."""
    frame = layout.Frame.from_cfg(cfg)
    buildings = ok_buildings(conn, cell_id)
    views, school = cell_views(conn, cell_id)
    judged = {e["building_id"] for e in db.estimates_in_cell(conn, cell_id)}
    with_photos = [b for b in buildings if b["building_id"] in views]
    order = review.pending_order(with_photos, school)
    again = set(redo)
    todo = [i for i in order if i not in judged or i in again]
    by_id = {b["building_id"]: b for b in with_photos}
    items = []
    for bid in todo[:limit]:
        item = review.blind_item(by_id[bid], views[bid], frame)
        item["sheet"] = f"{cell_id}/sheets/{safe_name(bid)}.jpg"
        items.append(item)
    return items, {"remaining": len(todo) - len(items), "no_photo": len(buildings) - len(with_photos), "judged": len(judged)}


def make_sheet(tiles: Sequence[tuple[str, Path]], cfg: Mapping[str, Any]) -> Image.Image:
    """Up to six crops as a two-column grid, each tile shrunk to sheet_tile_w x sheet_tile_h and labeled with its rank and direction."""
    w, h = cfg["sheet_tile_w"], cfg["sheet_tile_h"]
    sheet = Image.new("RGB", (2 * w, h * math.ceil(len(tiles) / 2)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (label, path) in enumerate(tiles):
        with open_image(path) as im:
            tile = im.convert("RGB").resize((w, h))
        x, y = (i % 2) * w, (i // 2) * h
        sheet.paste(tile, (x, y))
        draw.rectangle((x, y, x + 8 * len(label) + 14, y + 26), fill="black")
        draw.text((x + 6, y + 3), label, fill="white", font=font(18))
    return sheet


def write_sheets(conn, cfg: Mapping[str, Any], cell_id: str, items: Sequence[dict[str, Any]]) -> list[str]:
    """Write the sheet image of every item. Returns warnings (a missing crop file leaves its tile out)."""
    captures = common.resolve(cfg["captures_dir"])
    views, _ = cell_views(conn, cell_id)
    warnings = []
    for item in items:
        tiles = []
        for item_view in item["views"][:cfg["school_max_views"]]:
            row = next(v for v in views[item["building_id"]] if v["rank"] == item_view["rank"])
            path = inside(captures, row["crop_path"])
            if path.is_file():
                tiles.append((f"#{item_view['rank']} {item_view['facing']}", path))
            else:
                warnings.append(f"{item['building_id']}: crop file {row['crop_path']} is missing")
        if not tiles:
            warnings.append(f"{item['building_id']}: no crop file is readable, no sheet")
            continue
        target = inside(captures, item["sheet"])
        target.parent.mkdir(parents=True, exist_ok=True)
        make_sheet(tiles, cfg).save(target, "JPEG", quality=cfg["sheet_jpeg_quality"])
    return warnings


# --- record: judgements in (BR-2) ----------------------------------------------------------------------------------------

def read_judgements(path: str) -> list[Any]:
    raw = sys.stdin.read(MAX_RECORD_BYTES + 1) if path == "-" else Path(path).read_text(encoding="utf-8")
    if len(raw.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("judgement file is too large")
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"judgement file is not valid JSON: {e}") from None
    if not isinstance(data, list):
        raise ValueError("judgement file must hold a list of judgements")
    return data


def record(conn, cfg: Mapping[str, Any], judgements: Sequence[Mapping[str, Any]]) -> int:
    """Store the judgements and refresh the export file of every cell they belong to. Prints nothing about the register (BR-2.4)."""
    count = db.record_judgements(conn, cfg, judgements, common.now_iso())
    cells = {db.building_cell(conn, j["building_id"]) for j in judgements}
    for cell in sorted(c for c in cells if c):
        db.export_cell(conn, cell, common.resolve(cfg["overrides_dir"]))
    return count


# --- report: after judging (S4-2) ------------------------------------------------------------------------------------------

def report_lines(conn, cfg: Mapping[str, Any], cell_id: str) -> list[str]:
    eff = db.effective_buildings(conn, cfg, cell_id)
    views, _ = cell_views(conn, cell_id)
    status = Counter(e.floors_status for e in eff)
    basis = Counter(e.height_basis for e in eff)
    flags = Counter(f for e in eff for f in e.flags)
    agree = review.agreement(((e.building_id, e.register_floors, e.photo_floors, e.photo_confidence) for e in eff), cfg["blind_broken"])
    lines = [f"cell {cell_id}: {len(eff)} buildings, {len(eff) - status['unjudged']} judged, {status['unjudged']} not judged yet, "
             f"{sum(1 for e in eff if e.building_id not in views)} without photos",
             "floors status: " + ", ".join(f"{k} {status[k]}" for k in sorted(status)),
             "height basis: " + ", ".join(f"{k} {basis[k]}" for k in sorted(basis)),
             "review flags: " + (", ".join(f"{k} {flags[k]}" for k in judgement.FLAGS if flags[k]) or "none")]
    if agree["compared"]:
        per = ", ".join(f"{k} {s['agree']}/{s['compared']}" for k, s in agree["by_confidence"].items())
        lines.append(f"photo count agrees with the register on {agree['agree']} of {agree['compared']} buildings "
                     f"({agree['rate']:.0%}); by confidence: {per}; left out as blind-broken: {agree['excluded']}")
    else:
        lines.append("photo count vs register: no building has both yet")
    lines.append("review list:")
    lines += [f"  {e.building_id}  {','.join(e.flags)}" for e in eff if e.flags and e.flags != ("unjudged",)] or ["  (empty)"]
    return lines


# --- plan and compose: the comparison pairs (BR-7) --------------------------------------------------------------------------

def plan_cell(conn, cfg: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    """Batches of comparison pairs with the Studio camera for each (no files, same input gives the same plan)."""
    frame = layout.Frame.from_cfg(cfg)
    eff = db.effective_buildings(conn, cfg, cell_id)
    views, school = cell_views(conn, cell_id)
    by_id = {e.building_id: e for e in eff}
    batches = []
    pictured = [e for e in eff if e.building_id in views]  # a building without a crop has nothing to compare with
    for number, ids in enumerate(review.review_batches(pictured, school, cfg["review_batch_size"]), 1):
        pairs = []
        for bid in ids:
            e = by_id[bid]
            chosen = sorted(views.get(bid, []), key=lambda v: v["rank"])
            chosen = chosen if bid in school else chosen[:1]
            for v in chosen:
                pairs.append({
                    "key": f"{bid}__{v['rank']}", "building_id": bid, "rank": v["rank"],
                    "camera": review.camera_for_view(frame, v["pano_lat"], v["pano_lon"], v["heading_deg"], v["yaw_deg"],
                                                     v["pitch_deg"], cfg["camera_height_m"]),
                    "crop_fov_h_deg": v["fov_deg"], "crop": v["crop_path"], "file": f"{safe_name(bid)}__{v['rank']}.jpg",
                    "label": {"floors": e.floors_above, "floors_basis": e.floors_basis, "height_m": round(e.height_m, 1),
                              "height_basis": e.height_basis, "wall_color": e.wall_color, "flags": list(e.flags)}})
        batches.append({"number": number, "pairs": pairs})
    return {"cell_id": cell_id, "studio_fov_v_deg": round(review.STUDIO_FOV_V_DEG, 2), "batch_size": cfg["review_batch_size"],
            "pairs": sum(len(b["pairs"]) for b in batches), "batches": batches}


def label_lines(pair: Mapping[str, Any]) -> list[str]:
    lab = pair["label"]
    floors = f"{lab['floors']} floors ({lab['floors_basis']})" if lab["floors"] is not None else "floors unknown"
    return [f"{pair['building_id']}  view {pair['rank']}   left: Studio   right: street view",
            f"{floors}, {lab['height_m']} m ({lab['height_basis']}), wall {lab['wall_color']}"
            + (f", review: {'-'.join(lab['flags'])}" if lab["flags"] else "")]


def compose_pair(capture: Path, crop: Path, pair: Mapping[str, Any]) -> Image.Image:
    """The Studio capture (cut to the crop's angle) next to the crop, under a label strip (BR-7.5)."""
    if not capture.is_file() or capture.stat().st_size > MAX_CAPTURE_BYTES:
        raise ValueError("capture is not a file or is larger than 20 MB")
    with open_image(capture) as shot:
        box = review.capture_crop_box(shot.width, shot.height, pair["crop_fov_h_deg"])
        left = shot.convert("RGB").crop(box).resize(PAIR_TILE)
    with open_image(crop) as photo:
        right = photo.convert("RGB").resize(PAIR_TILE)
    out = Image.new("RGB", (2 * PAIR_TILE[0], PAIR_TILE[1] + PAIR_HEADER), "white")
    out.paste(left, (0, PAIR_HEADER))
    out.paste(right, (PAIR_TILE[0], PAIR_HEADER))
    draw = ImageDraw.Draw(out)
    for n, line in enumerate(label_lines(pair)):
        draw.text((8, 4 + 24 * n), line, fill="black", font=font(18))
    return out


def compose(cfg: Mapping[str, Any], cell_id: str, captures_file: str) -> tuple[list[str], list[str]]:
    """Make the pair images of the captures listed in the file ({key: capture path}). Returns (files made, warnings)."""
    plan = json.loads((common.resolve(BUILD_DIR) / cell_id / "review.json").read_text(encoding="utf-8"))
    pairs = {p["key"]: p for b in plan["batches"] for p in b["pairs"]}
    mapping = json.loads(Path(captures_file).read_text(encoding="utf-8"))
    if not (isinstance(mapping, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items())):
        raise ValueError("captures file must map pair keys to capture file paths")
    captures = common.resolve(cfg["captures_dir"])
    made, warnings = [], []
    for key, path in sorted(mapping.items()):
        pair = pairs.get(key)
        if pair is None:
            warnings.append(f"{key[:60]}: not a pair of the plan, skipped")
            continue
        try:
            target = inside(captures, f"{cell_id}/review/{pair['file']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            compose_pair(Path(path), inside(captures, pair["crop"]), pair).save(target, "JPEG", quality=cfg["sheet_jpeg_quality"])
            made.append(f"{cell_id}/review/{pair['file']}")
        except (ValueError, OSError) as e:  # a capture that does not fit (too narrow, not an image, missing): skip it, say why
            warnings.append(f"{key}: {e}")
    return made, warnings


# --- command line -----------------------------------------------------------------------------------------------------------------

def cell_arg(text: str) -> str:
    if not judgement.CELL_RE.fullmatch(text):
        raise argparse.ArgumentTypeError(f"not an H3 cell id: {text[:40]!r}")
    return text


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="estimate.py", description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true", help="check that the libraries import; touches nothing")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("pending", help="blind list and sheet images of the next buildings to judge")
    p.add_argument("--cells", nargs=1, required=True, type=cell_arg, metavar="ID")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--redo", nargs="*", default=[], metavar="ID", help="judge these buildings again")
    r = sub.add_parser("record", help="store judgements from a JSON list")
    r.add_argument("--file", required=True, help="a file, or - for standard input")
    for name, text in (("report", "statuses, agreement with the register and the review list (after judging)"),
                       ("plan", "Studio camera values of the comparison pairs"), ):
        c = sub.add_parser(name, help=text)
        c.add_argument("--cells", nargs=1, required=True, type=cell_arg, metavar="ID")
    c = sub.add_parser("compose", help="put Studio captures next to their street-view crops")
    c.add_argument("--cells", nargs=1, required=True, type=cell_arg, metavar="ID")
    c.add_argument("--captures", required=True, help='JSON file: {"<building id>__<rank>": "<capture path>"}')
    ns = parser.parse_args(list(argv))
    if not ns.selftest and not ns.command:
        parser.error("a command is required (pending, record, report, plan, compose) or --selftest")
    if ns.command == "pending" and not 1 <= ns.limit <= 200:
        parser.error("--limit must be from 1 to 200")
    if ns.command == "pending":
        bad = [i for i in ns.redo if not judgement.is_building_id(i)]
        if bad:
            parser.error(f"--redo: not building ids: {bad}")
    return ns


def main(cfg: dict[str, Any]) -> int:
    args = parse_args(sys.argv[1:])
    if args.selftest:
        print("selftest ok: pillow, h3 and shapely import")
        return 0
    conn = db.connect(common.resolve(cfg["db_path"]))
    started = common.now_iso()
    cell = args.cells[0] if getattr(args, "cells", None) else None
    try:
        counts = run_command(conn, cfg, args, cell)
    except (ValueError, OSError) as e:  # a refused call: say why; nothing was changed
        message = common.mask(f"{type(e).__name__}: {e}")
        common.log(logging.ERROR, f"refused: {message}", cell)
        print(f"refused: {message}", file=sys.stderr)
        return 1
    db.record_run(conn, cell_id=cell, unit="C4", started_at=started, finished_at=common.now_iso(), status="ok",
                  counts={"command": args.command, **counts})
    common.log(logging.INFO, f"{args.command} done", cell, **counts)
    return 0


def run_command(conn, cfg: dict[str, Any], args: argparse.Namespace, cell: str | None) -> dict[str, int]:
    if args.command == "pending":
        items, left = pending_jobs(conn, cfg, cell, args.limit, args.redo)
        warnings = write_sheets(conn, cfg, cell, items)
        for item in items:
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
        for w in warnings:
            common.log(logging.WARNING, w, cell)
        print(f"# {len(items)} listed, {left['remaining']} more to judge, {left['no_photo']} buildings without photos, "
              f"{left['judged']} judged so far")
        return {"listed": len(items), **left, "warnings": len(warnings)}
    if args.command == "record":
        n = record(conn, cfg, read_judgements(args.file))
        print(f"recorded {n} judgements")
        return {"recorded": n}
    if args.command == "report":
        for line in report_lines(conn, cfg, cell):
            print(line)
        return {"reported": 1}
    if args.command == "plan":
        plan = plan_cell(conn, cfg, cell)
        folder = common.resolve(BUILD_DIR) / cell
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "review.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"plan: {plan['pairs']} pairs in {len(plan['batches'])} batches -> {folder / 'review.json'}; "
              f"set Studio's field of view to {plan['studio_fov_v_deg']} degrees and capture with camera_position and look_at_position")
        return {"pairs": plan["pairs"], "batches": len(plan["batches"])}
    made, warnings = compose(cfg, cell, args.captures)
    for f in made:
        print(f"pair: {f}")
    for w in warnings:
        common.log(logging.WARNING, w, cell)
    print(f"# {len(made)} pairs made, {len(warnings)} skipped")
    return {"made": len(made), "warnings": len(warnings)}


if __name__ == "__main__":
    common.run_cli(main, "estimate")
