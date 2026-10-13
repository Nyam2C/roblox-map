# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""C6: turn one cell's buildings and streets into Luau chunk files for the Studio builder.

Usage:
  uv run src/build_luau.py --cells 8930e0af13bffff [...]    # writes data/build/<cell>/chunk-NNN.luau, chunks.json and manifest.json
  uv run src/build_luau.py --selftest                       # import check only

Studio fetches chunks.json (the chunk files as data) through the Studio MCP (execute_luau); see studio/ServerStorage/MapBuilder.luau.
All geometry is computed in layout.py. Text that goes into Luau code is limited to a safe character set (SEC2).
Rules: aidlc-docs/construction/u2-studio-builder/functional-design/business-rules.md
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import h3

import common
import db
import details_rules
import judgement
import layout
import layout_details
import streets

BUILD_DIR = "data/build"
CHUNK_WARN_BYTES = 15_000  # U2 NFR P3, raised in U5 (BR-14.6): a bigger chunk file means chunk_size should come down
SAFE_TEXT = re.compile(r"[A-Za-z0-9:#_.\-]{1,100}")  # N-U2-4: the only characters that may reach Luau code
TEXT_ATTRS = ("name", "Source", "HeightBasis", "FloorsBasis", "WallColor", "Review")  # the texts of a building item that become code
ITEM_TEXTS = ("owner", "shape", "material", "color_name", "ink", "faces")  # U5 texts of any item; `text` goes through sign_string


# --- Luau text (SEC2) -------------------------------------------------------------------------------

def luau_string(text: str) -> str:
    """A Luau string literal. The allowed characters never need escaping, anything else is refused."""
    if not isinstance(text, str) or not SAFE_TEXT.fullmatch(text):
        raise ValueError(f"text not allowed in Luau code: {str(text)[:40]!r}")
    return f'"{text}"'


def luau_number(v: float) -> str:
    """Fixed notation, three decimals at most, no exponent and no -0 (BR-7.4). Only finite numbers."""
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
        raise ValueError(f"not a finite number: {v!r}")
    text = format(v, ".3f").rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def item_literal(item: layout.Item, cell_id: str) -> str:
    """One item as a Luau table. Keys: k kind, n name, x y z center, w h d size (local X, Y, Z), r yaw; buildings add
    s source, e height in m, q fit ratio, f floors, and from U4 b height basis, a floors basis, c wall color name,
    v review flags. U5 adds, only when they differ from the defaults (BR-14.2): i owner, p shape, m material, c color name
    (any kind), o ink, t sign text, u="LR" two-sided, md sign MaxDistance (x is the position), im sign image asset id (SI-6),
    j reflectance, g shadow, l collide.
    BuildingId and CellId are not sent: Builder takes them from n (or i) and the cell."""
    parts = [f"k={luau_string(item.kind)}", f"n={luau_string(item.name)}", f"x={luau_number(item.cx)}", f"y={luau_number(item.cy)}",
             f"z={luau_number(item.cz)}", f"w={luau_number(item.sx)}", f"h={luau_number(item.sy)}", f"d={luau_number(item.sz)}",
             f"r={luau_number(item.yaw_deg)}"]
    if item.kind == "building":
        a = item.attrs
        if a["CellId"] != cell_id or a["BuildingId"] != (item.owner or item.name):
            raise ValueError(f"building {item.name} does not belong to cell {cell_id}")
        parts += [f"s={luau_string(a['Source'])}", f"e={luau_number(a['HeightM'])}", f"q={luau_number(a['FitRatio'])}"]
        if "Floors" in a:
            parts.append(f"f={int(a['Floors'])}")
        for key, attr in (("b", "HeightBasis"), ("a", "FloorsBasis"), ("c", "WallColor"), ("v", "Review")):
            if attr in a:
                parts.append(f"{key}={luau_string(a[attr])}")
    elif item.color_name:
        parts.append(f"c={luau_string(item.color_name)}")
    if item.owner and item.owner != item.name:
        parts.append(f"i={luau_string(item.owner)}")
    if item.shape != "Block":
        if item.shape not in details_rules.SHAPES:
            raise ValueError(f"not a part shape: {item.shape!r}")
        parts.append(f"p={luau_string(item.shape)}")
    if item.material != layout.LOOKS[item.kind][0]:
        if item.material not in details_rules.MATERIALS:
            raise ValueError(f"not a Roblox material: {item.material!r}")
        parts.append(f"m={luau_string(item.material)}")
    if item.kind == "sign":
        parts.append(f"t={details_rules.sign_string(item.text)}")
        parts.append(f"o={luau_string(item.ink or 'ink_black')}")
        if item.faces == "LR":
            parts.append('u="LR"')
        if "MaxDistance" in item.attrs:
            parts.append(f"md={int(item.attrs['MaxDistance'])}")
        if "ImageAsset" in item.attrs:  # SI-6: a generated sign image, by Roblox asset id (a number, never text)
            asset = item.attrs["ImageAsset"]
            if not isinstance(asset, int) or isinstance(asset, bool) or not 0 < asset < 2 ** 53:
                raise ValueError(f"not a Roblox asset id: {asset!r}")
            if item.faces == "LR":
                raise ValueError(f"{item.name}: a two-sided sign cannot carry an image")
            parts.append(f"im={asset}")
    if item.reflectance:
        parts.append(f"j={luau_number(item.reflectance)}")
    default_shadow, default_collide = layout.KIND_DEFAULTS[item.kind]
    if item.shadow is not None and item.shadow != default_shadow:
        parts.append(f"g={1 if item.shadow else 0}")
    if item.collide is not None and item.collide != default_collide:
        parts.append(f"l={1 if item.collide else 0}")
    return "{" + ",".join(parts) + "}"


