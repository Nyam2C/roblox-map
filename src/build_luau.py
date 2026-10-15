# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0", "numpy==2.5.4", "scipy==1.18.1"]
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
import dataclasses
import json
import logging
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import h3
from shapely.geometry import Point
from shapely.ops import unary_union

import common
import db
import details_rules
import fields
import kits
import lite
import roofs
import judgement
import layout
import layout_details
import streets
import bridges
import terrain
import tiers

BUILD_DIR = "data/build"
CELL_PART_BUDGET = 15_000  # parts per cell (architecture.md section 5)
SIGN_REUSE_ASPECT = math.log(1.12)  # U7 K: a reused image may be stretched by 12 % at most
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
    j reflectance, tr transparency, g shadow, l collide; U7 kt kit mesh name.
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
    if item.kit is not None:  # U7 H: a kit mesh cloned from ServerStorage/Kits
        if item.kit not in kits.MESH_IDS:
            raise ValueError(f"not a kit: {item.kit!r}")
        parts.append(f"kt={luau_string(item.kit)}")
    if item.tilt_x:
        parts.append(f"ax={luau_number(item.tilt_x)}")
    if item.tilt_z:
        parts.append(f"az={luau_number(item.tilt_z)}")
    if item.reflectance:
        parts.append(f"j={luau_number(item.reflectance)}")
    if item.transparency:
        if not 0 < item.transparency < 1:
            raise ValueError(f"{item.name}: transparency must be between 0 and 1")
        parts.append(f"tr={luau_number(item.transparency)}")
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


EMPTY_NOTE = re.compile(r"no building|no clear building|trees only|only (?:park )?trees|park trees|vacant|empty lot|nothing", re.I)


def _seen_empty(est: Mapping[str, Any] | None, strict: bool = True) -> bool:
    """A judgement that counted nothing and (strict) said so in its note ("no building"); not strict: any note that says the place is
    empty (trees only, vacant lot), never one that only could not see the target."""
    if not est or est.get("floors_seen") is not None or est.get("height_est_m") is not None:
        return False
    note = str(est.get("note") or "")
    return "no building" in note.lower() if strict else bool(EMPTY_NOTE.search(note))


