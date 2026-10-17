# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0", "numpy==2.5.4", "pillow==12.3.0"]
# ///
"""Facade tracing experiment (aidlc-docs/construction/plans/facade-trace-experiment.md).

A street-view crop is unfolded onto the front face of its building box (homography of the face's four corners), so the
facade can be traced on a 1 m grid; the traced pieces become parts on that face; the Studio capture from the same camera is
unfolded the same way and laid over the photo.

Usage:
  uv run src/facade.py unfold  --cells <cell> --building gis:N [--corners "x,y x,y x,y x,y" [--top-m 10.2]]
  uv run src/facade.py trace   --cells <cell> --building gis:N --file <pieces.json> [--wrap]   # -> data/facade/<cell>/gis_N.trace.json
                                                                   # (studio/install/facade-trace.luau builds it, windows as Union kits)
  uv run src/facade.py compare --cells <cell> --building gis:N --file <pieces.json> --capture <studio.png> [--before <studio.png>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import common
import lookalike as LA

ROOT = Path(__file__).resolve().parent.parent
PX_PER_M = 80  # the crop shows this villa at about 65 px/m; 40 lost the mullions and bars
MARGIN_M = 1.0  # around the face on the unfolded image
ABOVE_M = 3.0  # room for a rooftop room above the face
VERTICAL = (0, 1, 4, 5)  # indexes of lookalike.FACES that are walls
# kind -> (depth out of the wall m, material, transparency); colour is measured on the photo. "Glass" is drawn as the rule
# build draws glass (SmoothPlastic + reflectance, layout_details.front_items): Roblox Glass with a photo's dark colour is black
FRAMED = ("window", "glass_stair", "door", "shopfront", "bay", "balcony_glazed")
FRAME_M, FRAME_RGB = 0.1, (205, 205, 200)  # aluminium frame around a glass piece
KINDS: dict[str, tuple[float, str, float]] = {
    "window": (0.08, "Glass", 0.0), "glass_stair": (0.3, "Glass", 0.0), "brick_stair": (0.6, "Brick", 0.0),
    "bay": (1.2, "Glass", 0.0), "bay_curved": (1.2, "Glass", 0.0),
    "balcony_open": (1.5, "Metal", 0.0), "balcony_glazed": (1.5, "Glass", 0.0),
    "door": (0.05, "Glass", 0.0), "shopfront": (0.05, "Glass", 0.0), "awning": (1.2, "SmoothPlastic", 0.0),
    "sign": (0.1, "SmoothPlastic", 0.0), "ac_unit": (0.3, "Metal", 0.0),
    "gate": (0.1, "Metal", 0.0), "gate_tiled": (0.3, "Brick", 0.0), "fence_brick": (0.25, "Brick", 0.0), "fence_iron": (0.05, "Metal", 0.0),
    "stone_base": (0.05, "Granite", 0.0), "band": (0.08, "Concrete", 0.0), "panel": (0.03, "Concrete", 0.0),
    "rooftop_box": (3.0, "Concrete", 0.0), "roof_railing": (0.05, "Metal", 0.0), "slab": (0.25, "Concrete", 0.0),
}


def data_dir(cell: str) -> Path:
    return ROOT / "data" / "facade" / cell


def pair_of(cell: str, bid: str) -> dict[str, Any]:
    plan = json.loads((ROOT / "data" / "build" / cell / "review.json").read_text(encoding="utf-8"))
    for batch in plan["batches"]:
        for p in batch["pairs"]:
            if p["building_id"] == bid:
                return p
    raise SystemExit(f"{bid}: no pair in review.json")


def box_of(cell: str, bid: str) -> dict[str, Any]:
    """The building's body box nearest to nothing in particular: the biggest k=building item (one box for a villa)."""
    chunks = json.loads((ROOT / "data" / "build" / cell / "chunks.json").read_text(encoding="utf-8"))
    boxes = [i for ch in chunks["chunks"] for i in ch["items"] if i["k"] == "building" and str(i.get("i") or i["n"]) == bid]
    if not boxes:
        raise SystemExit(f"{bid}: no building item in chunks.json")
    return max(boxes, key=lambda i: i["w"] * i["d"])


def homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """3x3 H with dst ~ H @ src for 4 point pairs (DLT, H[2,2] = 1)."""
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    return np.append(np.linalg.solve(np.array(a, float), np.array(b, float)), 1.0).reshape(3, 3)


def apply_h(h: np.ndarray, pts: np.ndarray) -> np.ndarray:
    p = np.c_[pts, np.ones(len(pts))] @ h.T
    return p[:, :2] / p[:, 2:]


def face_geometry(box: Mapping[str, Any], cam: LA.Camera, spm: float) -> dict[str, Any]:
    """The wall facing the camera with the biggest projected area: its bottom-left (as seen) corner, along/up/out unit vectors
    (studs), length and height in metres, and the four corners in photo pixels (bottom-left, bottom-right, top-right, top-left)."""
    corners = LA.box_corners(box)
    centre = corners.mean(axis=0)
    best = None
    for k in VERTICAL:
        quad = corners[list(LA.FACES[k])]
        mid = quad.mean(axis=0)
        if np.dot(mid - centre, cam.pos - mid) <= 0:
            continue
        cam_q = cam.to_cam(quad)
        if (cam_q[:, 2] <= LA.NEAR).any():
            continue
        px = cam.to_px(cam_q)
        area = 0.5 * abs(np.dot(px[:, 0], np.roll(px[:, 1], 1)) - np.dot(px[:, 1], np.roll(px[:, 0], 1)))
        if best is None or area > best[0]:
            best = (area, quad, mid)
    if best is None:
        raise SystemExit("no wall of the box faces the camera")
    _, quad, mid = best
    bottom = quad[quad[:, 1] < centre[1]]
    a, b = bottom[0], bottom[1]
    if cam.to_px(cam.to_cam(a[None]))[0, 0] > cam.to_px(cam.to_cam(b[None]))[0, 0]:
        a, b = b, a
    t = (b - a) / np.linalg.norm(b - a)
    n = mid - centre
    n[1] = 0.0
    n /= np.linalg.norm(n)
    up = np.array([0.0, 1.0, 0.0])
    h_st = float(box["h"])
    world = np.array([a, b, b + up * h_st, a + up * h_st])
    l_st = float(np.linalg.norm(b - a))
    d_st = float(box["w"] if abs(l_st - box["d"]) < abs(l_st - box["w"]) else box["d"])  # the box's other horizontal side
    return {"origin": a.tolist(), "t": t.tolist(), "n": n.tolist(), "L_m": l_st / spm, "D_m": d_st / spm,
            "H_m": h_st / spm, "corners_px": cam.to_px(cam.to_cam(world)).tolist()}


def unfold_h(geo: Mapping[str, Any], corners_px: Sequence[Sequence[float]], top_m: float | None) -> tuple[np.ndarray, tuple[int, int]]:
    """Homography unfolded-image pixel -> photo pixel, and the unfolded image size."""
    L, H, s = geo["L_m"], geo["H_m"], PX_PER_M
    top = H if top_m is None else top_m
    W_img, H_img = round((L + 2 * MARGIN_M) * s), round((H + ABOVE_M + MARGIN_M) * s)
    def out_px(u: float, y: float) -> tuple[float, float]:
        return (u + MARGIN_M) * s, (H + ABOVE_M - y) * s
    src = np.array([out_px(0, 0), out_px(L, 0), out_px(L, top), out_px(0, top)])
    return homography(src, np.array(corners_px, float)), (W_img, H_img)


def unfold_image(img: Image.Image, h: np.ndarray, size: tuple[int, int]) -> Image.Image:
    return img.convert("RGB").transform(size, Image.PERSPECTIVE, tuple((h / h[2, 2]).ravel()[:8]), Image.BICUBIC)


