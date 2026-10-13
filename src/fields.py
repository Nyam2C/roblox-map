# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "numpy==2.5.4", "pillow==12.3.0", "scipy==1.18.1", "shapely==2.2.0"]
# ///
"""J: the school sports-ground kit. Finds each school's ground in the V-World satellite photo and writes
regions/<region>/cells/<cell>/fields.json (kept in git); build_luau.py makes the ground from it (U7 J).

Usage (repo root):
  uv run src/fields.py --cells 8930e0af13bffff     # Overpass (OSM amenity=school areas) once, then any data/satellite/<cell>-z19.jpg
                                                   # that holds the school; schools a Manual script already makes are kept as
                                                   # made_by "manual" (to compare with), the others are "kit"
  uv run src/fields.py --selftest                  # import check only

OSM in Bucheon has the school areas but no pitches (2026-10-14: 3 schools, 0 leisure=pitch), so the ground comes from the photo:
inside the school area, minus roofs and crowns, the biggest smooth patch of sand colour (bright, red over blue) or artificial turf
(olive: green over red and blue, duller than a crown), closed over its lines, then its minimum-area rectangle turned to the school
buildings' grid when within 6 degrees. Measured 2026-10-14: sand (205..225, 195..210, 160..170), faded turf (107..114, 119..125,
89..91). Reference look (Creator Store models measured in MCP_Test, then deleted: 10541782424 court, 12968011289 track,
3925271000 stadium): lines 0.7 studs wide just above the ground, circles of short straight pieces, goal 7.32 x 2.44 m (a quarter of the
pitch width and 2 m high on a small ground).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import h3

import common
import db
import layout
from layout import Frame, Item, _item

OVERPASS = "https://overpass-api.de/api/interpreter"
OSM_ID = re.compile(r"way:[0-9]{1,15}")  # the only id that reaches a part name
SAT_DIR = "data/satellite"
MIN_AREA_M2 = 400.0      # a smaller patch is a yard, not the ground (옥산초 turf is about 21 x 33 m)
SNAP_DEG = 6.0           # turn the ground to the school's grid when this close
SMOOTH_STD = 12.0        # local brightness spread (7 px) of a ground; gravel, cars and shadows are rougher
LOOKS = {"sand": ("Sand", "field_sand", (196, 178, 140)), "turf": ("Grass", "field_turf", (97, 108, 80))}
LINE = ("SmoothPlastic", "field_line", (240, 240, 235))
POST = ("SmoothPlastic", "field_post", (240, 240, 238))
D = {"top": 0.5, "slab": 0.4, "line_w": 0.7, "line_t": 0.06, "line_in_m": 2.2, "circle_m": 9.15, "circle_pieces": 16,
     "goal_w_m": 7.32, "goal_h_m": 2.44, "small_goal_h_m": 2.0, "post": 0.4, "goal_min_len_m": 20.0}


# --- finding the ground (numpy only here, so build_luau can import field_items without it) -----------------------------

def ground_masks(rgb, smooth_only: bool = True):
    """(sand, turf) pixel masks of a photo: colour class and (smooth_only) a smooth neighbourhood."""
    import numpy as np
    from scipy import ndimage as ndi
    from trees import GCC_MIN
    r, g, b = (rgb[..., i].astype(float) for i in range(3))
    lum = (r + g + b) / 3
    mean = ndi.uniform_filter(lum, 7)
    std = np.sqrt(np.maximum(ndi.uniform_filter(lum * lum, 7) - mean * mean, 0))
    smooth = std < SMOOTH_STD
    gcc = g / np.maximum(r + g + b, 1)
    sand = (r > 150) & (r - b >= 25) & (r - b <= 90) & (np.abs(r - g) <= 35)
    turf = (g >= r) & (g - b >= 15) & (g >= 80) & (g <= 175) & (gcc < GCC_MIN)
    return (sand & smooth, turf & smooth) if smooth_only else (sand, turf)


def find_ground(rgb, geo, school: Sequence[Sequence[float]], roofs: Sequence[Sequence[Sequence[float]]], grid_yaws: Sequence[float],
                frame: Frame) -> dict[str, Any] | None:
    """The ground of one school (outline lat/lon pairs) in studs: x, z, yaw, w (long side), d, fit, surface; None when no patch is big enough."""
    import numpy as np
    from scipy import ndimage as ndi
    from trees import _fill
    h, w = rgb.shape[:2]
    lat0 = sum(p[0] for p in school) / len(school)
    mpp = geo.m_per_px(lat0)
    inside = _fill((w, h), [[geo.to_px(*p) for p in school]])
    roof = ndi.binary_dilation(_fill((w, h), [[geo.to_px(*p) for p in o] for o in roofs]), iterations=3)
    best = None
    raw = dict(zip(("sand", "turf"), ground_masks(rgb, smooth_only=False)))
    for surface, mask in zip(("sand", "turf"), ground_masks(rgb)):
        m = ndi.binary_closing(ndi.binary_opening(mask & inside & ~roof, iterations=2), iterations=4)
        m = ndi.binary_fill_holes(m) & inside & ~roof
        labels, n = ndi.label(m)
        if n == 0:
            continue
        sizes = ndi.sum(m, labels, range(1, n + 1))
        k = int(np.argmax(sizes)) + 1
        area = float(sizes[k - 1]) * mpp * mpp
        if area >= MIN_AREA_M2 and (best is None or area > best[0]):
            best = (area, surface, labels == k)
    if best is None:
        return None
    area, surface, comp = best
    # the edge pixels the smoothness test dropped (its window straddles the edge): grow back over the same colour
    comp = comp | (ndi.binary_dilation(comp, iterations=4) & raw[surface] & inside & ~roof)
    area = float(comp.sum()) * mpp * mpp
    ys, xs = np.nonzero(comp)
    edge = comp & ~ndi.binary_erosion(comp)
    ey, ex = np.nonzero(edge)
    pts = [layout.to_meters(frame, *geo.to_latlon(x + 0.5, y + 0.5)) for x, y in zip(ex[::2], ey[::2])]
    box = layout.box_of_points(pts, area)
    if box is None:
        return None
    yaw = box.yaw_deg
    for gy in grid_yaws:
        for cand in (gy % 180.0, (gy + 90.0) % 180.0):
            diff = (yaw - cand + 90.0) % 180.0 - 90.0
            if abs(diff) <= SNAP_DEG:
                yaw = cand
                break
        else:
            continue
        break
    # the extent along the (snapped) axes from every pixel (_extent): a thin strip that leaks round a court or along a fence is
    # left out (부흥중 2026-10-14: the hull's rectangle took half the basketball court)
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    step = max(1, int(len(xs) / 40000))
    allp = [layout.to_meters(frame, *geo.to_latlon(x + 0.5, y + 0.5)) for x, y in zip(xs[::step], ys[::step])]
    us = np.array([(e - box.cx_m) * c + (n - box.cy_m) * s for e, n in allp])
    vs = np.array([-(e - box.cx_m) * s + (n - box.cy_m) * c for e, n in allp])
    (u0, u1), (v0, v1) = _extent(us), _extent(vs)
    du, dv = (u0 + u1) / 2, (v0 + v1) / 2
    cx, cy = box.cx_m + du * c - dv * s, box.cy_m + du * s + dv * c
    width, depth = float(u1 - u0), float(v1 - v0)
    if depth > width:
        width, depth, yaw = depth, width, (yaw + 90.0) % 180.0
    box = layout.Box(float(cx), float(cy), width, depth, yaw, min(1.0, area / (width * depth)))
    s_ = frame.studs_per_m
    F = layout.fmt
    return {"surface": surface, "x": F(box.cx_m * s_), "z": F(-box.cy_m * s_), "yaw": F(box.yaw_deg), "w": F(box.width_m * s_),
            "d": F(box.depth_m * s_), "fit": F(box.fit_ratio)}


def _extent(values, bin_m: float = 0.5, share: float = 0.5) -> tuple[float, float]:
    """The first and last 0.5 m slice holding at least `share` of the median slice's pixels: the ground's real ends, not a strip."""
    import numpy as np
    lo = float(values.min())
    counts = np.bincount(((values - lo) / bin_m).astype(int))
    full = counts[counts > 0]
    keep = np.nonzero(counts >= share * float(np.median(full)))[0]
    return lo + keep[0] * bin_m, lo + (keep[-1] + 1) * bin_m


# --- the kit's parts -------------------------------------------------------------------------------------------------

def field_items(field: Mapping[str, Any], frame: Frame) -> list[Item]:
    """The parts of one ground: the slab, the pitch lines (outline, halfway line, centre circle) and two goals."""
    s = frame.studs_per_m
    gid = f"field:{field['osm']}"
    x0, z0, yaw, W, Dp = float(field["x"]), float(field["z"]), float(field["yaw"]), float(field["w"]), float(field["d"])
    c, sn = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))

    def at(u: float, v: float) -> tuple[float, float]:  # ground-local studs (u along the long side) -> world x, z (Studio: +Z south)
        return x0 + u * c + v * sn, z0 - u * sn + v * c

    material, cname, color = LOOKS[field["surface"]]
    out: list[Item] = []
    seq = 0

    def part(name: str, u: float, v: float, y: float, size: tuple[float, float, float], look: tuple[str, str, tuple[int, int, int]],
             turn: float = 0.0, collide: bool | None = None) -> None:
        nonlocal seq
        x, z = at(u, v)
        out.append(_item("prop", f"{gid}#{name}", gid, seq, (x, y, z), size, (yaw + turn) % 360.0, None, look[2], material=look[0],
                         color_name=look[1], collide=collide))
        seq += 1

    part("ground", 0, 0, D["top"] - D["slab"] / 2, (W, D["slab"], Dp), (material, cname, color), collide=True)
    inset = D["line_in_m"] * s
    pl, pw = W - 2 * inset, Dp - 2 * inset
    lw, lt, ly = D["line_w"], D["line_t"], D["top"] + D["line_t"] / 2 + 0.01
    if pl > 4 * lw and pw > 4 * lw:
        for name, u, v, size in (("ln", 0, -pw / 2, (pl, lt, lw)), ("ls", 0, pw / 2, (pl, lt, lw)), ("lw", -pl / 2, 0, (lw, lt, pw)),
                                 ("le", pl / 2, 0, (lw, lt, pw)), ("lh", 0, 0, (lw, lt, pw))):
            part(name, u, v, ly, size, LINE, collide=False)
        r = min(D["circle_m"] * s, 0.3 * pw)
        n = int(D["circle_pieces"])
        piece = 2 * r * math.tan(math.pi / n) + lw / 2
        for k in range(n):
            a = 2 * math.pi * (k + 0.5) / n
            part(f"c{k}", r * math.cos(a), r * math.sin(a), ly, (lw, lt, piece), LINE, turn=-math.degrees(a), collide=False)
        if pl / s >= D["goal_min_len_m"]:
            gw_m = min(D["goal_w_m"], 0.25 * pw / s)  # a small school ground gets a small goal
            gw, gh, p = gw_m * s, (D["goal_h_m"] if gw_m >= 5.0 else D["small_goal_h_m"]) * s, D["post"]
            for side in (-1, 1):
                u = side * pl / 2
                for v in (-gw / 2, gw / 2):
                    part(f"g{side}{'ab'[v > 0]}", u, v, D["top"] + gh / 2, (p, gh, p), POST, collide=True)
                part(f"g{side}bar", u, 0, D["top"] + gh + p / 2, (p, p, gw + p), POST, collide=True)
    return out


def load_fields(path: Path) -> list[dict[str, Any]]:
    """The kit grounds of a cell's fields.json (made_by "kit"); none without the file. A bad row refuses the build."""
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))["fields"]
    out = []
    for r in rows:
        if r.get("made_by") != "kit":
            continue
        if not (r.get("surface") in LOOKS and isinstance(r.get("osm"), str) and OSM_ID.fullmatch(r["osm"])
                and all(isinstance(r.get(k), (int, float)) and math.isfinite(r[k]) for k in ("x", "z", "yaw", "w", "d"))
                and r["w"] > 0 and r["d"] > 0):
            raise ValueError(f"{path.name}: bad field row {str(r)[:60]}")
        out.append(r)
    return out