def render_chunk(cell_id: str, number: int, total: int, items: Sequence[layout.Item]) -> str:
    """The Luau code of one chunk. The first chunk starts the cell, the last one finishes it and returns the counts (BR-7.3)."""
    looks = ",".join(f"{kind}={{{luau_string(m)},{r},{g},{b}}}" for kind, (m, (r, g, b)) in sorted(layout.LOOKS.items()))
    walls = {i.attrs["WallColor"]: i.color for i in items if i.kind == "building" and "WallColor" in i.attrs}
    walls.update({i.color_name: i.color for i in items if i.color_name and i.kind != "building"})  # U5: every color name of the chunk
    walls.update({i.ink: details_rules.PALETTE[i.ink] for i in items if i.kind == "sign" and i.ink})
    if walls:  # the colors this chunk's items use, sent once per chunk
        looks += ",walls={" + ",".join(f"[{luau_string(k)}]={{{c[0]},{c[1]},{c[2]}}}" for k, c in sorted(walls.items())) + "}"
    lines = [f"-- chunk {number}/{total} of cell {cell_id}: generated by build_luau.py, do not edit",
             'local Builder = require(game:GetService("ServerStorage"):WaitForChild("MapBuilder"))',
             f"local CELL = {luau_string(cell_id)}", "local LOOKS = {" + looks + "}", "local ITEMS = {"]
    lines += [f"\t{item_literal(i, cell_id)}," for i in items]
    lines.append("}")
    if number == 1:
        lines.append("Builder.begin(CELL)")
    lines.append("local added = Builder.add(CELL, ITEMS, LOOKS)")
    lines.append("return Builder.finish(CELL)" if number == total else "return added")
    return "\n".join(lines) + "\n"


# --- the plan for one cell ------------------------------------------------------------------------------

@dataclass
class Plan:
    cell_id: str
    items: list[layout.Item]
    files: dict[str, str]  # file name -> text, chunk files and manifest.json
    counts: dict[str, Any]
    warnings: list[str]