def draw_grid(im: Image.Image, geo: Mapping[str, Any], floors: int) -> Image.Image:
    im = im.copy()
    d = ImageDraw.Draw(im)
    s, L, H = PX_PER_M, geo["L_m"], geo["H_m"]
    font = ImageFont.load_default(size=13)
    def X(u: float) -> float: return (u + MARGIN_M) * s
    def Y(y: float) -> float: return (H + ABOVE_M - y) * s
    for u in range(0, int(L) + 1):
        d.line([(X(u), 0), (X(u), im.height)], fill=(0, 255, 255), width=1)
        d.text((X(u) + 2, im.height - 16), f"{u}", fill=(255, 255, 0), font=font)
    for y in range(0, int(H + ABOVE_M) + 1):
        d.line([(0, Y(y)), (im.width, Y(y))], fill=(0, 255, 255), width=1)
        d.text((2, Y(y) - 14), f"{y}", fill=(255, 255, 0), font=font)
    fh = H / floors
    for k in range(floors + 1):
        d.line([(X(0), Y(k * fh)), (X(L), Y(k * fh))], fill=(255, 0, 200), width=3)
    d.line([(X(0), Y(0)), (X(0), Y(H))], fill=(255, 0, 200), width=3)
    d.line([(X(L), Y(0)), (X(L), Y(H))], fill=(255, 0, 200), width=3)
    return im


def draw_pieces(im: Image.Image, geo: Mapping[str, Any], pieces: Sequence[Mapping[str, Any]], colour=(255, 255, 0)) -> Image.Image:
    im = im.copy()
    d = ImageDraw.Draw(im)
    s, H = PX_PER_M, geo["H_m"]
    for p in pieces:
        d.rectangle([(p["u0"] + MARGIN_M) * s, (H + ABOVE_M - p["y1"]) * s, (p["u1"] + MARGIN_M) * s, (H + ABOVE_M - p["y0"]) * s],
                    outline=colour, width=2)
    return im


def setup(cell: str, bid: str, corners: str | None, top_m: float | None) -> tuple[dict, dict, Image.Image, np.ndarray, tuple[int, int]]:
    cfg = common.load_config()
    pair, box = pair_of(cell, bid), box_of(cell, bid)
    cam = LA.camera_of(pair)
    geo = face_geometry(box, cam, float(cfg["studs_per_m"]))
    geo["spm"] = float(cfg["studs_per_m"])
    geo["floors"] = int(pair["label"]["floors"] or 1)
    photo = Image.open(ROOT / "captures" / pair["crop"]).convert("RGB")
    cpx = [tuple(map(float, c.split(","))) for c in corners.split()] if corners else geo["corners_px"]
    geo["corners_used"] = [list(c) for c in cpx]
    h, size = unfold_h(geo, cpx, top_m if corners else None)
    return pair, geo, photo, h, size


def measure(photo_flat: np.ndarray, geo: Mapping[str, Any], p: Mapping[str, Any]) -> list[int]:
    """Median colour of the inner 60 % of a piece on the unfolded photo."""
    s, H = PX_PER_M, geo["H_m"]
    du, dy = 0.2 * (p["u1"] - p["u0"]), 0.2 * (p["y1"] - p["y0"])
    x0, x1 = round((p["u0"] + du + MARGIN_M) * s), round((p["u1"] - du + MARGIN_M) * s)
    y0, y1 = round((H + ABOVE_M - p["y1"] + dy) * s), round((H + ABOVE_M - p["y0"] - dy) * s)
    patch = photo_flat[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)].reshape(-1, 3)
    return [int(c) for c in np.median(patch, axis=0)]


