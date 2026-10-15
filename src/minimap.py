# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""C9: the minimap data and the installer of the U6 scripts (minimap, big map, kick scooter).

Usage:
  uv run src/minimap.py --cells 8930e0af13bffff 8930e0af12bffff   # writes data/build/minimap.luau and data/build/install-u6.luau
  (Studio: put minimap.luau into ReplicatedStorage/MinimapData.Source, then run install-u6.luau for the scripts; one file would pass
   Studio's 200,000-character Source limit)
  uv run src/minimap.py --selftest                                 # import check only

minimap.luau is the ModuleScript text ReplicatedStorage/MinimapData: rectangles in Studio studs (the same plan items build_luau.py makes:
roads, paths, buildings) plus a few hand-set areas and place names. install-u6.luau creates or updates every U6 object in Studio from the
studio/StarterPlayerScripts and studio/ServerScriptService sources and that data; Claude runs it with execute_luau (Edit). Run it again after a cell is built.
Rules: aidlc-docs/construction/plans/u6-minimap-scooter-plan.md
"""
from __future__ import annotations

import argparse
import logging
import math
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import h3

import json

import build_luau
import common
import db
import details_rules as R
import fields
import layout
import streets

BUILD_DIR = "data/build"
STUDIO_DIR = Path(__file__).resolve().parent.parent / "studio"

# look codes of a rectangle; the client colours and orders them (area < road < building)
PARK, FIELD, COURT, ROAD, PATH, BUILDING, RAMP = 1, 2, 3, 4, 5, 6, 7
ITEM_LOOK = {"road": ROAD, "path": PATH, "building": BUILDING}

# hand-set ground the plan items do not have (studs; rotation = yaw degrees counterclockwise from east, like an item).
# The numbers are read off Workspace/Manual of the first cell: the park block (studio/manual/bucheon-dodang/Park.luau), the school sports ground
# (397 x 192 turned 10 degrees), the 부흥중 sand ground and basketball court.
AREAS: tuple[tuple[int, float, float, float, float, float], ...] = (
    (PARK, -411.0, -18.0, 142.0, 244.0, -5.7),
    (FIELD, -56.0, 34.0, 397.0, 192.0, -10.0),
    (FIELD, -501.0, -283.0, 185.0, 180.0, 170.76),
    (COURT, -635.5, -292.5, 77.0, 115.0, 170.76),
)
LABEL_TEXT = re.compile(r"[가-힣A-Za-z0-9 ]{1,20}")  # the only characters that may reach Luau code (N-U2-4)

# place names (U6 map detail Q1 = A+B+C+D, Q2 = A, 2026-10-14): {text, x, z, level, kind, rotation}.
# level 1 shows on the small map too, 2 on the big map, 3 when the big map is zoomed in; kind 1 dong, 2 road, 3 facility, 4 building.
DONG, ROAD_NAME, FACILITY, BUILDING_NAME = 1, 2, 3, 4
HAND_LABELS = (("옥산공원", -411.0, -18.0, 1, FACILITY, 0.0),)  # the park has no building record
# a register name goes on the map only when it ends like a building or a facility: personal names and lot numbers never do
# ("<동> 131-16 단독주택 (<사람>)" is in the register, 2026-10-14)
NAME_ENDS = ("아파트", "빌라", "빌라트", "빌", "맨션", "하이츠", "타운", "홈타운", "캐슬", "팰리스", "프라자", "플라자", "타워", "빌딩", "센터",
             "상가", "오피스텔", "시장", "병원", "의원", "금고", "은행", "우체국", "교회", "성당", "유치원", "어린이집", "하우스", "힐", "힐스",
             "뷰", "빌리지", "파크", "랜드", "스페이스빌", "학교", "경로당")
MAJOR_ENDS = ("학교", "행정복지센터", "주민센터")  # level 1 facilities
FACILITY_ENDS = MAJOR_ENDS + ("경로당", "금고", "은행", "우체국", "병원", "의원", "교회", "성당", "유치원", "어린이집", "센터", "시장")
BLOCK_NO = re.compile(r"[0-9]{3,4}동")
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
MARGIN = 40.0  # studs of empty map around the outermost rectangle corner


def rect_of(look: int, cx: float, cz: float, w: float, d: float, rot: float) -> list[float]:
    """[look, x, z, w, d, rotation], lengths to 0.1 stud; w runs along the part's own X and d along its Z (the item rule)."""
    return [look, round(cx, 1), round(cz, 1), round(w, 1), round(d, 1), round(rot % 360.0, 2)]


def corners(r: Sequence[float]) -> list[tuple[float, float]]:
    """The four corners (x, z) of a rectangle. rotation = yaw: the local X axis points (cos, -sin) in (x, z), the local Z axis (sin, cos)."""
    _, x, z, w, d, rot = r
    a = math.radians(rot)
    ux, uz, vx, vz = math.cos(a), -math.sin(a), math.sin(a), math.cos(a)
    return [(x + sa * ux * w / 2 + sb * vx * d / 2, z + sa * uz * w / 2 + sb * vz * d / 2) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def rects_of_items(items: Sequence[layout.Item]) -> list[list[float]]:
    """The map rectangles of a plan: roads, paths and building boxes, in a fixed order."""
    out = [rect_of(ITEM_LOOK[i.kind], i.cx, i.cz, i.sx, i.sz, i.yaw_deg) for i in items if i.kind in ITEM_LOOK]
    out += [rect_of(RAMP, i.cx, i.cz, i.sx, i.sz, i.yaw_deg) for i in items if "#ramp" in i.name]  # trick ramps
    return sorted(out, key=lambda r: (r[0], r[1], r[2], r[3], r[4], r[5]))


def bounds_of(rects: Sequence[Sequence[float]]) -> list[float]:
    """[x0, z0, x1, z1] around every corner plus the margin; an empty map gets a 1 x 1 stud box so the client never divides by zero."""
    pts = [p for r in rects for p in corners(r)]
    if not pts:
        return [0.0, 0.0, 1.0, 1.0]
    return [round(min(p[0] for p in pts) - MARGIN, 1), round(min(p[1] for p in pts) - MARGIN, 1),
            round(max(p[0] for p in pts) + MARGIN, 1), round(max(p[1] for p in pts) + MARGIN, 1)]


def luau_label(text: str) -> str:
    if not LABEL_TEXT.fullmatch(text):
        raise ValueError(f"label {text!r} has characters that are not allowed in Luau code")
    return '"' + text + '"'


def map_name(name: str | None) -> str | None:
    """A register name fit for the map, or None (personal names, lot numbers, odd characters)."""
    if not name:
        return None
    n = re.sub(r"\s+", " ", name).strip()
    if "(" in n or "단독주택" in n or re.search(r"[0-9]+-[0-9]+", n) or not LABEL_TEXT.fullmatch(n):
        return None
    if BLOCK_NO.fullmatch(n) or n.endswith(NAME_ENDS):
        return n
    return None


def building_labels(buildings: Sequence[Mapping[str, Any]], frame: layout.Frame) -> list[tuple]:
    """One label per name and place: the same name within 150 studs is one complex (four 한신빌라 boxes, the school's wings)."""
    groups: list[dict[str, Any]] = []
    for b in sorted(buildings, key=lambda b: str(b["building_id"])):
        n = map_name(b.get("name"))
        if n is None or not b.get("centroid"):
            continue
        x, z = layout.to_studs(frame, b["centroid"][0], b["centroid"][1])
        a = float(b.get("building_area") or 0.0)
        reach = 450 if n.endswith(FACILITY_ENDS) else 150  # a school's wings lie far apart
        for g in groups:
            if g["name"] == n and math.hypot(g["x"] - x, g["z"] - z) < reach:
                w = g["area"] + a + 1e-6
                g["x"], g["z"] = (g["x"] * (g["area"] + 1e-9) + x * (a + 1e-9)) / (w + 1e-9), (g["z"] * (g["area"] + 1e-9) + z * (a + 1e-9)) / (w + 1e-9)
                g["area"] += a
                g["floors"] = max(g["floors"], b.get("floors_above") or 0)
                break
        else:
            groups.append({"name": n, "x": x, "z": z, "area": a, "floors": b.get("floors_above") or 0})
    out = []
    for g in groups:
        n = g["name"]
        if n.endswith(MAJOR_ENDS):
            level, kind = 1, FACILITY
        elif n.endswith(FACILITY_ENDS):
            level, kind = 2, FACILITY
        elif BLOCK_NO.fullmatch(n):
            level, kind = 3, BUILDING_NAME
        else:
            level, kind = (2 if g["area"] >= 300 or g["floors"] >= 7 else 3), BUILDING_NAME
        out.append((n, round(g["x"], 1), round(g["z"], 1), level, kind, 0.0))
    # two names on one spot (OSM "중3동 주민센터" and the register's "중3동행정복지센터"): keep the more important, then the longer
    out.sort(key=lambda l: (l[3], -len(l[0]), l[0]))
    kept: list[tuple] = []
    for l in out:
        if not any(math.hypot(l[1] - k[1], l[2] - k[2]) < 60 for k in kept):
            kept.append(l)
    return kept


def road_labels(features: Sequence[Mapping[str, Any]], frame: layout.Frame) -> list[tuple]:
    """Road names along their longest piece (and a second one on a long road), turned to read left to right."""
    pieces: dict[str, list[tuple[float, float, float, float, float]]] = {}
    level_of: dict[str, int] = {}
    for f in features:
        tags = f.get("tags") or {}
        n = (tags.get("name") or "").strip()
        if not n or not LABEL_TEXT.fullmatch(n) or len(f["geometry"]) < 2:
            continue
        pts = [layout.to_studs(frame, p[0], p[1]) for p in f["geometry"]]
        for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
            pieces.setdefault(n, []).append((math.hypot(x1 - x0, z1 - z0), (x0 + x1) / 2, (z0 + z1) / 2, x1 - x0, z1 - z0))
        hw = str(tags.get("highway") or "")
        lv = 1 if hw.replace("_link", "") in layout.BIG_ROADS else 3 if re.search(r"번[가-힣]?길$", n) else 2
        level_of[n] = min(level_of.get(n, 9), lv)
    out = []
    for n in sorted(pieces):
        ps = sorted(pieces[n], key=lambda p: (-p[0], p[1], p[2]))
        chosen = [ps[0]]
        if sum(p[0] for p in ps) > 1200:
            far = [p for p in ps if math.hypot(p[1] - ps[0][1], p[2] - ps[0][2]) > 500]
            chosen += far[:1]
        for _, x, z, dx, dz in chosen:
            rot = math.degrees(math.atan2(dz, dx))  # UI rotation is clockwise and +Z is down on the map: the same angle
            rot = (rot + 90) % 180 - 90  # never upside down
            out.append((n, round(x, 1), round(z, 1), level_of[n], ROAD_NAME, round(rot, 1)))
    return out


def dong_labels(cells: Sequence[str], frame: layout.Frame, places: Mapping[str, str]) -> list[tuple]:
    """A dong name at the middle of the built cells that lie in it."""
    by: dict[str, list[tuple[float, float]]] = {}
    for c in cells:
        n = places.get(c)
        if n and LABEL_TEXT.fullmatch(n):
            lat, lon = h3.cell_to_latlng(c)
            by.setdefault(n, []).append(layout.to_studs(frame, lat, lon))
    return [(n, round(sum(p[0] for p in ps) / len(ps), 1), round(sum(p[1] for p in ps) / len(ps), 1), 2, DONG, 0.0) for n, ps in sorted(by.items())]


def cell_places(cfg: Mapping[str, Any], cells: Sequence[str]) -> dict[str, str]:
    """The dong of each cell, from regions/<region>/places.json (git), asking Nominatim reverse (zoom 16) once for a missing cell."""
    out: dict[str, str] = {}
    for c in cells:
        path = Path(common.cell_config(cfg, c)["cell_dir"]).parent.parent / "places.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"note": "dong of each cell, Nominatim reverse zoom 16", "cells": {}}
        if c not in data["cells"]:
            lat, lon = h3.cell_to_latlng(c)
            r = common.http_get_json(NOMINATIM, {"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 16, "accept-language": "ko"},
                                     waits=cfg["retry_waits_s"], pause_s=1.1)
            a = r.get("address") or {}
            data["cells"][c] = a.get("quarter") or a.get("suburb") or a.get("neighbourhood") or ""
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        out[c] = data["cells"][c]
    return out


def hex_of(cell_id: str, items: Sequence[layout.Item], frame: layout.Frame, name: str) -> tuple:
    """A built cell for the teleport (2026-10-14): (name, landing x, landing z, six corners x1, z1 ... x6, z6) in studs. The landing is
    the sidewalk (else path, else road) piece nearest the cell centre, so a player never lands on a roof or in the traffic."""
    corners = [layout.to_studs(frame, lat, lon) for lat, lon in h3.cell_to_boundary(cell_id)]
    cx, cz = layout.to_studs(frame, *h3.cell_to_latlng(cell_id))
    land = (cx, cz)
    for kind in ("sidewalk", "path", "road"):
        pool = [i for i in items if i.kind == kind]
        if pool:
            best = min(pool, key=lambda i: (math.hypot(i.cx - cx, i.cz - cz), i.name))
            land = (best.cx, best.cz)
            break
    return (name, round(land[0], 1), round(land[1], 1), *[round(v, 1) for c in corners for v in c])


def hex_names(cells: Sequence[str], places: Mapping[str, str]) -> list[str]:
    """'<dong> <n>' for each cell, numbered within its dong in the given order; a cell without a dong is '칸 <n>'."""
    seen: dict[str, int] = {}
    out = []
    for c in cells:
        dong = places.get(c) or ""
        base = dong if dong and LABEL_TEXT.fullmatch(dong) else "칸"
        seen[base] = seen.get(base, 0) + 1
        out.append(f"{base} {seen[base]}")
    return out


def module_text(rects: Sequence[Sequence[float]], labels: Sequence[tuple] = HAND_LABELS, areas: Sequence[Sequence[float]] = (),
                hexes: Sequence[tuple] = ()) -> str:
    """The text of ReplicatedStorage/MinimapData. Areas come first so they are drawn under the roads."""
    allr = [rect_of(*a) for a in AREAS] + [list(a) for a in areas] + list(rects)
    # compact: whole studs and tenths of a degree, no spaces (25 cells crossed Studio's 200,000-character Source limit, 2026-10-15)
    rows = ",\n".join("{%d,%d,%d,%d,%d,%g}" % (r[0], round(r[1]), round(r[2]), max(1, round(r[3])), max(1, round(r[4])), round(r[5], 1)) for r in allr)
    lab = ",\n".join("\t{%s, %g, %g, %d, %d, %g}" % (luau_label(t), x, z, lv, k, rot) for t, x, z, lv, k, rot in labels)
    hx = ",\n".join("\t{%s, %s}" % (luau_label(h[0]), ", ".join("%g" % v for v in h[1:])) for h in hexes)
    return ("-- generated by src/minimap.py, do not edit. Rectangles are {look, x, z, width, depth, rotation} in Studio studs\n"
            "-- (look 1 park, 2 field, 3 court, 4 road, 5 path, 6 building, 7 trick ramp; rotation = yaw degrees counterclockwise from east).\n"
            "-- hexes are the built cells for the teleport: {name, landing x, landing z, x1, z1, ... x6, z6}.\n"
            "return {\n\tbounds = {%s},\n\trects = {\n%s\n\t},\n\tlabels = {\n%s\n\t},\n\thexes = {\n%s\n\t},\n}\n"
            % (", ".join("%g" % v for v in bounds_of(allr)), rows, lab, hx))


SOURCES = (("MinimapClient", "StarterPlayer.StarterPlayerScripts", "LocalScript", "StarterPlayerScripts/MinimapClient.client.luau"),
           ("HexTeleport", "ServerScriptService", "Script", "ServerScriptService/HexTeleport.server.luau"),
           ("ScooterClient", "StarterPlayer.StarterPlayerScripts", "LocalScript", "StarterPlayerScripts/ScooterClient.client.luau"),
           ("Scooter", "ServerScriptService", "Script", "ServerScriptService/Scooter.server.luau"),
           ("ParagliderClient", "StarterPlayer.StarterPlayerScripts", "LocalScript", "StarterPlayerScripts/ParagliderClient.client.luau"),
           ("Paraglider", "ServerScriptService", "Script", "ServerScriptService/Paraglider.server.luau"),
           # the server builds only the cells near players (2026-10-15); its data comes from studio/install/cell-data.luau
           ("CellStreamer", "ServerScriptService", "Script", "ServerScriptService/CellStreamer.server.luau"),
           ("CellLoading", "StarterPlayer.StarterPlayerScripts", "LocalScript", "StarterPlayerScripts/CellLoading.client.luau"),
           ("PlayerMap", "ServerScriptService", "Script", "ServerScriptService/PlayerMap.server.luau"),
           ("ManualCodec", "ServerStorage", "ModuleScript", "ServerStorage/ManualCodec.luau"),
           ("LiteSwap", "StarterPlayer.StarterPlayerScripts", "LocalScript", "StarterPlayerScripts/LiteSwap.client.luau"))


def long_string(text: str) -> str:
    level = 2
    while f"]{'=' * level}]" in text or text.endswith("]" + "=" * (level - 1)):
        level += 1
    return f"[{'=' * level}[\n{text}]{'=' * level}]"


def install_text(data_module: str, studio_dir: Path = STUDIO_DIR) -> str:
    """One Luau program that creates or updates every U6 object in Studio (Edit). Existing objects of the same name keep their place."""
    lines = ["-- generated by src/minimap.py: installs U6 (minimap, big map, kick scooter). Run in Studio (Edit) with execute_luau.",
             "local function ensure(parent, class, name)",
             "\tlocal o = parent:FindFirstChild(name)",
             "\tif o and o.ClassName ~= class then o:Destroy() o = nil end",
             "\tif not o then o = Instance.new(class) o.Name = name o.Parent = parent end",
             "\treturn o",
             "end",
             "local function at(path)",
             "\tlocal n = game",
             "\tfor part in path:gmatch(\"[^.]+\") do n = n:FindFirstChild(part) or game:GetService(part) end",
             "\treturn n",
             "end",
             "local made = {}",
             # the data goes in by its own request when it would push this program past Studio's 200,000-character Source limit
             # (15 cells, 2026-10-14): MINIMAP_DATA is then set by the caller before this program runs
             (f"local data = ensure(game:GetService(\"ReplicatedStorage\"), \"ModuleScript\", \"MinimapData\")\ndata.Source = {long_string(data_module)}\nmade[#made + 1] = \"MinimapData\""
              if data_module else "made[#made + 1] = \"MinimapData (installed apart from minimap.luau)\""),
             "ensure(game:GetService(\"ReplicatedStorage\"), \"RemoteEvent\", \"ScooterToggle\")\nmade[#made + 1] = \"ScooterToggle\"",
             "ensure(game:GetService(\"ReplicatedStorage\"), \"RemoteEvent\", \"HexTeleport\")\nmade[#made + 1] = \"HexTeleport\"",
             "ensure(game:GetService(\"ReplicatedStorage\"), \"RemoteEvent\", \"ScooterTrick\")\nmade[#made + 1] = \"ScooterTrick\"",
             "ensure(game:GetService(\"ReplicatedStorage\"), \"RemoteEvent\", \"LandmarkTeleport\")\nmade[#made + 1] = \"LandmarkTeleport\"",
             "ensure(game:GetService(\"ReplicatedStorage\"), \"RemoteEvent\", \"Paraglide\")\nmade[#made + 1] = \"Paraglide\""]
    for name, where, cls, fn in SOURCES:
        src = (studio_dir / fn).read_text(encoding="utf-8")
        lines.append(f"local s = ensure(at(\"{where}\"), \"{cls}\", \"{name}\")\ns.Source = {long_string(src)}\nmade[#made + 1] = \"{name}\"")
    lines.append("return made")
    return "\n".join(lines) + "\n"


def cell_items(conn, cfg: Mapping[str, Any], cell_id: str) -> list[layout.Item]:
    buildings, features, estimates, overrides, details = build_luau.load_cell_inputs(conn, cell_id)
    sat = streets.load_trees(common.cell_file(cfg, cell_id, "trees"))
    return build_luau.plan_cell(cell_id, buildings, features, common.cell_config(cfg, cell_id), estimates, overrides, details, None, sat).items


def parse_args(argv: Sequence[str], res: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="minimap.py", description=__doc__.split("\n")[0])
    parser.add_argument("--cells", nargs="+", metavar="ID", help="the built H3 cells the map shows")
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
    rects: list[list[float]] = []
    areas: list[list[float]] = []
    frame = layout.Frame.from_cfg(cfg)
    places = cell_places(cfg, args.cells)
    hexes = []
    for cell_id, name in zip(args.cells, hex_names(args.cells, places)):
        items = cell_items(conn, cfg, cell_id)
        rects += rects_of_items(items)
        hexes.append(hex_of(cell_id, items, frame, name))
        for g in fields.load_fields(common.cell_file(cfg, cell_id, "fields")):  # the school ground kit (U7 J)
            areas.append(rect_of(FIELD, g["x"], g["z"], g["w"], g["d"], g["yaw"]))
    buildings = [b for b in db.rows_in_cells(conn, "buildings", args.cells) if b["status"] == "ok"]
    features = [f for f in db.rows_in_cells(conn, "street_features", args.cells) if f["kind"] in ("road", "path")]
    labels = list(HAND_LABELS) + dong_labels(args.cells, frame, places) + road_labels(features, frame) + building_labels(buildings, frame)
    out = common.resolve(BUILD_DIR)
    out.mkdir(parents=True, exist_ok=True)
    data = module_text(sorted(rects), labels, areas, hexes)
    (out / "minimap.luau").write_text(data, encoding="utf-8")
    (out / "install-u6.luau").write_text(install_text(""), encoding="utf-8")  # scripts only; minimap.luau goes into MinimapData apart
    by_level = {lv: sum(1 for l in labels if l[3] == lv) for lv in (1, 2, 3)}
    common.log(logging.INFO, f"minimap written: {len(rects)} rectangles from {len(args.cells)} cells, plus {len(AREAS) + len(areas)} areas and "
                             f"{len(labels)} labels (level 1/2/3: {by_level[1]}/{by_level[2]}/{by_level[3]})")
    return 0


if __name__ == "__main__":
    common.run_cli(main, "minimap")
