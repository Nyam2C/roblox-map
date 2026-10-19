# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0", "pillow==12.3.0"]
# ///
"""U8 gates: what a cell has to pass before the next one is built (aidlc-docs/construction/plans/u8-auto-expand-plan.md).

G1 placement from the built chunks (this file): nothing standing on a carriageway (buildings, trees, posts, kits), no sidewalk,
curb or footpath on another road's carriageway, every crosswalk on a road and single, a road as wide on both sides of a cell
edge. The Studio check (.claude/skills/cycle-verify/road-clear-check.luau) adds the parts the chunks do not hold
(Workspace/Manual). G2 satellite tiles and G3 look-alike (lookalike.py) are judged by the verify agent; `summary` joins them
with the frame-rate walk into data/gate/<cell>/gate.json. Thresholds: gate.toml. Accepted exceptions:
regions/<region>/cells/<cell>/gate-allow.json. Both are the main session's; a worker agent never edits them.

Usage:
  uv run src/gate.py g1 --cells <cell...>                       # data/gate/<cell>/g1.json, one line per cell
  uv run src/gate.py studio --cell <cell> --file <check.json>   # the Studio check's answer -> data/gate/<cell>/g1-studio.json
  uv run src/gate.py tiles --cell <cell> --satellite <out_satellite.jpg> --capture <top.jpg>   # G2 tiles -> data/gate/<cell>/g2/
  uv run src/gate.py g2 --cell <cell> --file <answers.json>     # the verify agent's tile answers -> data/gate/<cell>/g2.json
  uv run src/gate.py fps --cell <cell> --avg 60 --low 57        # the walk -> data/gate/<cell>/fps.json
  uv run src/gate.py summary --cells <cell...> [--need fps]     # data/gate/<cell>/gate.json: pass, or what failed and where
  uv run src/gate.py status                                     # one line for every cell that has a gate.json
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import math
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import h3
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

import common
import kits
from road_overlaps import rect

GATE_FILE = "gate.toml"
GATE_DIR = "data/gate"
BUILD_DIR = "data/build"
LIST_MAX = 30  # items listed per check; the count is always the full one
# the last name part of props that belong on or over a carriageway: markings (crosswalks are checked on their own), kickers,
# bridge girders, walls and piers, wires and the arms and signs up a pole, crowns that overhang. Curbs go with the sidewalks,
# trees by their trunk.
OVER_ROAD = re.compile(r"(cl|dash|cw|sl|bw|pier|wire|larm|lhead|arm|zs)\d|ramp|deck|crown")
CURB = re.compile(r"curb[LR]")
TREE = re.compile(r"tree")
G1_CHECKS = ("buildings_on_road", "trees_on_road", "props_on_road", "sidewalks_on_road", "paths_on_road",
             "crosswalks_off_road", "crosswalks_double", "seam_widths")
PARTS = ("g1", "g1_studio", "g2", "g3", "trace", "fps")  # trace: src/facade.py check (a traced cell, instead of g3)  # the files summary joins, data/gate/<cell>/<part>.json (g1_studio: g1-studio.json)
ISSUES = ("missing_road", "extra_road", "road_width", "building_missing", "building_extra", "tree_on_road", "facility_missing", "other")


def load_gate(path: str | Path | None = None) -> dict[str, Any]:
    with common.resolve(path or GATE_FILE).open("rb") as f:
        return tomllib.load(f)


def gate_digest(path: str | Path | None = None) -> str:
    """First 12 hex of the thresholds file's sha1: every result says which thresholds judged it."""
    return hashlib.sha1(common.resolve(path or GATE_FILE).read_bytes()).hexdigest()[:12]


def tail(name: str) -> str:
    return name.rsplit("#", 1)[-1]


def root(name: str) -> str:
    """The road (feature id) or building a piece belongs to."""
    return name.split("#", 1)[0]


def span(item: Mapping[str, Any]) -> tuple[float, float]:
    """Bottom and top in studs. A standing cylinder's height is its X size (BR-14.3); tilt is ignored (a few studs at most)."""
    up = item["w"] if item.get("p") == "Cylinder" else item["h"]
    return item["y"] - up / 2, item["y"] + up / 2