def expand(pieces: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """A piece with repeat_dy is that piece again at each height offset (the tracer writes a floor-by-floor repeat once)."""
    out = []
    for p in pieces:
        base = {k: v for k, v in p.items() if k != "repeat_dy"}
        for dy in [0.0, *p.get("repeat_dy", [])]:
            q = {**base, "y0": base["y0"] + dy, "y1": base["y1"] + dy}
            if "mullions_y" in base:
                q["mullions_y"] = [y + dy for y in base["mullions_y"]]
            if "bars" in base:
                q["bars"] = {**base["bars"], "y": [y + dy for y in base["bars"].get("y", [])]}
            out.append(q)
    return out


SIDES = ("front", "left", "right", "back")
WRAP_BANDS = ("slab", "band")  # floor bands and eaves go round the corners
KEEP = ("cap", "pl", "y")  # rule parts kept: roof cap, plinth, yard (a yard part in front of the traced face is hidden)


def faces(geo: Mapping[str, Any]) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
    """side -> (seen-left bottom corner, along, out, length m) of the four walls; front is the traced face, the others are
    named as seen from the front (left = the end at u = 0)."""
    o, t, n, spm = np.array(geo["origin"]), np.array(geo["t"]), np.array(geo["n"]), geo["spm"]
    L, D = geo["L_m"] * spm, geo["D_m"] * spm
    return {"front": (o, t, n, geo["L_m"]), "left": (o - n * D, n, -t, geo["D_m"]),
            "right": (o + t * L, -n, t, geo["D_m"]), "back": (o + t * L - n * D, -t, -n, geo["L_m"])}


def wrap(pieces: Sequence[Mapping[str, Any]], L: float, D: float) -> dict[str, list[dict[str, Any]]]:
    """The front's floor bands, eaves and windows carried round to the walls nobody photographed (user 2026-10-18, option 1):
    a side takes the bands and window rows of the wing next to it (two windows a floor), the back mirrors the two wings."""
    left = [p for p in pieces if p["u1"] <= 0.4 * L]
    right = [p for p in pieces if p["u0"] >= 0.6 * L]
    def plain(p: Mapping[str, Any]) -> bool:
        return p["y0"] > 0.0 and float(p.get("out_m", 0.0)) >= 0.0
    def side(wing: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for p in wing:
            if not plain(p):
                continue
            if p["kind"] in WRAP_BANDS and "out_m" not in p:
                d = float(p.get("depth_m", KINDS[p["kind"]][0]))
                out.append({**p, "u0": -d, "u1": D + d})
            elif p["kind"] == "window":
                w = min(1.4, p["u1"] - p["u0"])
                for c in (D / 3, 2 * D / 3):
                    q = {k: v for k, v in p.items() if k != "mullions_u"}
                    out.append({**q, "u0": c - w / 2, "u1": c + w / 2, "mullions_u": [c]})
        return out
    back = []
    for p in left + right:
        if plain(p) and p["kind"] in WRAP_BANDS + ("window", "fence_iron") and "out_m" not in p or p["kind"] == "fence_iron":
            q = {**p, "u0": L - p["u1"], "u1": L - p["u0"]}
            if "mullions_u" in p:
                q["mullions_u"] = [L - u for u in p["mullions_u"]]
            back.append(q)
    return {"front": list(pieces), "left": side(left), "right": side(right), "back": back}


def trace_rows(geo: Mapping[str, Any], by_side: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[list[Any]]:
    """Parts as [x, y, z, sx, sy, sz, material, transparency, r, g, b, reflectance, face, unit, kit key] (studs). A window,
    door or railing with its frame, sashes and bars is one unit; units with the same key are the same shape (one Union kit)."""
    spm, up = geo["spm"], np.array([0.0, 1.0, 0.0])
    rows: list[list[Any]] = []
    unit = [0]
    for fi, sidename in enumerate(SIDES):
        o, t, n, _ = faces(geo)[sidename]
        for p in by_side.get(sidename, []):
            depth, mat, tr = KINDS[p["kind"]]
            depth = float(p.get("depth_m", depth))
            out = float(p.get("out_m", 0.0))
            u0, u1, y0, y1 = p["u0"], p["u1"], p["y0"], p["y1"]
            rgb = tuple(int(c) for c in p["rgb"])
            frame = tuple(p.get("frame_rgb", FRAME_RGB))
            detailed = p["kind"] == "fence_iron" or p["kind"] in FRAMED
            g, key = 0, ""
            if detailed:
                unit[0] += 1
                g = unit[0]
                shape = {k: p.get(k) for k in ("kind", "mullions_u", "mullions_y", "bars", "du", "depth_m", "rgb", "frame_rgb")}
                shape["mullions_u"] = [round(u - u0, 2) for u in p.get("mullions_u", [])]
                shape["mullions_y"] = [round(y - y0, 2) for y in p.get("mullions_y", [])]
                if shape["bars"]:
                    shape["bars"] = {**shape["bars"], "y": [round(y - y0, 2) for y in shape["bars"].get("y", [])]}
                shape["size"] = [round(u1 - u0, 2), round(y1 - y0, 2)]
                key = "fu-" + hashlib.sha1(json.dumps(shape, sort_keys=True).encode()).hexdigest()[:12]
            def row(a0: float, a1: float, b0: float, b1: float, o_m: float, d_m: float, m: str, tra: float, c: Sequence[int]) -> None:
                pos = o + t * (a0 + a1) / 2 * spm + up * (b0 + b1) / 2 * spm + n * (o_m + d_m / 2) * spm
                rows.append([*(round(float(v), 3) for v in pos), round((a1 - a0) * spm, 3), round((b1 - b0) * spm, 3), round(d_m * spm, 3),
                             "SmoothPlastic" if m == "Glass" else m, tra, *c, 0.25 if m == "Glass" else 0.0, fi + 1, g, key])
            def grille(a0: float, a1: float, b0: float, b1: float, du: float, ys: Sequence[float], o_m: float, w: float, c: Sequence[int]) -> None:
                k = max(1, round((a1 - a0) / du))
                for j in range(1, k):
                    a = a0 + (a1 - a0) * j / k
                    row(a - w / 2, a + w / 2, b0, b1, o_m, w, "Metal", 0.0, c)
                for b in ys:
                    row(a0, a1, b - w / 2, b + w / 2, o_m, w, "Metal", 0.0, c)
            if p["kind"] == "fence_iron":  # railing: top and bottom rail, thin posts
                row(u0, u1, y1 - 0.06, y1, out, 0.06, "Metal", 0.0, rgb)
                grille(u0, u1, y0, y1, float(p.get("du", 0.12)), [y0 + 0.03], out, 0.04, rgb)
                continue
            if p["kind"] in FRAMED:
                row(u0 - FRAME_M, u1 + FRAME_M, max(0.0, y0 - FRAME_M), y1 + FRAME_M, out, depth * 0.6, "SmoothPlastic", 0.0, frame)
            row(u0, u1, y0, y1, out, depth, mat, tr, rgb)
            for u in p.get("mullions_u", []):  # sash and pane frames, a little proud of the glass
                row(u - 0.03, u + 0.03, y0, y1, out, depth + 0.03, "SmoothPlastic", 0.0, frame)
            for y in p.get("mullions_y", []):
                row(u0, u1, y - 0.03, y + 0.03, out, depth + 0.03, "SmoothPlastic", 0.0, frame)
            if "bars" in p:  # window grille in front of the glass
                b = p["bars"]
                grille(u0, u1, y0, y1, float(b.get("du", 0.12)), b.get("y", []), out + depth + 0.06, 0.03, tuple(b.get("rgb", (95, 97, 100))))
    return rows


def trace_payload(bid: str, geo: Mapping[str, Any], by_side: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    fs = faces(geo)
    return {"id": bid, "keep": list(KEEP), "front_o": fs["front"][0].round(3).tolist(), "front_n": fs["front"][2].round(5).tolist(),
            "t": [fs[s][1].round(5).tolist() for s in SIDES], "rows": trace_rows(geo, by_side)}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("unfold", "trace", "compare"))
    ap.add_argument("--wrap", action="store_true", help="carry the front round to the other walls")
    ap.add_argument("--cells", required=True)
    ap.add_argument("--building", required=True)
    ap.add_argument("--corners")
    ap.add_argument("--top-m", type=float)
    ap.add_argument("--file")
    ap.add_argument("--capture")
    ap.add_argument("--before")
    a = ap.parse_args(argv)
    out = data_dir(a.cells)
    out.mkdir(parents=True, exist_ok=True)
    stem = a.building.replace(":", "_")
    spec = json.loads(Path(a.file).read_text(encoding="utf-8")) if a.file else {}
    corners = a.corners or (" ".join(f"{x},{y}" for x, y in spec["corners_px"]) if spec.get("corners_px") else None)
    top_m = a.top_m if a.top_m is not None else spec.get("top_m")
    pair, geo, photo, h, size = setup(a.cells, a.building, corners, top_m)
    flat = unfold_image(photo, h, size)
    if a.cmd == "unfold":
        draw_grid(flat, geo, geo["floors"]).save(out / f"{stem}.jpg", quality=92)
        ov = photo.copy()
        ImageDraw.Draw(ov).polygon([tuple(c) for c in geo["corners_px"]], outline=(255, 0, 200), width=3)
        ov.save(out / f"{stem}.outline.jpg", quality=92)
        (out / f"{stem}.json").write_text(json.dumps({k: geo[k] for k in ("L_m", "H_m", "floors", "corners_px", "corners_used")}
                                                     | {"crop": pair["crop"], "px_per_m": PX_PER_M}, indent=1), encoding="utf-8")
        print(out / f"{stem}.jpg", f"L={geo['L_m']:.2f} m H={geo['H_m']:.2f} m floors={geo['floors']}")
        return 0
    pieces = expand(spec["pieces"])
    for p in pieces:
        if p["kind"] not in KINDS or not (p["u0"] < p["u1"] and p["y0"] < p["y1"]):
            raise SystemExit(f"bad piece {p}")
    if a.cmd == "trace":
        flat_np = np.asarray(flat)
        pieces = [{**p, "rgb": p.get("rgb") or measure(flat_np, geo, p)} for p in pieces]
        by_side = wrap(pieces, geo["L_m"], geo["D_m"]) if a.wrap else {"front": pieces}
        payload = trace_payload(a.building, geo, by_side)
        (out / f"{stem}.trace.json").write_text(json.dumps(payload), encoding="utf-8")
        units = {r[14] for r in payload["rows"] if r[13]}
        print(out / f"{stem}.trace.json", {s: len(v) for s, v in by_side.items()}, len(payload["rows"]), "parts,",
              len({r[13] for r in payload["rows"] if r[13]}), "units,", len(units), "kit shapes")
        return 0
    # compare: the render unfolds with the box's own corners (the render is exactly the box)
    h_box, _ = unfold_h(geo, geo["corners_px"], None)
    def render_flat(path: str) -> Image.Image:
        return unfold_image(LA.render_of(Path(path), float(pair["crop_fov_h_deg"])), h_box, size)
    after = render_flat(a.capture)
    tiles = [("photo (unfolded)", draw_pieces(flat, geo, pieces))]
    if a.before:
        tiles.append(("before: rule build", render_flat(a.before)))
    tiles += [("after: traced", draw_pieces(after, geo, pieces)), ("50% overlay", draw_pieces(Image.blend(flat, after, 0.5), geo, pieces))]
    w, hh = size
    sheet = Image.new("RGB", (len(tiles) * (w + 10), hh + 28), "white")
    d = ImageDraw.Draw(sheet)
    for k, (label, im) in enumerate(tiles):
        sheet.paste(im, (k * (w + 10), 28))
        d.text((k * (w + 10) + 4, 6), label, fill="black", font=ImageFont.load_default(size=16))
    sheet.save(out / f"{stem}__compare.jpg", quality=92)
    crops = [photo.resize((512, 384))] + ([LA.render_of(Path(a.before), float(pair["crop_fov_h_deg"])).resize((512, 384))] if a.before else []) \
        + [LA.render_of(Path(a.capture), float(pair["crop_fov_h_deg"])).resize((512, 384))]
    side = Image.new("RGB", (len(crops) * 516, 384), "white")
    for k, im in enumerate(crops):
        side.paste(im, (k * 516, 0))
    side.save(out / f"{stem}__views.jpg", quality=92)
    print(out / f"{stem}__compare.jpg", out / f"{stem}__views.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