def plan_cell(cell_id: str, buildings: Sequence[Mapping[str, Any]], features: Sequence[Mapping[str, Any]],
              cfg: Mapping[str, Any], estimates: Mapping[str, Mapping[str, Any]] | None = None,
              overrides: Mapping[str, Mapping[str, Any]] | None = None,
              details: Mapping[str, Mapping[str, Any]] | None = None, sign_assets: Mapping[str, int] | None = None,
              sat_trees: Sequence[Sequence[float]] | None = None, tier: int = 1,
              sign_library: Sequence[Mapping[str, Any]] | None = None, grounds: Sequence[Mapping[str, Any]] | None = None,
              roof_tops: Mapping[str, str] | None = None, under_trees: set[str] | None = None,
              ground: "terrain.Ground | None" = None, decks: "bridges.Decks | None" = None,
              clear: Sequence[Mapping[str, Any]] | None = None, region_roads: Sequence[Mapping[str, Any]] | None = None) -> Plan:
    """Items, chunks and the manifest for one cell. No database and no files: the same input always gives the same text (P2-8, P5-1).

    Height, floors and wall color of a building are its final value: override > photo judgement > register > default (U4 BR-9).
    U5: duplicate outlines are dropped, bodies get boxes, roofs, bands, windows, facade elements, yards and signs from the
    merged details (judged > note > default), streets get pieces, markings, crosswalks and props (U5 BR-1 to BR-11).
    """
    frame, res = layout.Frame.from_cfg(cfg), cfg["h3_res"]
    estimates, overrides, details = estimates or {}, overrides or {}, details or {}
    warnings: list[str] = []
    items = [layout.ground_item(cell_id, frame, cfg)]
    canopies: list[Any] = []
    kept, dropped = layout_details.dedupe_buildings(buildings, frame)
    names: dict[str, str] = {}
    judged = 0
    bodies: list[tuple[layout_details.Body, Mapping[str, Any], Any]] = []
    for b in kept:
        bid = str(b["building_id"])
        if layout.is_underground(b):
            warnings.append(f"{bid}: underground facility (floors below {b.get('floors_below')}, above {b.get('floors_above')}): not built")
            continue
        if bid in (under_trees or ()) and _seen_empty(estimates.get(bid), strict=False):
            # nothing in the register, crowns on the satellite and no building in the photos: an outline left in a park (1ab, 2026-10-14)
            warnings.append(f"{bid}: empty record under the trees and the photos show no building: not built")
            continue
        bare = not (b.get("floors_above") or b.get("height_m") or b.get("usability_code") or b.get("building_area"))
        if (b.get("source") != "gis" or bare) and _seen_empty(estimates.get(bid), strict=b.get("source") != "gis") \
                and not layout_details.is_skybridge(b, (estimates.get(bid) or {}).get("note"), frame):
            # a gis record with no attributes at all and no building in the photos: park furniture outlines (153, 2026-10-15)
            # only OSM has it and the photos show no building: an outline left on a cleared lot (16b, 2026-10-14)
            warnings.append(f"{bid}: {'attribute-less record' if bare and b.get('source') == 'gis' else 'OSM-only outline'} and the photos show no building: not built")
            continue
        canopy = layout_details.canopy_kind(b, (estimates.get(bid) or {}).get("note"))
        if canopy:  # an open canopy over pumps or chargers, not a box (16b, 2026-10-15)
            poly = layout_details._poly_m(b["outline"], frame)
            if poly is not None and any(p.contains(poly.centroid) for p in canopies):
                warnings.append(f"{bid}: a second record of a canopy already built: skipped")
                continue
            canopies.append(poly)
            items += layout_details.canopy_items(b, canopy, frame, cfg)
            warnings.append(f"{bid}: open {canopy} canopy: built on columns")
            continue
        if layout_details.is_skybridge(b, (estimates.get(bid) or {}).get("note"), frame):
            items += layout_details.skybridge_items(b, frame, cfg)
            warnings.append(f"{bid}: elevated footbridge: built as a raised deck")
            continue
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
        if roof_tops and bid in roof_tops:  # the satellite's top colour for the flat-roof cap (roofs.py)
            body = dataclasses.replace(body, details={**body.details, "roof_top": roof_tops[bid]})
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
    # footpaths are drawn only off the road carriageways (2026-10-14); junctions and crosswalks still use the whole path
    region_ways = streets.carriageways(streets.streets_of(list(region_roads), frame, "", 0, cfg)) if region_roads else {}
    own_ids = {str(f["feature_id"]) for f in ok_features}
    extra_roads = [f for f in region_roads or [] if str(f["feature_id"]) not in own_ids]  # cuts this cell's paths too
    for f in streets.paths_off_roads(ok_features + extra_roads, frame, cfg):
        if str(f["feature_id"]).split(".")[0] in own_ids:  # a neighbour's road only cuts, it is built by its own cells
            pieces += layout.road_items(f, frame, cell_id, res, cfg)
    if decks is not None:  # overpasses: a girder and walls under and beside the road of a bridge way (2026-10-15)
        for f in ok_features:
            if str(f["feature_id"]) in decks.fids:
                pieces += bridges.deck_items(f, frame, cell_id, res, cfg)
    lines = streets.streets_of(ok_features, frame, cell_id, res, cfg)
    jcts = streets.junctions(lines, frame, cell_id, res, cfg)
    sidewalks, props = streets.street_items(lines, jcts, frame, cfg, rule_trees=sat_trees is None, region_ways=region_ways)
    entrances = [f for f in sorted(features, key=lambda f: str(f["feature_id"])) if f["kind"] == "subway_entrance" and SAFE_TEXT.fullmatch(str(f["feature_id"]))]
    props = props + streets.entrance_items(entrances, lines, frame, cell_id, res) + streets.ramp_items(lines, frame)
    if sat_trees is not None:  # trees read off the satellite photo replace the rule-based street trees (BR-11.4a)
        # not on a school ground: new dark turf reads as crowns on the photo (중흥중, 2026-10-14)
        # nor on a carriageway: trees.py masks roads by its own width, a widened road (road_lanes_by_name) or a junction keeps them (10b, 2026-10-14)
        ways = unary_union(list({**region_ways, **streets.carriageways(lines)}.values())) if lines or region_ways else None
        props = props + streets.tree_items(frame, [t for t in sat_trees if not any(fields.covers(g, t[0], t[1]) for g in list(grounds or []) + list(clear or []))
                                                   and not (ways is not None and ways.contains(Point(t[0] / frame.studs_per_m, -t[1] / frame.studs_per_m)))])
    for g in grounds or []:  # U7 J: school grounds of fields.json that no Manual script makes
        props = props + fields.field_items(g, frame)
    if decks is not None:  # no crosswalk, stop line or bollard of a junction up on a deck
        props = [p for p in props if p.group in decks.fids or decks.over(p.cx, p.cz) < 1.0]
    items += pieces + sidewalks + props
    spawn, spawn_warnings = layout.spawn_item(cell_id, frame, cfg, pieces)
    if spawn is not None:
        items.append(spawn)
    warnings += spawn_warnings
    if cfg.get("spawn_lat") is None:
        warnings.append("no spawn point configured (spawn_lat, spawn_lon): no spawn is built")
    items, sign_images, signs_reused = apply_sign_images(items, sign_assets or {}, sign_library or [])
    items = terrain.lift(items, ground, decks)  # 2026-10-15: onto the street-view ground heights (flat when the region has none)
    items = kits.stack_items(items, frame.studs_per_m)  # column stacks of uploaded kits (kits.STACKS); none uploaded leaves the parts
    if decks is not None:
        items += bridges.pier_items(decks, ok_features, ground, cell_id, res, cfg)
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
              "signs": signs, "labels": labels, "sign_images": sign_images, "signs_reused": signs_reused, "parts_total": len(items), "boxes": len(boxes_report),
              "no_facing": len(no_facing), "far_facing": len(far_facing), "tier": tier}
    # the far view of the B plan (lite.py): building boxes, roofs and coarse ground, always loaded while the full cell comes and goes
    lite_list = layout.order_items(lite.lite_items(cell_id, frame, items, ground, layout.ground_item(cell_id, frame, cfg)))
    counts["lite_items"] = len(lite_list)
    if len(items) > CELL_PART_BUDGET:
        warnings.append(f"{len(items)} parts: over the cell budget of {CELL_PART_BUDGET} (architecture.md section 5)")
        counts["warnings"] = len(warnings)
    manifest = {"cell_id": cell_id, "counts": counts, "poor_fit": poor_fit, "warnings": warnings, "boxes": boxes_report,
                "building_ids": building_ids, "duplicates_dropped": [list(d) for d in dropped], "no_facing": no_facing, "far_facing": far_facing,
                "files": {n: len(t.encode()) for n, t in sorted(files.items())},
                "config": {k: cfg[k] for k in ("origin_lat", "origin_lon", "studs_per_m", "chunk_size", "poor_fit_ratio",
                                                "ground_margin_m", "sidewalk_width_m", "spawn_lat", "spawn_lon", "spawn_yaw_deg",
                                                "pole_spacing_m", "lamp_spacing_m", "tree_spacing_m", "car_spacing_m", "school_zone_m",
                                                "roof_pitch_deg", "window_faces")}}
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    files["chunks.json"] = chunks_json(cell_id, [files[n] for n in sorted(files) if n.startswith("chunk-")], building_ids)
    files["lite.json"] = chunks_json(cell_id, [render_chunk(cell_id, 1, 1, lite_list)], [])
    return Plan(cell_id, items, files, counts, warnings)