def footprint(item: Mapping[str, Any]) -> Polygon:
    if item.get("p") == "Cylinder":  # stands on its X axis: the footprint is its diameter
        return Point(item["x"], item["z"]).buffer(item["h"] / 2, quad_segs=4)
    return rect(item)


def trunk(item: Mapping[str, Any], studs_per_m: float) -> tuple[float, float]:
    """Where a tree meets the ground. A whole-tree kit's box is the crown's, off the trunk (streets.tree_items): undo that offset."""
    kit = item.get("kt")
    if kit not in kits.TREES:
        return item["x"], item["z"]
    da, dl, _, size = _tree_box(kit)
    sc = item["w"] / (size[0] * studs_per_m)
    t = math.radians(item.get("r") or 0.0)
    ca, sa = math.cos(t), math.sin(t)
    de, dn = (da * ca - dl * sa) * sc, (da * sa + dl * ca) * sc
    return item["x"] - de * studs_per_m, item["z"] + dn * studs_per_m


_tree_box = functools.lru_cache(maxsize=None)(kits.tree_box)  # the mesh is rebuilt on every call; a cell has hundreds of trees


@dataclass(frozen=True)
class Way:
    """One carriageway piece: footprint, the footprint less the edge band, top height, width across (studs)."""
    road: str
    name: str
    poly: Polygon
    inner: Polygon
    top: float
    width: float


def ways_of(items: Iterable[Mapping[str, Any]], edge: float) -> list[Way]:
    out = []
    for i in items:
        if i["k"] == "road":
            p = rect(i)
            out.append(Way(root(i["n"]), i["n"], p, p.buffer(-edge, join_style=2) if i["d"] > 2 * edge else Polygon(), span(i)[1], i["d"]))
    return out


class Roads:
    """The carriageways of a cell and its neighbours, with the questions the checks ask of them."""

    def __init__(self, ways: Sequence[Way], low: float, high: float):
        self.ways, self.low, self.high = list(ways), low, high
        self.tree = STRtree([w.poly for w in self.ways])

    def near(self, geom: Any) -> list[Way]:
        return [self.ways[j] for j in self.tree.query(geom)]

    def blocking(self, geom: Any, sp: tuple[float, float]) -> list[Way]:
        """Pieces under geom whose clear space (top + low up to top + high) the thing reaches into: an overpass passes above."""
        return [w for w in self.near(geom) if sp[1] > w.top + self.low and sp[0] < w.top + self.high]

    def level(self, geom: Any, sp: tuple[float, float], band: float = 1.0) -> list[Way]:
        """Pieces under geom at the thing's own level (a sidewalk beside the road, not one under a deck)."""
        return [w for w in self.near(geom) if sp[1] > w.top - band and sp[0] < w.top + band]


def _area(geom: Any, ways: Sequence[Way], inner: bool) -> float:
    shapes = [w.inner if inner else w.poly for w in ways]
    shapes = [p for p in shapes if not p.is_empty]
    return geom.intersection(unary_union(shapes)).area if shapes else 0.0


def _at(item: Mapping[str, Any]) -> list[float]:
    return [round(item["x"], 1), round(item["z"], 1)]


def _check(found: Sequence[Mapping[str, Any]], allowed: set[str], fail: bool | None = None) -> dict[str, Any]:
    kept = [f for f in found if f["id"] not in allowed]
    return {"n": len(kept), "fail": bool(kept) if fail is None else fail, "items": kept[:LIST_MAX],
            "allowed": sorted({f["id"] for f in found if f["id"] in allowed})}