def _texts_ok(item: layout.Item) -> bool:
    texts = [item.name] + [str(item.attrs[k]) for k in TEXT_ATTRS if k in item.attrs] + \
        [str(getattr(item, f)) for f in ITEM_TEXTS if getattr(item, f)]
    return all(SAFE_TEXT.fullmatch(v) for v in texts) and (item.kind != "sign" or bool(details_rules.SIGN_TEXT.fullmatch(item.text or "")))


def plan_cell(cell_id: str, buildings: Sequence[Mapping[str, Any]], features: Sequence[Mapping[str, Any]],
              cfg: Mapping[str, Any], estimates: Mapping[str, Mapping[str, Any]] | None = None,
              overrides: Mapping[str, Mapping[str, Any]] | None = None,
              details: Mapping[str, Mapping[str, Any]] | None = None, sign_assets: Mapping[str, int] | None = None,
              sat_trees: Sequence[Sequence[float]] | None = None) -> Plan:
    """Items, chunks and the manifest for one cell. No database and no files: the same input always gives the same text (P2-8, P5-1).

    Height, floors and wall color of a building are its final value: override > photo judgement > register > default (U4 BR-9).
    U5: duplicate outlines are dropped, bodies get boxes, roofs, bands, windows, facade elements, yards and signs from the
    merged details (judged > note > default), streets get pieces, markings, crosswalks and props (U5 BR-1 to BR-11).
    """
    frame, res = layout.Frame.from_cfg(cfg), cfg["h3_res"]
    estimates, overrides, details = estimates or {}, overrides or {}, details or {}
    warnings: list[str] = []
    items = [layout.ground_item(cell_id, frame, cfg)]
    kept, dropped = layout_details.dedupe_buildings(buildings, frame)
    names: dict[str, str] = {}
    judged = 0
    bodies: list[tuple[layout_details.Body, Mapping[str, Any], Any]] = []
    for b in kept:
        bid = str(b["building_id"])
        eff = judgement.effective_building(b, estimates.get(bid), overrides.get(bid), cfg)
        outline = b["outline"]
        if not (isinstance(outline, (list, tuple)) and len(outline) >= 3
                and all(isinstance(p, (list, tuple)) and len(p) == 2 and layout._finite(p[0], p[1]) for p in outline)):
            warnings.append(f"{bid}: outline has fewer than 3 usable points")
            continue
        detail = details.get(bid)
        note = (estimates.get(bid) or {}).get("note")
        try:
            body = layout_details.make_body(b, eff, detail, note, frame, cfg)
        except (ValueError, TypeError) as e:
            warnings.append(f"{bid}: {e}")
            continue
        if body is None:
            warnings.append(f"{bid}: outline has no area")
            continue
        bodies.append((body, b, eff))
    # facing, occlusion
    lines = layout_details._feature_lines(features, frame, cfg)
    all_polys = {body.building_id: [layout_details._box_poly(bx) for bx in body.boxes] for body, _, _ in bodies}
    resolved: list[tuple[layout_details.Body, Mapping[str, Any], Any]] = []
    no_facing, far_facing = [], []
    for body, b, eff in bodies:
        others = [p for oid, ps in all_polys.items() if oid != body.building_id for p in ps]
        body = layout_details.resolve_body(body, lines, others, cfg)
        if body.is_body and body.facing is None:
            no_facing.append(body.building_id)
        if body.far:
            far_facing.append(body.building_id)
        resolved.append((body, b, eff))
    # building items
    signs = labels = 0
    details_used = 0
    building_ids: list[str] = []
    boxes_report = []
    for body, b, eff in resolved:
        group: list[layout.Item] = layout_details.box_items(body, b, eff, frame)
        body_warnings = list(body.warnings)
        if body.is_body:
            for bi in range(len(body.boxes)):
                group += layout_details.roof_items(body, bi, frame, cfg)
                group += layout_details.body_items(body, bi, frame, cfg, body_warnings)
            group += layout_details.front_items(body, frame, cfg, body_warnings)
            group += layout_details.yard_items(body, frame, cfg)
            sign_list, n_labels = layout_details.sign_items(body, frame, cfg, body_warnings)
            group += sign_list
        if not all(_texts_ok(i) for i in group):
            warnings.append(f"{body.building_id}: id, source or a value has characters that are not allowed in Luau code")
            continue
        warnings += body_warnings
        items += group
        signs += sum(1 for i in group if i.kind == "sign")
        labels += n_labels if body.is_body else 0
        building_ids.append(body.building_id)
        for name in body.names:
            names[name] = b.get("name") or ""
        judged += int(body.building_id in estimates)
        details_used += int(body.building_id in details and body.is_body)
        if len(body.boxes) > 1:
            area = layout_details._poly_m(b["outline"], frame).area
            boxes_report.append({"building_id": body.building_id, "boxes": len(body.boxes),
                                 "fit_ratio": layout.fmt(min(1.0, area / sum(bx.width_m * bx.depth_m for bx in body.boxes)))})
    # streets
    pieces: list[layout.Item] = []
    ok_features = []
    for f in sorted(features, key=lambda f: str(f["feature_id"])):
        if f["kind"] not in ("road", "path"):
            continue
        if not SAFE_TEXT.fullmatch(str(f["feature_id"])):
            warnings.append(f"{f['feature_id']}: id has characters that are not allowed in Luau code")
            continue
        ok_features.append(f)
        pieces += layout.road_items(f, frame, cell_id, res, cfg)
    lines = streets.streets_of(ok_features, frame, cell_id, res, cfg)
    jcts = streets.junctions(lines, frame, cell_id, res, cfg)
    sidewalks, props = streets.street_items(lines, jcts, frame, cfg, rule_trees=sat_trees is None)
    if sat_trees is not None:  # trees read off the satellite photo replace the rule-based street trees (BR-11.4a)
        props = props + streets.tree_items(frame, sat_trees)
    items += pieces + sidewalks + props
    spawn, spawn_warnings = layout.spawn_item(cell_id, frame, cfg, pieces)
    if spawn is not None:
        items.append(spawn)
    warnings += spawn_warnings
    if cfg.get("spawn_lat") is None:
        warnings.append("no spawn point configured (spawn_lat, spawn_lon): no spawn is built")
    sign_images = 0
    for i in items:  # SI-6: band and floor signs whose image was made and uploaded get the asset id; the text stays as the fallback
        if i.kind == "sign" and sign_assets and i.text and i.color_name and i.ink:
            tail = details_rules.sign_tail(i.name)
            if tail in details_rules.SIGN_IMAGE_TAILS:
                asset = sign_assets.get(details_rules.sign_image_key(i.text, tail, i.color_name, i.ink, details_rules.aspect_bucket(i.sx, i.sy)))
                if asset is not None:
                    i.attrs["ImageAsset"] = int(asset)
                    sign_images += 1
    items = layout.order_items(items)
    chunks = layout.chunk_items(items, cfg["chunk_size"])
    files = {f"chunk-{n:03d}.luau": render_chunk(cell_id, n, len(chunks), c) for n, c in enumerate(chunks, 1)}
    for name, text in files.items():
        if len(text.encode()) > CHUNK_WARN_BYTES:
            warnings.append(f"{name} is {len(text.encode()) / 1000:.1f} KB: lower chunk_size so each Studio call stays small")
    by_kind = {k: sum(1 for i in items if i.kind == k) for k in layout.ORDER}
    poor_fit = [{"building_id": i.name, "name": names[i.name], "fit_ratio": i.attrs["FitRatio"]}
                for i in items if i.kind == "building" and i.attrs["FitRatio"] < cfg["poor_fit_ratio"]]
    counts = {"items": len(items), "chunks": len(chunks), **{f"items_{k}": v for k, v in by_kind.items()},
              "buildings_in": len(buildings), "buildings_built": len(building_ids), "duplicates_dropped": len(dropped),
              "buildings_skipped": len(buildings) - len(building_ids) - len(dropped),
              "streets_in": sum(1 for f in features if f["kind"] in ("road", "path")), "junctions": sum(1 for j in jcts if j.owned),
              "poor_fit": len(poor_fit), "warnings": len(warnings), "judged": judged, "details_used": details_used,
              "flagged": sum(1 for i in items if i.kind == "building" and "Review" in i.attrs),
              "signs": signs, "labels": labels, "sign_images": sign_images, "parts_total": len(items), "boxes": len(boxes_report),
              "no_facing": len(no_facing), "far_facing": len(far_facing)}
    manifest = {"cell_id": cell_id, "counts": counts, "poor_fit": poor_fit, "warnings": warnings, "boxes": boxes_report,
                "building_ids": building_ids, "duplicates_dropped": [list(d) for d in dropped], "no_facing": no_facing, "far_facing": far_facing,
                "files": {n: len(t.encode()) for n, t in sorted(files.items())},
                "config": {k: cfg[k] for k in ("origin_lat", "origin_lon", "studs_per_m", "chunk_size", "poor_fit_ratio",
                                                "ground_margin_m", "sidewalk_width_m", "spawn_lat", "spawn_lon", "spawn_yaw_deg",
                                                "pole_spacing_m", "lamp_spacing_m", "tree_spacing_m", "car_spacing_m", "school_zone_m",
                                                "roof_pitch_deg", "window_faces")}}
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    files["chunks.json"] = chunks_json(cell_id, [files[n] for n in sorted(files) if n.startswith("chunk-")], building_ids)
    return Plan(cell_id, items, files, counts, warnings)