# --- command line ----------------------------------------------------------------------------------------------------

def schools_query(cell_id: str) -> str:
    pts = h3.cell_to_boundary(cell_id)
    s, w, n, e = min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)
    return f'[out:json][timeout:60];(way["amenity"="school"]({s},{w},{n},{e}););out tags geom;'


def manual_osm(region_dir: Path) -> set[str]:
    data = json.loads((region_dir / "manual.json").read_text(encoding="utf-8")) if (region_dir / "manual.json").exists() else {"places": []}
    return {p["osm"] for p in data["places"] if p.get("osm")}


def parse_args(argv: Sequence[str], res: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fields.py", description=__doc__.split("\n")[0])
    parser.add_argument("--cells", nargs="+", metavar="ID", help="H3 cell IDs")
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
        import numpy, PIL, scipy  # noqa: F401
        print("selftest ok: h3, numpy, pillow, scipy and shapely import")
        return 0
    import numpy as np
    from PIL import Image
    from trees import Georef
    conn = db.connect(common.resolve(cfg["db_path"]))
    every = [r[0] for r in conn.execute("select cell_id from cells")]
    buildings = [b for b in db.rows_in_cells(conn, "buildings", every) if b["status"] == "ok"]
    photos = []
    for meta in sorted(common.resolve(SAT_DIR).glob(f"*-z19.json")):
        m = json.loads(meta.read_text(encoding="utf-8"))
        photos.append((Georef(int(m["tile_x0"]), int(m["tile_y0"])), meta.with_suffix(".jpg")))
    for cell_id in args.cells:
        ccfg = common.cell_config(cfg, cell_id)
        frame = Frame.from_cfg(ccfg)
        region_dir = Path(ccfg["cell_dir"]).parent.parent
        manual = manual_osm(region_dir)
        response = common.http_get_json(OVERPASS, {"data": schools_query(cell_id)}, waits=cfg["retry_waits_s"], pause_s=cfg["overpass_pause_s"])
        rows = []
        for el in response.get("elements", []):
            school = [(p["lat"], p["lon"]) for p in el.get("geometry") or []]
            if len(school) < 3:
                continue
            c = (sum(p[0] for p in school) / len(school), sum(p[1] for p in school) / len(school))
            if h3.latlng_to_cell(c[0], c[1], cfg["h3_res"]) != cell_id:
                continue  # a school belongs to the cell of its centre, like a building
            osm = f"way:{el['id']}"
            photo = None
            for geo, jpg in photos:
                with Image.open(jpg) as im:
                    size = im.size
                if all(0 <= x < size[0] and 0 <= y < size[1] for x, y in (geo.to_px(*p) for p in school)):
                    photo = (geo, jpg)
                    break
            if photo is None:
                common.log(logging.WARNING, f"{osm}: no satellite photo holds the whole school; run satellite.py cell first", cell_id)
                continue
            from shapely.geometry import Point, Polygon
            area = Polygon([(p[1], p[0]) for p in school])
            near = [b for b in buildings if area.intersects(Polygon([(p[1], p[0]) for p in b["outline"]]))]
            yaws = []
            for b in sorted(near, key=lambda b: -(b.get("building_area") or 0)):
                if area.covers(Point(b["centroid"][1], b["centroid"][0])):
                    box = layout.outline_to_box([(p[0], p[1]) for p in b["outline"]], frame)
                    if box:
                        yaws.append(box.yaw_deg)
            rgb = np.asarray(Image.open(photo[1]).convert("RGB"))
            ground = find_ground(rgb, photo[0], school, [b["outline"] for b in near], yaws[:3], frame)
            if ground is None:
                common.log(logging.WARNING, f"{osm}: no ground found", cell_id)
                continue
            rows.append({"osm": osm, "name": el.get("tags", {}).get("name", ""), "made_by": "manual" if osm in manual else "kit", **ground})
            common.log(logging.INFO, f"{osm}: {ground['surface']} {ground['w']} x {ground['d']} studs, fit {ground['fit']}", cell_id)
        path = common.cell_file(ccfg, cell_id, "fields")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"cell_id": cell_id, "source": "OSM amenity=school + V-World satellite z19", "fields": rows},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        common.log(logging.INFO, f"{len(rows)} grounds -> {path}", cell_id)
    return 0


if __name__ == "__main__":
    common.run_cli(main, "fields")