def placement(items: Sequence[Mapping[str, Any]], around: Sequence[Mapping[str, Any]], g: Mapping[str, Any], studs_per_m: float,
              allow: Mapping[str, Iterable[str]] | None = None) -> dict[str, Any]:
    """G1 over one cell's chunk items; `around` = the neighbour cells' items (their roads count, their things are theirs)."""
    s = studs_per_m
    a2 = s * s
    allow = {k: set(v) for k, v in (allow or {}).items()}
    edge = g["edge_m"] * s
    roads = Roads(ways_of(list(items) + list(around), edge), g["clear_low_m"] * s, g["clear_high_m"] * s)
    out: dict[str, Any] = {}

    # buildings: the boxes of each building against the carriageways they stand in (cycle-verify 3c, now with neighbours and decks)
    by_building: dict[str, float] = {}
    where: dict[str, list[float]] = {}
    for i in items:
        if i["k"] != "building":
            continue
        p = rect(i)
        m2 = _area(p, roads.blocking(p, span(i)), inner=False) / a2
        bid = i.get("i") or root(i["n"])
        if m2 > by_building.get(bid, 0.0):
            by_building[bid], where[bid] = m2, _at(i)
    over = sorted(((m2, bid) for bid, m2 in by_building.items() if m2 > g["building_m2"]), reverse=True)
    found = [{"id": bid, "m2": round(m2, 2), "at": where[bid]} for m2, bid in over]
    kept = [f for f in found if f["id"] not in allow.get("buildings_on_road", set())]
    out["buildings_on_road"] = _check(found, allow.get("buildings_on_road", set()),
                                      fail=len(kept) > g["buildings_allowed"] or any(f["m2"] > g["building_max_m2"] for f in kept))

    # trees by the trunk, posts and other props by their footprint
    trees, props = [], []
    for i in items:
        if i["k"] != "prop":
            continue
        t = tail(i["n"])
        if TREE.match(t):
            x, z = trunk(i, s)
            pt = Point(x, z)
            if any(not w.inner.is_empty and w.inner.contains(pt) for w in roads.blocking(pt, span(i))):
                trees.append({"id": i["n"], "at": [round(x, 1), round(z, 1)]})
        elif not (OVER_ROAD.match(t) or CURB.match(t)):
            p = footprint(i)
            under = roads.blocking(p, span(i))
            m2 = _area(p, under, inner=True) / a2
            centre = Point(i["x"], i["z"])  # a thin post covers less than prop_m2 even when it stands in the middle of the road
            if m2 > g["prop_m2"] or any(not w.inner.is_empty and w.inner.contains(centre) for w in under):
                props.append({"id": i["n"], "m2": round(m2, 2), "at": _at(i)})
    out["trees_on_road"] = _check(trees, allow.get("trees_on_road", set()))
    out["props_on_road"] = _check(sorted(props, key=lambda f: -f["m2"]), allow.get("props_on_road", set()))

    # sidewalks and curbs on another road's carriageway (the rule is streets._on_other_road); on their own road only at bends: a warning
    other, own = [], []
    for i in items:
        if not (i["k"] == "sidewalk" or (i["k"] == "prop" and CURB.match(tail(i["n"])))):
            continue
        p = rect(i)
        level = roads.level(p, span(i))
        mine = root(i["n"])
        m2 = _area(p, [w for w in level if w.road != mine], inner=True) / a2
        if m2 > g["sidewalk_m2"]:
            other.append({"id": i["n"], "m2": round(m2, 2), "at": _at(i), "roads": sorted({w.road for w in level if w.road != mine})[:3]})
        m2_own = _area(p, [w for w in level if w.road == mine], inner=True) / a2
        if m2_own > g["sidewalk_m2"]:
            own.append({"id": i["n"], "m2": round(m2_own, 2), "at": _at(i)})
    out["sidewalks_on_road"] = _check(sorted(other, key=lambda f: -f["m2"]), allow.get("sidewalks_on_road", set()))

    paths = []
    for i in items:
        if i["k"] == "path":
            p = rect(i)
            m2 = _area(p, roads.level(p, span(i)), inner=True) / a2
            if m2 > g["path_m2"]:
                paths.append({"id": i["n"], "m2": round(m2, 2), "at": _at(i)})
    out["paths_on_road"] = _check(sorted(paths, key=lambda f: -f["m2"]), allow.get("paths_on_road", set()))

    # crosswalks: every stripe on a carriageway, and no two crosswalks painted over each other
    stripes = [i for i in items if i["k"] == "prop" and tail(i["n"]).startswith("cw")]
    off: dict[str, list[float]] = {}
    for i in stripes:
        pt = Point(i["x"], i["z"])
        if not any(w.poly.contains(pt) for w in roads.level(pt, span(i))):
            off.setdefault(i["n"].rsplit("-", 1)[0], _at(i))
    out["crosswalks_off_road"] = _check([{"id": k, "at": v} for k, v in sorted(off.items())], allow.get("crosswalks_off_road", set()))
    polys = [rect(i) for i in stripes]
    st = STRtree(polys) if polys else None
    double: dict[str, list[float]] = {}
    for a, i in enumerate(stripes):
        for b in (st.query(polys[a]) if st is not None else []):
            if b <= a:
                continue
            ida, idb = stripes[a]["n"].rsplit("-", 1)[0], stripes[b]["n"].rsplit("-", 1)[0]
            small = min(polys[a].area, polys[b].area)
            if ida != idb and small > 0 and polys[a].intersection(polys[b]).area / small > g["crosswalk_double"]:
                double.setdefault("|".join(sorted((ida, idb))), _at(i))
    out["crosswalks_double"] = _check([{"id": k, "at": v} for k, v in sorted(double.items())], allow.get("crosswalks_double", set()))

    # the same road on both sides of a cell edge has the same width (region_road_fits makes it so; this says when it does not)
    mine_w: dict[str, list[float]] = {}
    for w in ways_of(items, edge):
        mine_w.setdefault(w.road, []).append(w.width)
    theirs: dict[str, list[float]] = {}
    for w in ways_of(around, edge):
        theirs.setdefault(w.road, []).append(w.width)
    seams = []
    for rid in sorted(set(mine_w) & set(theirs)):
        a, b = _median(mine_w[rid]), _median(theirs[rid])
        if abs(a - b) > g["seam_width_m"] * s:
            seams.append({"id": rid, "here_m": round(a / s, 2), "next_m": round(b / s, 2)})
    out["seam_widths"] = _check(seams, allow.get("seam_widths", set()))

    fails = [k for k in G1_CHECKS if out[k]["fail"]]
    return {"pass": not fails, "fail": fails, "checks": out,
            "warn": {"own_road_sidewalks": own[:LIST_MAX], "own_road_sidewalks_n": len(own), "width_jumps": width_jumps(items, s)}}


