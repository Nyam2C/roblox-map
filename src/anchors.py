# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""F: anchors for the Manual scripts -> studio/manual/<region>/anchors.json (U7 F, kept in git).

A Manual script must not hold box numbers or box coordinates (lessons 2026-10-14: a new box split moved the 부흥중 roof). It asks
for a building's anchor instead: the outline's own minimum-area rectangle (centre, yaw, size; the same whatever the box split)
and the building's current boxes, so a part that sits on one wing finds the box under a point of that wing.

Usage (repo root):
  uv run src/anchors.py build --region bucheon-dodang                 # anchors of the buildings listed in regions/<region>/manual.json
  uv run src/anchors.py script --region bucheon-dodang --name School  # anchors prelude + studio/manual/<region>/School.luau
                                                                      #   -> data/build/manual/School.luau, run that with execute_luau (Edit)
"""
from __future__ import annotations

import argparse
import tomllib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import build_luau
import common
import db
import judgement
import layout
import layout_details
from details_rules import DIMS

MANUAL_DIR = "studio/manual"
OUT_DIR = "data/build/manual"
F = layout.fmt


def anchor_of(building: Mapping[str, Any], eff: Any, detail: Mapping[str, Any] | None, note: str | None, frame: layout.Frame,
              cfg: Mapping[str, Any]) -> dict[str, Any] | None:
    """Anchor of one building in studs: x, z, yaw, w, d of the outline's rectangle (P7-10: box split free), top of the boxes, roof
    (the walkable top: above the flat-roof cap), flat, and boxes [[x, z, w, d, yaw], ...] as the Builder makes them now."""
    rect = layout.outline_to_box([(p[0], p[1]) for p in building["outline"]], frame)
    body = layout_details.make_body(building, eff, detail, note, frame, cfg)
    if rect is None or body is None:
        return None
    s = frame.studs_per_m
    top = body.height_m * s
    flat = body.is_body and body.roof_shape == "flat"
    return {"x": F(rect.cx_m * s), "z": F(-rect.cy_m * s), "yaw": F(rect.yaw_deg), "w": F(rect.width_m * s), "d": F(rect.depth_m * s),
            "top": F(top), "roof": F(top + (DIMS["cap_h"] - DIMS["cap_sink"]) * s if flat else top), "flat": flat,
            "boxes": [[F(b.cx_m * s), F(-b.cy_m * s), F(b.width_m * s), F(b.depth_m * s), F(b.yaw_deg)] for b in body.boxes]}


def load_places(region_dir: Path) -> list[dict[str, Any]]:
    data = json.loads((region_dir / "manual.json").read_text(encoding="utf-8"))
    places = data["places"]
    for p in places:
        if not (isinstance(p.get("name"), str) and isinstance(p.get("buildings", []), list)):
            raise ValueError(f"manual.json: a place needs a name and a buildings list: {p}")
    return places


def build_anchors(conn, cfg: Mapping[str, Any], region: str) -> dict[str, Any]:
    region_dir = common.resolve(cfg["regions_dir"]) / region
    wanted = {bid for p in load_places(region_dir) for bid in p.get("buildings", [])}
    cells = tomllib.loads((region_dir / "region.toml").read_text(encoding="utf-8"))["cells"]
    out: dict[str, Any] = {}
    for cell_id in cells:
        ccfg = common.cell_config(cfg, cell_id)
        frame = layout.Frame.from_cfg(ccfg)
        try:
            buildings, _, estimates, overrides, details = build_luau.load_cell_inputs(conn, cell_id)
        except ValueError:
            continue  # a cell not collected yet holds none of them
        for b in buildings:
            bid = str(b["building_id"])
            if bid not in wanted:
                continue
            eff = judgement.effective_building(b, estimates.get(bid), overrides.get(bid), ccfg)
            a = anchor_of(b, eff, details.get(bid), (estimates.get(bid) or {}).get("note"), frame, ccfg)
            if a is not None:
                out[bid] = {"cell": cell_id, **a}
    missing = sorted(wanted - set(out))
    if missing:
        raise ValueError(f"no stored building with an outline for {missing}")
    return dict(sorted(out.items()))


# The prelude the script command puts before a Manual script. A.box(id, x, z, yawHint) is the box under the world point (x, z)
# (the nearest box when none covers it), turned by a quarter turn when that brings it nearest to yawHint, so a script's
# "local -Z is south" holds when a new split swaps the box's long side. Its CFrame is at the box centre, half the top high, like the
# literals it replaces; the size is (along X, top, along Z).
PRELUDE = """-- anchors prelude (src/anchors.py, from studio/manual/{region}/anchors.json); do not edit here
local ANCHORS = game:GetService("HttpService"):JSONDecode([==[{json}]==])
local A = {{}}
function A.get(id) local a = ANCHORS[id] assert(a, "no anchor for " .. id) return a end
function A.frame(id) local a = A.get(id) return CFrame.new(a.x, 0, a.z) * CFrame.Angles(0, math.rad(a.yaw), 0), a end
function A.boxes(id)
\tlocal a, out = A.get(id), {{}}
\tfor _, b in ipairs(a.boxes) do table.insert(out, {{ cf = CFrame.new(b[1], a.top / 2, b[2]) * CFrame.Angles(0, math.rad(b[5]), 0), size = Vector3.new(b[3], a.top, b[4]) }}) end
\treturn out, a
end
function A.box(id, x, z, yawHint)
\tlocal boxes, a = A.boxes(id)
\tlocal p, best, bestD = Vector3.new(x, a.top / 2, z), nil, math.huge
\tfor _, b in ipairs(boxes) do
\t\tlocal l = b.cf:PointToObjectSpace(p)
\t\tlocal out = math.max(math.abs(l.X) - b.size.X / 2, 0) + math.max(math.abs(l.Z) - b.size.Z / 2, 0)
\t\tif out < bestD then best, bestD = b, out end
\tend
\tlocal cf, size = best.cf, best.size
\tif yawHint then
\t\tlocal _, ry = cf:ToOrientation()
\t\tlocal k = math.floor(((math.rad(yawHint) - ry) / (math.pi / 2)) + 0.5) % 4
\t\tcf = cf * CFrame.Angles(0, k * math.pi / 2, 0)
\t\tif k % 2 == 1 then size = Vector3.new(size.Z, size.Y, size.X) end
\tend
\treturn cf, size, a
end
-- end of prelude
"""


def prelude(region: str, anchors: Mapping[str, Any]) -> str:
    return PRELUDE.format(region=region, json=json.dumps(anchors, ensure_ascii=False, separators=(",", ":")))


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="anchors for the Manual scripts (U7 F)")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--region", required=True)
    s = sub.add_parser("script")
    s.add_argument("--region", required=True)
    s.add_argument("--name", required=True, help="a Manual script name, e.g. School")
    return p.parse_args(argv)


def main(cfg: dict[str, Any]) -> int:
    args = parse_args(sys.argv[1:])
    manual_dir = common.resolve(MANUAL_DIR) / args.region
    path = manual_dir / "anchors.json"
    if args.cmd == "build":
        anchors = build_anchors(db.connect(common.resolve(cfg["db_path"])), cfg, args.region)
        manual_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(anchors, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(anchors)} anchors -> {path}")
        return 0
    anchors = json.loads(path.read_text(encoding="utf-8"))
    out = common.resolve(OUT_DIR) / f"{args.name}.luau"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prelude(args.region, anchors) + (manual_dir / f"{args.name}.luau").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    common.run_cli(main, "anchors")