def apply_sign_images(items: Sequence[layout.Item], own: Mapping[str, int], library: Sequence[Mapping[str, Any]]
                      ) -> tuple[list[layout.Item], int, int]:
    """SI-6: a band or floor sign whose image was uploaded (this cell's signs.json or the region library, same key) gets the asset
    id; the text stays as the fallback. U7 K: a building's name (owner + text) none of whose image signs has its own image reuses
    an uploaded image of the region with the first sign's tail (band or floor sign, so a ground-floor name stays one) and panel
    color and an aspect within 12 % whose name the building does not show yet, chosen by pick on that sign's name; every sign of
    that name then reads the image's text, and
    its other image signs take an image of that text with their own tail, aspect and color when there is one. Returns (items,
    signs with an image, of them reused)."""
    exact = {**{r["key"]: int(r["asset_id"]) for r in library}, **own}
    looks: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for r in library:
        looks.setdefault((r["tail"], r["bg"]), []).append(r)

    def near(n: int, tail: str, aspect: str) -> list[Mapping[str, Any]]:  # the Builder stretches the image over the sign
        a = float(aspect)
        return [r for r in looks.get((tail, items[n].color_name), []) if abs(math.log(float(r["aspect"]) / a)) <= SIGN_REUSE_ASPECT]
    groups: dict[tuple[str | None, str], list[tuple[int, str, str]]] = {}
    for n, i in enumerate(items):
        if i.kind == "sign" and i.text and i.color_name and i.ink and details_rules.sign_tail(i.name) in details_rules.SIGN_IMAGE_TAILS:
            groups.setdefault((i.owner, i.text), []).append((n, details_rules.sign_tail(i.name), details_rules.aspect_bucket(i.sx, i.sy)))
    picked: dict[int, int] = {}
    renamed: dict[tuple[str | None, str], str] = {}
    used: dict[str | None, set[str]] = {}  # the reused names of each building: a name appears once (review 2026-10-14: 3 floors read "아람피부과")
    reused = 0
    for (owner, text), signs in groups.items():
        keys = {n: details_rules.sign_image_key(text, tail, items[n].color_name, items[n].ink, aspect) for n, tail, aspect in signs}
        if any(k in exact for k in keys.values()):
            picked.update({n: exact[k] for n, k in keys.items() if k in exact})
            continue
        n0, tail0, aspect0 = signs[0]
        rows = [r for r in near(n0, tail0, aspect0) if r["text"] not in used.setdefault(owner, set())]
        if not rows:
            continue
        new_text = rows[details_rules.pick(items[n0].name, "sign_reuse", len(rows))]["text"]
        renamed[(owner, text)] = new_text
        used[owner].add(new_text)
        for n, tail, aspect in signs:
            match = [r for r in near(n, tail, aspect) if r["text"] == new_text]
            if match:
                picked[n] = int(match[0]["asset_id"])
                reused += 1
    out = []
    for n, i in enumerate(items):
        if i.kind == "sign" and (i.owner, i.text) in renamed:
            i = dataclasses.replace(i, text=renamed[(i.owner, i.text)], attrs=dict(i.attrs))
        if n in picked:
            i.attrs["ImageAsset"] = picked[n]
        out.append(i)
    return out, len(picked), reused