def _median(v: Sequence[float]) -> float:
    v = sorted(v)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def width_jumps(items: Sequence[Mapping[str, Any]], studs_per_m: float, ratio: float = 1.6) -> list[dict[str, Any]]:
    """Two roads that meet end to end on one line with very different widths: shown, never failed (a road may really narrow)."""
    pieces = [i for i in items if i["k"] == "road"]
    polys = [rect(i) for i in pieces]
    if not polys:
        return []
    st = STRtree(polys)
    seen: set[tuple[str, str]] = set()
    out = []
    for a, i in enumerate(pieces):
        ta = math.radians(i["r"])
        for b in st.query(polys[a]):
            j = pieces[b]
            ra, rb = root(i["n"]), root(j["n"])
            if ra == rb or (rb, ra) in seen or (ra, rb) in seen:
                continue
            tb = math.radians(j["r"])
            if abs(math.cos(ta - tb)) < 0.94:  # not on one line
                continue
            # how far j's centre sits across i's centre line (i's local Z axis is (sin r, cos r) in x, z): side by side, like the
            # two halves of a divided road, is not a jump
            off = abs((j["x"] - i["x"]) * math.sin(ta) + (j["z"] - i["z"]) * math.cos(ta))
            if off > 0.5 * studs_per_m + abs(i["d"] - j["d"]) / 2:
                continue
            wide, narrow = max(i["d"], j["d"]), min(i["d"], j["d"])
            if narrow > 0 and wide / narrow > ratio:
                seen.add((ra, rb))
                out.append({"roads": [ra, rb], "m": [round(i["d"] / studs_per_m, 1), round(j["d"] / studs_per_m, 1)], "at": _at(i)})
    return out[:LIST_MAX]


# --- files ------------------------------------------------------------------------------------------

def cell_items(cell_id: str, build_dir: str | Path | None = None) -> list[dict[str, Any]] | None:
    path = common.resolve(build_dir or BUILD_DIR) / cell_id / "chunks.json"
    if not path.exists():
        return None
    return [i for ch in json.loads(path.read_text(encoding="utf-8"))["chunks"] for i in ch["items"]]


