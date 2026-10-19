# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0", "numpy==2.5.4", "pillow==12.3.0"]
# ///
"""Facade tracing (user decision 2026-10-18, replaces the 7-field judgement; aidlc-docs/construction/plans/facade-trace-experiment.md).

Each street-view crop is unfolded onto the wall of its building box that faces the camera (homography of the wall's four
corners) and laid on a 1 m grid; the cell-trace agent (.claude/skills/cycle-build/trace-prompt.md) writes the facade as pieces in
metres; record measures their colours on the photo and keeps only the fronts that pass the check (pieces on edges of the photo,
reaching the wall's top) in regions/<region>/cells/<cell>/facade.json, which build_luau.py lays over the 7-field rule build
(facade_parts.py; mixed, user 2026-10-19). check reports the kept ones (parts per building).

Usage (cycle-build 4T; run build_luau.py once first: the boxes come from data/build/<cell>/chunks.json):
  uv run src/facade.py cell    --cells <cell>     # unfold every pictured building, list files data/facade/<cell>/trace-NN.json
  uv run src/facade.py record  --cells <cell>     # trace-NN.out.json -> facade.json (colours, corners, only fronts that pass)
  uv run src/facade.py check   --cells <cell>     # data/gate/<cell>/trace.json (gate.py summary needs it on a traced cell)
  uv run src/facade.py unfold  --cells <cell> --building gis:N [--corners "x,y x,y x,y x,y" --top-m 10.2]   # one building
  uv run src/facade.py compare --cells <cell> --building gis:N --capture <studio.png> [--before <studio.png>]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import common
import facade_parts as FP
import lookalike as LA

ROOT = Path(__file__).resolve().parent.parent
PX_PER_M = 80  # the crop shows this villa at about 65 px/m; 40 lost the mullions and bars
MARGIN_M = 1.0  # around the face on the unfolded image
ABOVE_M = 3.0  # room for a rooftop room above the face
VERTICAL = (0, 1, 4, 5)  # indexes of lookalike.FACES that are walls


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
    axis, sign = FP.face_of_normal(box, n.tolist())
    return {"origin": a.tolist(), "t": t.tolist(), "n": n.tolist(), "L_m": l_st / spm, "D_m": d_st / spm,
            "H_m": h_st / spm, "corners_px": cam.to_px(cam.to_cam(world)).tolist(), "face": {"axis": axis, "sign": sign}}


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


GATE_DIR = ROOT / "data" / "gate"
BATCH = 10  # buildings per cell-trace agent: two images each, about 20 images (request limit, lessons 2026-10-17 61b)


def chunk_items(cell: str) -> list[dict[str, Any]]:
    chunks = json.loads((ROOT / "data" / "build" / cell / "chunks.json").read_text(encoding="utf-8"))
    return [i for ch in chunks["chunks"] for i in ch["items"]]


def body_boxes(items: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Building id -> its biggest box (the one traced)."""
    out: dict[str, dict[str, Any]] = {}
    for i in items:
        if i["k"] == "building":
            bid = str(i.get("i") or i["n"])
            if bid not in out or i["w"] * i["d"] > out[bid]["w"] * out[bid]["d"]:
                out[bid] = i
    return out