PAIR = re.compile(r'(\w+)=("([^"]*)"|-?\d+(?:\.\d+)?)')


def chunks_json(cell_id: str, chunk_texts: Sequence[str], building_ids: Sequence[str]) -> str:
    """The chunk files as data (chunks.json) for the Studio HttpService path: read back from the Luau text, so both say the same."""
    def table(body: str) -> dict[str, Any]:
        return {k: s if raw.startswith('"') else (float(raw) if "." in raw else int(raw)) for k, raw, s in PAIR.findall(body)}
    chunks, counts = [], {}
    for text in chunk_texts:
        looks_line = next(line for line in text.splitlines() if line.startswith("local LOOKS = "))
        looks: dict[str, Any] = {kind: [m, int(r), int(g), int(b)] for kind, m, r, g, b in re.findall(r'(\w+)=\{"(\w+)",(\d+),(\d+),(\d+)\}', looks_line)}
        wpart = looks_line.split("walls={", 1)
        looks["walls"] = {name: [int(r), int(g), int(b)] for name, r, g, b in re.findall(r'\["([^"]+)"\]=\{(\d+),(\d+),(\d+)\}', wpart[1])} if len(wpart) == 2 else {}
        items = [table(line.strip()[1:-2]) for line in text.splitlines() if line.startswith("\t{")]
        for it in items:
            counts[it["k"]] = counts.get(it["k"], 0) + 1
        chunks.append({"looks": looks, "items": items})
    return json.dumps({"cell_id": cell_id, "chunks": chunks, "counts": counts, "building_ids": list(building_ids)}, ensure_ascii=False)