def load_allow(cfg: Mapping[str, Any], cell_id: str) -> dict[str, set[str]]:
    """regions/<region>/cells/<cell>/gate-allow.json: {"allow": [{"check", "id", "reason"}]}. No file, no exceptions."""
    try:
        path = common.cell_file(cfg, cell_id, "gate-allow")
    except ValueError:  # a cell outside every region (a test or a scratch cell) has none
        return {}
    if not path.exists():
        return {}
    out: dict[str, set[str]] = {}
    for row in json.loads(path.read_text(encoding="utf-8")).get("allow", []):
        if not (isinstance(row, Mapping) and row.get("check") and row.get("id") and str(row.get("reason") or "").strip()):
            raise ValueError(f"{path}: every exception needs check, id and reason: {row!r}")
        out.setdefault(str(row["check"]), set()).add(str(row["id"]))
    return out


def gate_path(cell_id: str, part: str, gate_dir: str | Path | None = None) -> Path:
    return common.resolve(gate_dir or GATE_DIR) / cell_id / f"{part.replace('_', '-')}.json"


def write_json(path: Path, data: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_g1(cfg: Mapping[str, Any], cell_id: str, gate: Mapping[str, Any], digest: str) -> dict[str, Any]:
    items = cell_items(cell_id)
    if items is None:
        raise FileNotFoundError(f"{BUILD_DIR}/{cell_id}/chunks.json: build the cell first (build_luau.py)")
    near = [c for c in sorted(h3.grid_disk(cell_id, 1)) if c != cell_id]
    around, used = [], []
    for c in near:
        got = cell_items(c)
        if got is not None:
            around += got
            used.append(c)
    result = placement(items, around, gate["g1"], float(cfg["studs_per_m"]), load_allow(cfg, cell_id))
    return {"cell": cell_id, "gate": digest, "neighbours": used, "at": common.now_iso(), **result}


# --- the Studio check (road-clear-check.luau) -------------------------------------------------------

def studio_result(raw: Mapping[str, Any], g: Mapping[str, Any], allowed: Iterable[str] = ()) -> dict[str, Any]:
    """The Studio check's hits grouped by what they belong to: the biggest overlap of each, over g1.studio_m2."""
    best: dict[str, Mapping[str, Any]] = {}
    for h in raw.get("hits", []):
        key = str(h["owner"])
        if float(h["m2"]) > g["studio_m2"] and float(h["m2"]) > float(best.get(key, {}).get("m2", 0.0)):
            best[key] = h
    found = [{"id": k, "m2": round(float(v["m2"]), 2), "part": v.get("part"), "road": v.get("road"), "at": v.get("at")}
             for k, v in sorted(best.items(), key=lambda kv: -float(kv[1]["m2"]))]
    check = _check(found, set(allowed))
    return {"pass": not check["fail"], "fail": ["on_road"] if check["fail"] else [], "checks": {"on_road": check},
            "roads": raw.get("roads"), "parts": raw.get("parts"), "cells": raw.get("cells")}


# --- G2: satellite tiles for the verify agent --------------------------------------------------------

def tile_boxes(width: int, height: int, n: int = 3) -> dict[str, tuple[int, int, int, int]]:
    """A1 .. C3 (rows from the top, columns from the left) as (left, top, right, bottom) pixel boxes that cover the image."""
    xs = [round(width * k / n) for k in range(n + 1)]
    ys = [round(height * k / n) for k in range(n + 1)]
    return {f"{'ABCDEFGH'[r]}{c + 1}": (xs[c], ys[r], xs[c + 1], ys[r + 1]) for r in range(n) for c in range(n)}


def make_tiles(satellite: Path, capture: Path, out_dir: Path, n: int = 3, min_width: int = 640) -> list[Path]:
    """Each tile: the satellite and the Studio top view of the same square side by side, scaled up to min_width each."""
    from PIL import Image, ImageDraw
    sat, cap = Image.open(satellite).convert("RGB"), Image.open(capture).convert("RGB")
    if sat.size != cap.size:
        raise ValueError(f"{satellite} is {sat.size}, {capture} is {cap.size}: use satellite.py compare's _satellite.jpg of this capture")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, box in tile_boxes(*sat.size, n).items():
        a, b = sat.crop(box), cap.crop(box)
        k = max(1.0, min_width / a.width)
        a, b = (im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS) for im in (a, b))
        sheet = Image.new("RGB", (a.width * 2 + 12, a.height + 28), (255, 255, 255))
        sheet.paste(a, (0, 28))
        sheet.paste(b, (a.width + 12, 28))
        d = ImageDraw.Draw(sheet)
        d.text((6, 6), f"{name}  satellite (left) | Studio top view (right), north up", fill=(0, 0, 0))
        p = out_dir / f"{name}.jpg"
        sheet.save(p, quality=88)
        paths.append(p)
    return paths