def load_sign_library(cfg: Mapping[str, Any], cell_id: str) -> list[dict[str, Any]]:
    """U7 K: every uploaded sign image of the cell's region (signs.json of all its cells) as rows of key, asset_id, text, tail, bg,
    ink, aspect, sorted by key. A row whose key does not match its look refuses the build, like a bad asset entry."""
    folder, _ = common.region_of(cfg, cell_id)
    rows: dict[str, dict[str, Any]] = {}
    for path in sorted((folder / "cells").glob("*/signs.json")):
        assets = load_sign_assets(path)
        signs = json.loads(path.read_text(encoding="utf-8"))["signs"]
        for key, asset in assets.items():
            r = signs[key]
            look = {k: r.get(k) for k in ("text", "tail", "bg", "ink", "aspect")}
            if not all(isinstance(v, str) for v in look.values()) or details_rules.sign_image_key(**look) != key:
                raise ValueError(f"{path.parent.name}/signs.json: key {key} does not match its look")
            rows[key] = {"key": key, "asset_id": asset, **look}
    return [rows[k] for k in sorted(rows)]


PAIR = re.compile(r'(\w+)=("([^"]*)"|-?\d+(?:\.\d+)?)')


def chunks_json(cell_id: str, chunk_texts: Sequence[str], building_ids: Sequence[str], land: Mapping[str, Any] | None = None) -> str:
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
    body: dict[str, Any] = {"cell_id": cell_id, "chunks": chunks, "counts": counts, "building_ids": list(building_ids)}
    if land is not None:  # the ground heights under the cell's slab for MapBuilder.terrain (2026-10-15)
        body["terrain"] = land
    return json.dumps(body, ensure_ascii=False)


def cell_index(cells: Sequence[str], frame: layout.Frame) -> dict[str, Any]:
    """Every built cell's centre in studs and its rings (itself and the built cells one and two steps away) for
    ServerScriptService/CellStreamer, which builds a player's cell and two rings (user decision 2026-10-15)."""
    built = set(cells)
    out = {}
    for c in sorted(built):
        x, z = layout.to_studs(frame, *h3.cell_to_latlng(c))
        out[c] = {"x": round(x, 1), "z": round(z, 1), "ring1": sorted(built & set(h3.grid_disk(c, 1))),
                  "ring2": sorted(built & set(h3.grid_disk(c, 2)))}
    return {"cells": out}


def write_cell_index(root: Path, cfg: Mapping[str, Any]) -> Path:
    """root/cellindex.json over every cell that has a manifest under root."""
    cells = sorted(p.parent.name for p in root.glob("*/manifest.json"))
    path = root / "cellindex.json"
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cell_index(cells, layout.Frame.from_cfg(cfg))), encoding="utf-8")
    return path


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
    features = [f for f in db.rows_in_cells(conn, "street_features", [cell_id]) if f["kind"] in ("road", "path", "subway_entrance")]
    estimates = {e["building_id"]: e for e in db.estimates_in_cell(conn, cell_id)}
    return buildings, features, estimates, db.overrides_by_building(conn, cell_id), db.details_by_building(conn, cell_id)