def write_plan(plan: Plan, root: Path) -> list[Path]:
    """Write the files of one cell to root/<cell>/. Chunk files of an earlier run that are no longer needed are removed."""
    folder = root / plan.cell_id
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("chunk-*.luau"):
        old.unlink()
    paths = []
    for name, text in sorted(plan.files.items()):
        path = folder / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


SIGN_KEY_RE = re.compile(r"[0-9a-f]{16}")


def load_sign_assets(path: Path) -> dict[str, int]:
    """signs.json of a cell -> {sign image key: Roblox asset id}. No file means text signs everywhere (SI-9); a bad entry refuses the build."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("signs") if isinstance(data, dict) else None
    if not isinstance(rows, dict):
        raise ValueError(f"{path.name}: not a sign asset file")
    out: dict[str, int] = {}
    for key, row in rows.items():
        asset = row.get("asset_id") if isinstance(row, dict) else None
        if not (isinstance(key, str) and SIGN_KEY_RE.fullmatch(key) and isinstance(asset, int) and not isinstance(asset, bool) and 0 < asset < 2 ** 53):
            raise ValueError(f"{path.name}: bad sign asset entry {str(key)[:20]!r}")
        out[key] = asset
    return out


def load_cell_inputs(conn, cell_id: str) -> tuple[list, list, dict, dict, dict]:
    """The database rows plan_cell needs: buildings, road and path features, estimates, overrides, details (also used by signs.py)."""
    buildings = [b for b in db.rows_in_cells(conn, "buildings", [cell_id]) if b["status"] == "ok"]
    if not buildings:
        raise ValueError("no buildings stored for this cell: run register.py first")
    features = [f for f in db.rows_in_cells(conn, "street_features", [cell_id]) if f["kind"] in ("road", "path")]
    estimates = {e["building_id"]: e for e in db.estimates_in_cell(conn, cell_id)}
    return buildings, features, estimates, db.overrides_by_building(conn, cell_id), db.details_by_building(conn, cell_id)


def build_cell(conn, cfg: Mapping[str, Any], cell_id: str, root: Path) -> Plan:
    cfg = common.cell_config(cfg, cell_id)
    buildings, features, estimates, overrides, details = load_cell_inputs(conn, cell_id)
    sign_assets = load_sign_assets(common.cell_file(cfg, cell_id, "signs"))
    sat_trees = streets.load_trees(common.cell_file(cfg, cell_id, "trees"))
    plan = plan_cell(cell_id, buildings, features, cfg, estimates, overrides, details, sign_assets, sat_trees)
    write_plan(plan, root)
    return plan


# --- command line ---------------------------------------------------------------------------------------------

def parse_args(argv: Sequence[str], res: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="build_luau.py", description=__doc__.split("\n")[0])
    parser.add_argument("--cells", nargs="+", metavar="ID", help="H3 cell IDs to build")
    parser.add_argument("--selftest", action="store_true", help="check that the libraries import; touches nothing")
    ns = parser.parse_args(list(argv))
    if ns.selftest:
        return ns
    if not ns.cells:
        parser.error("--cells is required (or use --selftest)")
    bad = [c for c in ns.cells if not (h3.is_valid_cell(c) and h3.get_resolution(c) == res)]
    if bad:
        parser.error(f"not valid resolution-{res} H3 cell IDs: {bad}")
    return ns


def main(cfg: dict[str, Any]) -> int:
    args = parse_args(sys.argv[1:], cfg["h3_res"])
    if args.selftest:
        print("selftest ok: h3 and shapely import")
        return 0
    conn = db.connect(common.resolve(cfg["db_path"]))
    root = common.resolve(BUILD_DIR)
    failed = 0
    for cell_id in args.cells:
        started = common.now_iso()
        try:
            plan = build_cell(conn, cfg, cell_id, root)
            db.record_run(conn, cell_id=cell_id, unit="C6", started_at=started, finished_at=common.now_iso(), status="ok",
                          counts=plan.counts)
            common.log(logging.INFO, "chunk files written", cell_id, **plan.counts)
            for w in plan.warnings:
                common.log(logging.WARNING, w, cell_id)
            common.log(logging.INFO, f"next: Studio fetches {root / cell_id}/chunks.json from 127.0.0.1 (cycle-build studio-build.luau), "
                       "then Builder.verify; ServerStorage/MapBuilder must hold studio/ServerStorage/MapBuilder.luau", cell_id)
        except Exception as e:  # carry on with the next cell
            failed += 1
            message = common.mask(f"{type(e).__name__}: {e}")
            common.log(logging.ERROR, f"cell failed: {message}", cell_id)
            db.record_run(conn, cell_id=cell_id, unit="C6", started_at=started, finished_at=common.now_iso(), status="failed",
                          error=message)
    common.log(logging.INFO, f"done: {len(args.cells) - failed} ok, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    common.run_cli(main, "build_luau")