def g2_result(answers: Mapping[str, Any], g: Mapping[str, Any], allowed: Iterable[str] = (), n: int = 3) -> dict[str, Any]:
    """The verify agent's tile answers: every tile answered, known issue types; fails on more major issues than g2.major_allowed."""
    want = set(tile_boxes(n, n, n))
    rows = {str(t.get("tile")): t for t in answers.get("tiles", [])}
    missing = sorted(want - set(rows))
    if missing or set(rows) - want:
        raise ValueError(f"tiles answered {sorted(rows)}, expected {sorted(want)}")
    majors, minors = [], []
    for name in sorted(rows):
        for issue in rows[name].get("issues") or []:
            kind, sev = issue.get("type"), issue.get("severity")
            if kind not in ISSUES or sev not in ("major", "minor"):
                raise ValueError(f"tile {name}: issue type must be one of {ISSUES} and severity major or minor: {issue!r}")
            row = {"id": f"{name}:{kind}", "note": str(issue.get("note") or "")[:200]}
            (majors if sev == "major" else minors).append(row)
    allowed = set(allowed)
    kept = [m for m in majors if m["id"] not in allowed]
    fail = len(kept) > g["major_allowed"]
    return {"pass": not fail, "fail": ["major_issues"] if fail else [], "major": kept, "minor": minors,
            "allowed": sorted({m["id"] for m in majors if m["id"] in allowed})}


# --- the frame-rate walk, the summary ---------------------------------------------------------------

def fps_result(avg: float, low: float, g: Mapping[str, Any]) -> dict[str, Any]:
    fails = [k for k, ok in (("avg", avg >= g["min_avg"]), ("low", low >= g["min_low"])) if not ok]
    return {"pass": not fails, "fail": fails, "avg": avg, "low": low}


def tier_of(cfg: Mapping[str, Any], cell_id: str) -> int:
    """The cell's tier from regions/<region>/tiers.json (tiers.py); 1 when it is not classified yet (the strict case)."""
    try:
        folder, _ = common.region_of(cfg, cell_id)
    except ValueError:
        return 1
    path = folder / "tiers.json"
    if not path.exists():
        return 1
    row = json.loads(path.read_text(encoding="utf-8")).get("cells", {}).get(cell_id) or {}
    return int(row.get("tier") or 1)


def needed(tier: int, fps: bool, traced: bool = False) -> list[str]:
    """Parts a cell must have passed: placement (both checks) and the satellite always, the trace check on a traced cell, the walk
    when it is due (every gate.toml fps.every_cells cells). No look-alike scoring (G3) any more: it cost about $9 a cell and fixed
    a few judgements and colours (user 2026-10-19); src/lookalike.py stays for a cell someone wants scored by hand."""
    return ["g1", "g1_studio", "g2"] + (["trace"] if traced and tier == 1 else []) + (["fps"] if fps else [])


def summary(parts: Mapping[str, Mapping[str, Any] | None], need: Sequence[str]) -> dict[str, Any]:
    fails = []
    for p in need:
        got = parts.get(p)
        if got is None:
            fails.append(f"{p}:missing")
        elif not got.get("pass"):
            fails += [f"{p}:{f}" for f in got.get("fail") or ["fail"]]
    return {"pass": not fails, "fail": fails, "need": list(need),
            "parts": {p: (None if v is None else {"pass": bool(v.get("pass")), "fail": list(v.get("fail") or [])}) for p, v in parts.items()}}