def pairs_of(cell: str) -> dict[str, dict[str, Any]]:
    plan = json.loads((ROOT / "data" / "build" / cell / "review.json").read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for batch in plan["batches"]:
        for p in batch["pairs"]:
            out.setdefault(p["building_id"], p)
    return out


def cmd_cell(cell: str) -> int:
    out = data_dir(cell)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("trace-*.json"):  # lists and answers of an earlier run (record reads every trace-NN.out.json)
        old.unlink()
    items, skipped = [], {}
    for bid in sorted(pairs_of(cell)):
        stem = bid.replace(":", "_")
        try:
            pair, geo, photo, h, size = setup(cell, bid, None, None)
        except SystemExit as e:  # no wall faces the camera, or the box is gone
            skipped[bid] = str(e)
            continue
        draw_grid(unfold_image(photo, h, size), geo, geo["floors"]).save(out / f"{stem}.jpg", quality=92)
        ov = photo.copy()
        ImageDraw.Draw(ov).polygon([tuple(c) for c in geo["corners_px"]], outline=(255, 0, 200), width=3)
        ov.save(out / f"{stem}.outline.jpg", quality=92)
        items.append({"building_id": bid, "image": str((out / f"{stem}.jpg").relative_to(ROOT)),
                      "outline": str((out / f"{stem}.outline.jpg").relative_to(ROOT)),
                      "L_m": round(geo["L_m"], 2), "H_m": round(geo["H_m"], 2), "floors": geo["floors"]})
    lists = []
    for k in range(0, len(items), BATCH):
        n = k // BATCH + 1
        path = out / f"trace-{n:02d}.json"
        path.write_text(json.dumps({"items": items[k:k + BATCH], "output": str((out / f"trace-{n:02d}.out.json").relative_to(ROOT))},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        lists.append(str(path.relative_to(ROOT)))
    (out / "cell.json").write_text(json.dumps({"lists": lists, "skipped": skipped}, indent=1), encoding="utf-8")
    print(json.dumps({"cell": cell, "unfolded": len(items), "lists": lists, "skipped": len(skipped)}))
    return 0


def wall_colour(flat: np.ndarray, geo: Mapping[str, Any], pieces: Sequence[Mapping[str, Any]],
                occluded: Sequence[Mapping[str, Any]], min_pixels: int = 400) -> list[int] | None:
    """The bare wall's colour on the unfolded photo: the wall above the first floor, minus every piece and hidden part (median;
    None when too little shows). It goes to walls.json, which build_luau.py already applies (the 7-field colour is gone)."""
    s, H, L = PX_PER_M, geo["H_m"], geo["L_m"]
    mask = np.zeros(flat.shape[:2], bool)
    y_top, y_low = round(ABOVE_M * s), round((H + ABOVE_M - min(H, H / max(1, geo["floors"]))) * s)
    mask[y_top:y_low, round(MARGIN_M * s):round((L + MARGIN_M) * s)] = True
    for p in [*pieces, *occluded]:
        mask[round((H + ABOVE_M - p["y1"]) * s):round((H + ABOVE_M - p["y0"]) * s),
             max(0, round((p["u0"] + MARGIN_M) * s)):max(0, round((p["u1"] + MARGIN_M) * s))] = False
    px = flat[mask]
    return [int(c) for c in np.median(px, axis=0)] if len(px) >= min_pixels else None


def cmd_record(cell: str) -> int:
    cfg = common.load_config()
    out = data_dir(cell)
    answers: dict[str, dict[str, Any]] = {}
    for f in sorted(out.glob("trace-*.out.json")):
        for b in json.loads(f.read_text(encoding="utf-8")).get("buildings", []):
            answers[str(b["building_id"])] = b
    if not answers:
        raise SystemExit(f"no trace answers in {out} (cell-trace writes trace-NN.out.json)")
    entries: dict[str, dict[str, Any]] = {}
    walls: dict[str, dict[str, Any]] = {}
    unusable = []
    for bid, b in sorted(answers.items()):
        if str(b.get("unusable") or "").strip().lower() == "no building":  # an empty lot: build_luau leaves the record out
            entries[bid] = {"source": "empty"}
            continue
        if b.get("unusable") or not b.get("pieces"):
            unusable.append(bid)
            continue
        pieces = FP.expand(b["pieces"])
        for p in pieces:
            FP.check_piece(p)
        corners = " ".join(f"{x},{y}" for x, y in b["corners_px"]) if b.get("corners_px") else None
        pair, geo, photo, h, size = setup(cell, bid, corners, b.get("top_m") or None)
        flat = np.asarray(unfold_image(photo, h, size))
        pieces = [{**p, "rgb": p.get("rgb") or measure(flat, geo, p)} for p in pieces]
        entries[bid] = {"source": "trace", "face": geo["face"], "L_m": round(geo["L_m"], 3), "H_m": round(geo["H_m"], 3),
                        "floors": geo["floors"], "corners_px": b.get("corners_px"), "top_m": b.get("top_m"), "pieces": pieces}
        if b.get("finish"):
            entries[bid]["finish"] = b["finish"]
        rgb = wall_colour(flat, geo, pieces, b.get("occluded") or [])
        if rgb:
            walls[bid] = {"rgb": rgb, "from": "facade trace (bare wall on the unfolded photo)"}
    # mixed with the 7-field rule build (user 2026-10-19): only a traced front that passes the check replaces the rule front;
    # the others, the unusable photos and the unpictured buildings stay rule-built (no borrowed fronts)
    g = tomllib.loads((ROOT / "gate.toml").read_text(encoding="utf-8"))["trace"]
    weak = []
    for bid, e in sorted(entries.items()):
        if e["source"] != "trace":
            continue
        row = building_check(cell, bid, e, g)
        if row["support"] < g["min_support"] or row["top"] < g["min_top"]:
            weak.append(bid)
            del entries[bid]
            walls.pop(bid, None)
    path = common.cell_file(cfg, cell, "facade")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "buildings": entries}, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    if walls:  # merged into the cell's walls.json (other entries stay)
        wpath = common.cell_file(cfg, cell, "walls")
        old = json.loads(wpath.read_text(encoding="utf-8")) if wpath.exists() else {"walls": {}}
        old.setdefault("walls", {}).update(walls)
        wpath.write_text(json.dumps(old, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"cell": cell, "traced": sum(e["source"] == "trace" for e in entries.values()), "weak_rule_build": weak,
                      "unusable": len(unusable), "empty": sum(e["source"] == "empty" for e in entries.values()), "walls": len(walls),
                      "file": str(path)}))
    return 0


def gradients(flat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    g = flat.astype(float).mean(axis=2)
    return np.abs(np.diff(g, axis=1)), np.abs(np.diff(g, axis=0))


def edge_support(grads: tuple[np.ndarray, np.ndarray], geo: Mapping[str, Any], p: Mapping[str, Any], thresh: float, reach: int = 3) -> float:
    """The share of a piece's outline that runs along an edge of the unfolded photo: brightness changes across the outline
    within `reach` pixels (a window drawn on a blank wall, or a metre off, scores low)."""
    gx, gy = grads
    s, H = PX_PER_M, geo["H_m"]
    x0, x1 = round((p["u0"] + MARGIN_M) * s), round((p["u1"] + MARGIN_M) * s)
    y0, y1 = round((H + ABOVE_M - p["y1"]) * s), round((H + ABOVE_M - p["y0"]) * s)
    hits = total = 0
    for x in (x0, x1):
        for y in range(max(0, y0), min(gx.shape[0], y1), 2):
            lo, hi = max(0, x - reach), min(gx.shape[1], x + reach)
            if hi > lo:
                total += 1
                hits += gx[y, lo:hi].max() > thresh
    for y in (y0, y1):
        for x in range(max(0, x0), min(gy.shape[1], x1), 2):
            lo, hi = max(0, y - reach), min(gy.shape[0], y + reach)
            if hi > lo:
                total += 1
                hits += gy[lo:hi, x].max() > thresh
    return hits / total if total else 0.0


def building_check(cell: str, bid: str, e: Mapping[str, Any], g: Mapping[str, Any]) -> dict[str, Any]:
    """support: the median share of piece outlines on edges of the unfolded photo; top: how near the wall's top the traced
    facade reaches (a grid the box got wrong squashes it, a 13.6 m villa read as 11.5 m, 2026-10-18)."""
    corners = " ".join(f"{x},{y}" for x, y in e["corners_px"]) if e.get("corners_px") else None
    pair, geo, photo, h, size = setup(cell, bid, corners, e.get("top_m") or None)
    grads = gradients(np.asarray(unfold_image(photo, h, size)))
    sup = [edge_support(grads, geo, p, g["edge_threshold"]) for p in e["pieces"]]
    walls_top = [p["y1"] for p in e["pieces"] if p["kind"] != "rooftop_box"]
    return {"support": round(float(np.median(sup)), 3) if sup else 0.0,
            "weak_pieces": [k for k, v in enumerate(sup) if v < g["min_piece_support"]],
            "top": round(max(walls_top) / float(e["H_m"]), 3) if walls_top else 0.0}


def cmd_check(cell: str) -> int:
    cfg = common.load_config()
    spm = float(cfg["studs_per_m"])
    g = tomllib.loads((ROOT / "gate.toml").read_text(encoding="utf-8"))["trace"]
    entries = json.loads(common.cell_file(cfg, cell, "facade").read_text(encoding="utf-8"))["buildings"]
    boxes = body_boxes(chunk_items(cell))
    rows, fails = {}, []
    weak = 0
    for bid, e in sorted(entries.items()):
        if e["source"] == "empty":
            continue
        box = boxes.get(bid)
        if box is None:
            fails.append(f"{bid}:no_box")
            continue
        parts, _ = FP.parts_of(e, box, spm)
        row: dict[str, Any] = {"source": e["source"], "parts": len(parts)}
        if len(parts) > g["max_parts_per_building"]:
            fails.append(f"{bid}:parts_{len(parts)}")
        if e["source"] == "trace":
            row.update(building_check(cell, bid, e, g))
            if row["support"] < g["min_support"] or row["top"] < g["min_top"]:
                weak += 1
        rows[bid] = row
    traced = sum(1 for r in rows.values() if r["source"] == "trace")
    if traced and weak / traced > g["max_weak_rate"]:
        fails.append(f"weak_{weak}_of_{traced}")
    result = {"cell": cell, "pass": not fails, "fail": fails, "traced": traced, "weak": weak, "buildings": rows,
              "at": common.now_iso()}
    path = GATE_DIR / cell / "trace.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(cell, "PASS" if result["pass"] else "FAIL " + ",".join(fails), f"traced={traced} weak={weak}")
    return 0 if result["pass"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("cell", "record", "check", "unfold", "compare"))
    ap.add_argument("--cells", required=True)
    ap.add_argument("--building")
    ap.add_argument("--corners")
    ap.add_argument("--top-m", type=float)
    ap.add_argument("--capture")
    ap.add_argument("--before")
    a = ap.parse_args(argv)
    if a.cmd == "cell":
        return cmd_cell(a.cells)
    if a.cmd == "record":
        return cmd_record(a.cells)
    if a.cmd == "check":
        return cmd_check(a.cells)
    if not a.building:
        ap.error("--building is required")
    out = data_dir(a.cells)
    out.mkdir(parents=True, exist_ok=True)
    stem = a.building.replace(":", "_")
    pair, geo, photo, h, size = setup(a.cells, a.building, a.corners, a.top_m)
    flat = unfold_image(photo, h, size)
    if a.cmd == "unfold":
        draw_grid(flat, geo, geo["floors"]).save(out / f"{stem}.jpg", quality=92)
        ov = photo.copy()
        ImageDraw.Draw(ov).polygon([tuple(c) for c in geo["corners_px"]], outline=(255, 0, 200), width=3)
        ov.save(out / f"{stem}.outline.jpg", quality=92)
        print(out / f"{stem}.jpg", f"L={geo['L_m']:.2f} m H={geo['H_m']:.2f} m floors={geo['floors']}")
        return 0
    # compare: the photo unfolded (with the recorded corners) next to the Studio capture unfolded with the box's own corners
    cfg = common.load_config()
    entry = json.loads(common.cell_file(cfg, a.cells, "facade").read_text(encoding="utf-8"))["buildings"].get(a.building, {})
    pieces = entry.get("pieces", []) if entry.get("source") == "trace" else []
    if entry.get("corners_px"):
        corners = " ".join(f"{x},{y}" for x, y in entry["corners_px"])
        pair, geo, photo, h, size = setup(a.cells, a.building, corners, entry.get("top_m"))
        flat = unfold_image(photo, h, size)
    h_box, _ = unfold_h(geo, geo["corners_px"], None)

    def render_flat(path: str) -> Image.Image:
        return unfold_image(LA.render_of(Path(path), float(pair["crop_fov_h_deg"])), h_box, size)
    tiles = [("photo (unfolded)", draw_pieces(flat, geo, pieces))]
    if a.before:
        tiles.append(("before", render_flat(a.before)))
    after = render_flat(a.capture)
    tiles += [("traced", draw_pieces(after, geo, pieces)), ("50% overlay", draw_pieces(Image.blend(flat, after, 0.5), geo, pieces))]
    w, hh = size
    sheet = Image.new("RGB", (len(tiles) * (w + 10), hh + 28), "white")
    d = ImageDraw.Draw(sheet)
    for k, (label, im) in enumerate(tiles):
        sheet.paste(im, (k * (w + 10), 28))
        d.text((k * (w + 10) + 4, 6), label, fill="black", font=ImageFont.load_default(size=16))
    sheet.save(out / f"{stem}__compare.jpg", quality=92)
    print(out / f"{stem}__compare.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