def load_exits(path: Path) -> list[dict[str, Any]]:
    """Subway exits OSM lacks, read off the satellite and street view (regions/<region>/exits.json, cycle-build 2c, 2026-10-15), as
    subway_entrance rows like the OSM ones; none without the file. Row: {"id": "exit:<station>-<ref>", "ref": "6", "lat", "lon"}."""
    if not path.exists():
        return []
    out = []
    for r in json.loads(path.read_text(encoding="utf-8"))["exits"]:
        if not (SAFE_TEXT.fullmatch(str(r.get("id"))) and str(r.get("ref")).isdigit()
                and all(isinstance(r.get(k), (int, float)) and math.isfinite(r[k]) for k in ("lat", "lon"))):
            raise ValueError(f"{path.name}: bad exit {str(r.get('id'))[:30]!r}")
        out.append({"feature_id": r["id"], "kind": "subway_entrance", "geometry": [[r["lat"], r["lon"]]], "tags": {"ref": str(r["ref"])}})
    return out


def load_clear(path: Path) -> list[dict[str, Any]]:
    """Rectangles of hand-made courts (courts.py) that keep satellite trees off; none without the file."""
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))["clear"]
    if not all(all(isinstance(r.get(k), (int, float)) and math.isfinite(r[k]) for k in ("x", "z", "yaw", "w", "d")) for r in rows):
        raise ValueError(f"{path.name}: bad rectangle")
    return rows


_ROADS: dict[str, list[dict[str, Any]]] = {}


def region_roads(conn, cfg: Mapping[str, Any], cell_id: str) -> list[dict[str, Any]]:
    """Every road feature of the cell's region, once each (cached per region): a cell keeps its trees, sidewalks and street props
    off a neighbour's carriageway even when its own data does not hold that road."""
    folder, data = common.region_of(cfg, cell_id)
    if folder.name not in _ROADS:
        seen: dict[str, dict[str, Any]] = {}
        for f in db.rows_in_cells(conn, "street_features", list(data.get("cells") or [])):
            if f["kind"] == "road" and SAFE_TEXT.fullmatch(str(f["feature_id"])):
                seen.setdefault(str(f["feature_id"]), f)
        _ROADS[folder.name] = [seen[k] for k in sorted(seen)]
    return _ROADS[folder.name]


_DECKS: dict[str, "bridges.Decks"] = {}


def region_decks(conn, cfg: Mapping[str, Any], cell_id: str) -> "bridges.Decks":
    """The overpasses of the cell's region, from the road features of all its cells (cached per region)."""
    folder, data = common.region_of(cfg, cell_id)
    key = folder.name
    if key not in _DECKS:
        roads = [f for f in db.rows_in_cells(conn, "street_features", list(data.get("cells") or [])) if f["kind"] == "road"]
        _DECKS[key] = bridges.Decks(roads, layout.Frame.from_cfg(cfg), cfg)
    return _DECKS[key]


def build_cell(conn, cfg: Mapping[str, Any], cell_id: str, root: Path) -> Plan:
    cfg = common.cell_config(cfg, cell_id)
    tier = tiers.tier_of(cfg, cell_id) or 1  # never classified: treated as tier 1 (cycle-build step 0)
    buildings, features, estimates, overrides, details = load_cell_inputs(conn, cell_id)
    features = features + load_exits(common.region_of(cfg, cell_id)[0] / "exits.json")
    sign_assets = load_sign_assets(common.cell_file(cfg, cell_id, "signs"))
    sat_trees = streets.load_trees(common.cell_file(cfg, cell_id, "trees"))
    plan = plan_cell(cell_id, buildings, features, cfg, estimates, overrides, details, sign_assets, sat_trees, tier,
                     load_sign_library(cfg, cell_id), fields.load_fields(common.cell_file(cfg, cell_id, "fields")),
                     roofs.load_roofs(common.cell_file(cfg, cell_id, "roofs")),
                     streets.load_under_trees(common.cell_file(cfg, cell_id, "trees")), terrain.ground_for(cfg), region_decks(conn, cfg, cell_id),
                     load_clear(common.cell_file(cfg, cell_id, "courts")), region_roads(conn, cfg, cell_id))
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
    write_cell_index(root, cfg)  # CellStreamer's index of every built cell (2026-10-15)
    # the region's ground for MapBuilder.settleManual (hand-made places sit on it too), 2026-10-15
    ground = terrain.ground_for(common.cell_config(cfg, args.cells[0])) if args.cells else None
    if ground is not None:
        g = ground.coarse(16.0)
        root.mkdir(parents=True, exist_ok=True)
        (root / "terrain.json").write_text(json.dumps(g.window(g.x0, g.x0 + g.step * (g.nx - 1), g.z0, g.z0 + g.step * (g.nz - 1))), encoding="utf-8")
    common.log(logging.INFO, f"done: {len(args.cells) - failed} ok, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    common.run_cli(main, "build_luau")