def read_part(cell_id: str, part: str, gate_dir: str | Path | None = None) -> dict[str, Any] | None:
    path = gate_path(cell_id, part, gate_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# --- command line -----------------------------------------------------------------------------------

def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="gate.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("g1").add_argument("--cells", nargs="+", required=True)
    for name in ("studio", "g2"):
        p = sub.add_parser(name)
        p.add_argument("--cell", required=True)
        p.add_argument("--file", required=True, type=Path)
    t = sub.add_parser("tiles")
    t.add_argument("--cell", required=True)
    t.add_argument("--satellite", required=True, type=Path)
    t.add_argument("--capture", required=True, type=Path)
    f = sub.add_parser("fps")
    f.add_argument("--cell", required=True)
    f.add_argument("--avg", required=True, type=float)
    f.add_argument("--low", required=True, type=float)
    s = sub.add_parser("summary")
    s.add_argument("--cells", nargs="+", required=True)
    s.add_argument("--need", nargs="*", default=[], choices=["fps"])
    sub.add_parser("status")
    return ap.parse_args(list(argv))


def _cell_ok(cell_id: str, res: int) -> str:
    if not (h3.is_valid_cell(cell_id) and h3.get_resolution(cell_id) == res):
        raise ValueError(f"not an H3 cell of resolution {res}: {cell_id!r}")
    return cell_id


def main(cfg: dict[str, Any], argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    gate, digest = load_gate(), gate_digest()
    res = int(cfg["h3_res"])
    if args.command == "g1":
        bad = 0
        for cell in args.cells:
            out = run_g1(cfg, _cell_ok(cell, res), gate, digest)
            write_json(gate_path(cell, "g1"), out)
            counts = " ".join(f"{k}={out['checks'][k]['n']}" for k in G1_CHECKS if out["checks"][k]["n"])
            print(cell, "PASS" if out["pass"] else "FAIL " + ",".join(out["fail"]), counts)
            bad += not out["pass"]
        return 1 if bad else 0
    if args.command == "status":
        for p in sorted(common.resolve(GATE_DIR).glob("*/gate.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            print(p.parent.name, "PASS" if d["pass"] else "FAIL " + ",".join(d["fail"]), d.get("at", ""))
        return 0
    if args.command == "summary":
        bad = 0
        for cell in args.cells:
            _cell_ok(cell, res)
            tier = tier_of(cfg, cell)
            parts = {p: read_part(cell, p) for p in PARTS}
            traced = common.cell_file(cfg, cell, "facade").exists()
            out = {"cell": cell, "tier": tier, "gate": digest, "at": common.now_iso(),
                   **summary(parts, needed(tier, "fps" in args.need, traced))}
            write_json(gate_path(cell, "gate"), out)
            print(cell, "PASS" if out["pass"] else "FAIL " + ",".join(out["fail"]))
            bad += not out["pass"]
        return 1 if bad else 0
    cell = _cell_ok(args.cell, res)
    allow = load_allow(cfg, cell)
    if args.command == "studio":
        out = {"cell": cell, "gate": digest, "at": common.now_iso(),
               **studio_result(json.loads(args.file.read_text(encoding="utf-8")), gate["g1"], allow.get("studio", ()))}
        write_json(gate_path(cell, "g1_studio"), out)
    elif args.command == "tiles":
        paths = make_tiles(args.satellite, args.capture, gate_path(cell, "g2").parent / "g2")
        print("\n".join(str(p) for p in paths))
        return 0
    elif args.command == "g2":
        out = {"cell": cell, "gate": digest, "at": common.now_iso(),
               **g2_result(json.loads(args.file.read_text(encoding="utf-8")), gate["g2"], allow.get("g2", ()))}
        write_json(gate_path(cell, "g2"), out)
    else:
        out = {"cell": cell, "gate": digest, "at": common.now_iso(), **fps_result(args.avg, args.low, gate["fps"])}
        write_json(gate_path(cell, "fps"), out)
    print(cell, args.command, "PASS" if out["pass"] else "FAIL " + ",".join(out["fail"]))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    common.run_cli(main, "gate")
