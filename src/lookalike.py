# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0", "numpy==2.5.4", "pillow==12.3.0"]
# ///
"""U8 G3 look-alike: does each built building look like its street-view photo? (aidlc-docs/construction/plans/u8-auto-expand-plan.md)

Heights and footprints are right (user 2026-10-17); what is checked is whether the building looks like the photo. Every pictured
building of a tier-1 cell is captured in Studio with its crop's camera (review.json from estimate.py plan). The building's boxes
projected through that same camera give its outline in both images, drawn far to near so nearer buildings hide it as they do
in the photo. The pairs go on sheets for the verify agent, who scores six looks from 0 to 2 by
.claude/skills/cycle-verify/lookalike-rubric.md without knowing which slot is what. Canaries hide among the pairs: a photo
next to another building's render (it must score low) and a pair shown twice (it must score the same); a scorer that misses them
is not believed. The wall colour is measured too: the photo's and the render's inside the outline (upper floors, no green, no
sky), their CIEDE2000 difference and the colour that would close it (walls.json, used by build_luau.py).

Usage:
  uv run src/lookalike.py plan --cells <cell>                    # the captures to take, in order -> data/gate/<cell>/g3/plan.json
  uv run src/lookalike.py sheets --cells <cell> --captures <captures.json>   # outlines, colours, sheets with canaries
  uv run src/lookalike.py score --cells <cell> --file <scores.json>          # data/gate/<cell>/g3.json: pass, failed buildings, fixes
  uv run src/lookalike.py walls --cells <cell> [--apply]         # colour fixes of failed buildings -> regions/<region>/cells/<cell>/walls.json
  uv run src/lookalike.py gaps [--min 10]                        # what the map cannot show yet, counted over every scored cell
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import h3
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import common
import gate as G
import review
from estimate import inside

CROP = (1024, 768)  # the street-view crops (capture.py)
SHEET_IMAGE = (512, 384)  # one image of a pair on a sheet
HEADER = 30
NEAR = 0.3  # studs: the near plane faces are cut at
REACH = 700.0  # studs (about 190 m): buildings farther from the camera do not hide anything in a crop that looks 120 m at most
ATTRS = ("color", "finish", "windows", "ground", "extras", "roof")
ROUTES = ("detail", "color", "rule", "facility", "none")
OUTLINE = (255, 0, 200)
# the corners of a box by (x, y, z) sign bits and its six faces as corner loops
FACES = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))


# --- the camera of a crop ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Camera:
    """A pinhole at pos looking at fwd with no roll, the crop's horizontal field of view over w x h pixels (Studio axes)."""
    pos: np.ndarray
    right: np.ndarray
    up: np.ndarray
    fwd: np.ndarray
    f: float
    w: int
    h: int

    def to_cam(self, pts: np.ndarray) -> np.ndarray:
        v = np.asarray(pts, dtype=float) - self.pos
        return np.stack([v @ self.right, v @ self.up, v @ self.fwd], axis=-1)

    def to_px(self, cam: np.ndarray) -> np.ndarray:
        z = cam[..., 2]
        return np.stack([self.w / 2 + self.f * cam[..., 0] / z, self.h / 2 - self.f * cam[..., 1] / z], axis=-1)


def camera_of(pair: Mapping[str, Any], size: tuple[int, int] = CROP) -> Camera:
    pos = np.array(pair["camera"]["position"], dtype=float)
    fwd = np.array(pair["camera"]["look_at"], dtype=float) - pos
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0.0, 1.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    f = (size[0] / 2) / math.tan(math.radians(float(pair["crop_fov_h_deg"])) / 2)
    return Camera(pos, right, up, fwd, f, size[0], size[1])


# --- boxes, faces and the outline of a building ---------------------------------------------------------------------

def box_corners(item: Mapping[str, Any]) -> np.ndarray:
    """The 8 corners (studs) of an item's box, index = 4 * x bit + 2 * y bit + z bit; yaw only (CFrame.Angles(0, r, 0))."""
    t = math.radians(item.get("r") or 0.0)
    ax, az = np.array([math.cos(t), 0.0, -math.sin(t)]), np.array([math.sin(t), 0.0, math.cos(t)])
    c = np.array([item["x"], item["y"], item["z"]], dtype=float)
    w, h, d = (item["w"], item["h"], item["d"]) if item.get("p") != "Cylinder" else (item["h"], item["w"], item["d"])
    out = []
    for sx in (-0.5, 0.5):
        for sy in (-0.5, 0.5):
            for sz in (-0.5, 0.5):
                out.append(c + sx * w * ax + np.array([0.0, sy * h, 0.0]) + sz * d * az)
    return np.array(out)


def clip_near(poly: np.ndarray, near: float = NEAR) -> np.ndarray:
    """A polygon in camera coordinates cut to z >= near (Sutherland-Hodgman)."""
    out = []
    n = len(poly)
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        ia, ib = a[2] >= near, b[2] >= near
        if ia:
            out.append(a)
        if ia != ib:
            t = (near - a[2]) / (b[2] - a[2])
            out.append(a + (b - a) * t)
    return np.array(out) if out else np.zeros((0, 3))


def faces_toward(corners: np.ndarray, cam: Camera) -> list[np.ndarray]:
    """The faces of a box that face the camera, each cut at the near plane and in pixels (a face fully behind it is dropped)."""
    centre = corners.mean(axis=0)
    out = []
    for loop in FACES:
        quad = corners[list(loop)]
        mid = quad.mean(axis=0)
        if np.dot(mid - centre, cam.pos - mid) <= 0:
            continue
        cut = clip_near(cam.to_cam(quad))
        if len(cut) >= 3:
            out.append(cam.to_px(cut))
    return out


def building_parts(items: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    """Building id -> its body boxes and roofs: what makes the outline (facades, signs and props are too small to matter)."""
    out: dict[str, list[Mapping[str, Any]]] = {}
    for i in items:
        if i["k"] in ("building", "roof"):
            out.setdefault(str(i.get("i") or G.root(i["n"])), []).append(i)
    return out


def outline_masks(target: str, parts: Mapping[str, Sequence[Mapping[str, Any]]], cam: Camera) -> tuple[np.ndarray, np.ndarray]:
    """(visible, whole) boolean masks of the target in the crop: every building drawn far to near (painter), then the target alone."""
    boxes = []
    for n, (bid, items) in enumerate(sorted(parts.items())):
        for i in items:
            corners = box_corners(i)
            dist = float(np.linalg.norm(corners.mean(axis=0) - cam.pos))
            if dist <= REACH or bid == target:
                boxes.append((dist, n + 1, bid, corners))
    labels = Image.new("I", (cam.w, cam.h), 0)
    alone = Image.new("L", (cam.w, cam.h), 0)
    draw, draw_alone = ImageDraw.Draw(labels), ImageDraw.Draw(alone)
    target_label = None
    for dist, label, bid, corners in sorted(boxes, key=lambda b: -b[0]):
        for face in faces_toward(corners, cam):
            xy = [(float(x), float(y)) for x, y in face]
            draw.polygon(xy, fill=label)
            if bid == target:
                draw_alone.polygon(xy, fill=255)
                target_label = label
    lab = np.asarray(labels)
    visible = (lab == target_label) if target_label is not None else np.zeros((cam.h, cam.w), bool)
    return visible, np.asarray(alone) > 0


def edge_of(mask: np.ndarray, width: int = 5) -> np.ndarray:
    m = Image.fromarray(mask.astype(np.uint8) * 255)
    return np.asarray(m) > np.asarray(m.filter(ImageFilter.MinFilter(width)))


# --- colour ---------------------------------------------------------------------------------------------------------

def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(np.asarray(c, dtype=float), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055) * 255.0


def srgb_to_lab(rgb: Sequence[float] | np.ndarray) -> np.ndarray:
    """sRGB 0-255 -> CIELAB (D65)."""
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = srgb_to_linear(rgb) @ m.T / np.array([0.95047, 1.0, 1.08883])
    d = 6 / 29
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def de2000(lab1: Sequence[float], lab2: Sequence[float]) -> float:
    """CIEDE2000 colour difference (Sharma, Wu and Dalal 2005)."""
    L1, a1, b1 = (float(v) for v in lab1)
    L2, a2, b2 = (float(v) for v in lab2)
    c7 = ((math.hypot(a1, b1) + math.hypot(a2, b2)) / 2) ** 7
    g = 0.5 * (1 - math.sqrt(c7 / (c7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0
    dlp, dcp = L2 - L1, c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p - h1p > 180 else h2p - h1p + 360
    dHp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2)
    lbp, cbp = (L1 + L2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    else:
        hbp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    rc = 2 * math.sqrt(cbp ** 7 / (cbp ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (lbp - 50) ** 2 / math.sqrt(20 + (lbp - 50) ** 2)
    sc, sh = 1 + 0.045 * cbp, 1 + 0.015 * cbp * t
    rt = -math.sin(math.radians(2 * dtheta)) * rc
    return math.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dHp / sh) ** 2 + rt * (dcp / sc) * (dHp / sh))


def wall_rows(mask: np.ndarray, keep: float = 0.7) -> np.ndarray:
    """The mask less its lowest (1 - keep) rows: the ground floor (shops, awnings, cars, people) is not the wall colour."""
    rows = np.where(mask.any(axis=1))[0]
    if len(rows) == 0:
        return mask
    cut = rows[0] + int((rows[-1] - rows[0] + 1) * keep)
    out = mask.copy()
    out[cut:] = False
    return out


def wall_colour(rgb: np.ndarray, mask: np.ndarray, photo: bool) -> tuple[np.ndarray | None, int]:
    """Median colour of the wall pixels and how many were used: no foliage or sky (photo), the middle of the brightness range
    (windows and shade below, glare above)."""
    px = rgb[mask].astype(float)
    if photo and len(px):
        r, g, b = px[:, 0], px[:, 1], px[:, 2]
        green = (g > r + 12) & (g > b + 6)
        sky = (b > r + 25) & (b > g + 5) & (b > 150)
        px = px[~(green | sky)]
    if len(px) == 0:
        return None, 0
    lum = px @ np.array([0.2126, 0.7152, 0.0722])
    lo, hi = np.percentile(lum, 20), np.percentile(lum, 85)
    px = px[(lum >= lo) & (lum <= hi)]
    return (np.median(px, axis=0) if len(px) else None), int(len(px))


def corrected(current: Sequence[int], photo: Sequence[float], render: Sequence[float], lo: float, hi: float) -> list[int]:
    """The wall colour that would make the render's wall read as the photo's: each channel scaled in linear light by
    photo / render (Studio lights it the same way again), the scale kept inside [lo, hi]."""
    ratio = np.clip(srgb_to_linear(photo) / np.maximum(srgb_to_linear(render), 1e-4), lo, hi)
    return [int(round(v)) for v in np.clip(linear_to_srgb(srgb_to_linear(current) * ratio), 0, 255)]


def measure(photo: np.ndarray, render: np.ndarray, visible: np.ndarray, g: Mapping[str, Any]) -> dict[str, Any] | None:
    m = wall_rows(visible)
    p, n_p = wall_colour(photo, m, True)
    r, n_r = wall_colour(render, m, False)
    if p is None or r is None or min(n_p, n_r) < g["color_min_pixels"]:
        return None
    return {"de": round(de2000(srgb_to_lab(p), srgb_to_lab(r)), 1), "photo": [int(round(v)) for v in p],
            "render": [int(round(v)) for v in r], "pixels": min(n_p, n_r)}


# --- pairs, canaries and sheets -------------------------------------------------------------------------------------

def plan_pairs(review_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every pair of review.json in its own order: the captures the verify agent takes, one at a time (lessons 2026-10-14)."""
    return [p for b in review_plan["batches"] for p in b["pairs"]]


def slot_plan(keys: Sequence[str], seed: str, swaps: int, dups: int) -> list[dict[str, Any]]:
    """Slots S001 ...: every real pair once, `swaps` photos with another pair's render, `dups` pairs a second time; shuffled the
    same way for the same cell (seed) so a rerun shows the same sheets."""
    rng = random.Random(int(hashlib.sha1(seed.encode()).hexdigest()[:12], 16))
    keys = sorted(keys)
    rows: list[dict[str, Any]] = [{"kind": "pair", "key": k} for k in keys]
    if len(keys) >= 2:
        for k in rng.sample(keys, min(swaps, len(keys))):
            other = rng.choice([x for x in keys if x != k])
            rows.append({"kind": "swap", "key": k, "other": other})
    if keys:
        for k in rng.sample(keys, min(dups, len(keys))):
            rows.append({"kind": "dup", "key": k})
    rng.shuffle(rows)
    return [{"slot": f"S{n:03d}", **r} for n, r in enumerate(rows, 1)]


def render_of(capture: Path, fov_h: float) -> Image.Image:
    """The Studio capture cut to the crop's angle and size (review.capture_crop_box): the same pinhole as the photo."""
    with Image.open(capture) as shot:
        box = review.capture_crop_box(shot.width, shot.height, fov_h)
        return shot.convert("RGB").crop(box).resize(CROP, Image.LANCZOS)


def with_outline(im: Image.Image, edge: np.ndarray) -> Image.Image:
    a = np.asarray(im).copy()
    a[edge] = OUTLINE
    return Image.fromarray(a).resize(SHEET_IMAGE, Image.LANCZOS)


def sheet(rows: Sequence[tuple[str, Image.Image, Image.Image]]) -> Image.Image:
    """Pairs under one another: slot id, then photo left and Studio right."""
    w, h = SHEET_IMAGE
    out = Image.new("RGB", (2 * w + 8, len(rows) * (h + HEADER)), "white")
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=18)
    for n, (slot, left, right) in enumerate(rows):
        y = n * (h + HEADER)
        draw.text((6, y + 5), f"{slot}    left: street-view photo    right: Studio (the outlined building)", fill="black", font=font)
        out.paste(left, (0, y + HEADER))
        out.paste(right, (w + 8, y + HEADER))
    return out


# --- scores ----------------------------------------------------------------------------------------------------------

def check_scores(scores: Mapping[str, Any], slots: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """slot -> its answer; every slot answered once, every look 0, 1 or 2, a yes/no for the same building, fixes from ROUTES."""
    want = {s["slot"] for s in slots}
    rows: dict[str, dict[str, Any]] = {}
    for r in scores.get("slots", []):
        slot = str(r.get("slot"))
        if slot in rows:
            raise ValueError(f"{slot} answered twice")
        attrs = r.get("attrs") or {}
        if set(attrs) != set(ATTRS) or not all(isinstance(attrs[a], int) and not isinstance(attrs[a], bool) and 0 <= attrs[a] <= 2 for a in ATTRS):
            raise ValueError(f"{slot}: attrs must give {ATTRS} each as 0, 1 or 2")
        if not isinstance(r.get("same_building"), bool):
            raise ValueError(f"{slot}: same_building must be true or false")
        for f in r.get("fix") or []:
            if f.get("attr") not in ATTRS or f.get("route") not in ROUTES:
                raise ValueError(f"{slot}: a fix needs attr from {ATTRS} and route from {ROUTES}: {f!r}")
        rows[slot] = dict(r)
    if set(rows) != want:
        raise ValueError(f"slots answered {len(rows)}, expected {len(want)}: missing {sorted(want - set(rows))[:5]}, unknown {sorted(set(rows) - want)[:5]}")
    return rows


def total(row: Mapping[str, Any]) -> int:
    return sum(int(row["attrs"][a]) for a in ATTRS)


def canary_report(rows: Mapping[str, Mapping[str, Any]], slots: Sequence[Mapping[str, Any]], g: Mapping[str, Any]) -> dict[str, Any]:
    """Did the scorer catch the canaries? A swap must score at most swap_max_total and not be called the same building; a
    duplicate must score within dup_max_diff of its pair."""
    by_key = {s["key"]: s["slot"] for s in slots if s["kind"] == "pair"}
    missed = []
    for s in slots:
        r = rows[s["slot"]]
        if s["kind"] == "swap" and (total(r) > g["swap_max_total"] or r["same_building"]):
            missed.append({"slot": s["slot"], "kind": "swap", "total": total(r)})
        if s["kind"] == "dup" and abs(total(r) - total(rows[by_key[s["key"]]])) > g["dup_max_diff"]:
            missed.append({"slot": s["slot"], "kind": "dup", "total": total(r), "first": total(rows[by_key[s["key"]]])})
    return {"valid": not missed, "missed": missed, "swaps": sum(s["kind"] == "swap" for s in slots), "dups": sum(s["kind"] == "dup" for s in slots)}


def judge(rows: Mapping[str, Mapping[str, Any]], slots: Sequence[Mapping[str, Any]], pairs: Mapping[str, Mapping[str, Any]],
          colours: Mapping[str, Mapping[str, Any] | None], facilities: set[str], g: Mapping[str, Any]) -> dict[str, Any]:
    """Per building (its pairs averaged: a school has one per face): total, looks, pass; the cell: failed share and fixes."""
    per: dict[str, list[Mapping[str, Any]]] = {}
    keys: dict[str, list[str]] = {}
    for s in slots:
        if s["kind"] == "pair":
            bid = pairs[s["key"]]["building_id"]
            per.setdefault(bid, []).append(rows[s["slot"]])
            keys.setdefault(bid, []).append(s["key"])
    buildings, tickets, gaps = {}, [], {}
    for bid in sorted(per):
        rs = per[bid]
        looks = {a: round(sum(r["attrs"][a] for r in rs) / len(rs), 2) for a in ATTRS}
        tot = round(sum(total(r) for r in rs) / len(rs), 2)
        same = sum(r["same_building"] for r in rs) * 2 >= len(rs)
        facility = bid in facilities
        floor = g["facility_min_total"] if facility else g["min_total"]
        failed = tot < floor or not same or any(looks[a] < 0.5 for a in g["key_attrs"])
        cols = [c for c in (colours.get(k) for k in keys[bid]) if c]
        colour = max(cols, key=lambda c: c["pixels"]) if cols else None  # the view that saw the most wall
        fixes = [dict(f) for r in rs for f in (r.get("fix") or []) if f.get("route") != "none"]
        buildings[bid] = {"total": tot, "looks": looks, "same_building": same, "facility": facility, "fail": failed,
                          "pairs": keys[bid], "color": colour, "notes": [str(r.get("note") or "")[:200] for r in rs]}
        if failed:
            tickets.append({"building": bid, "low": [a for a in ATTRS if looks[a] < 1.5], "fix": fixes[:6],
                            "color": colour if colour and colour["de"] > g["color_de_fail"] and looks["color"] < 1.5 else None})
        for f in fixes:
            if f["route"] == "rule":
                k = f"{f['attr']}: {str(f.get('want') or '').strip()[:80]}"
                gaps.setdefault(k, []).append(bid)
    n = len(buildings)
    failed = [b for b, v in buildings.items() if v["fail"]]
    rate = len(failed) / n if n else 0.0
    bad_facilities = [b for b in failed if buildings[b]["facility"]]
    fails = (["fail_rate"] if rate > g["max_fail_rate"] else []) + (["facilities"] if bad_facilities else [])
    return {"pass": not fails, "fail": fails, "buildings_scored": n, "failed": failed, "fail_rate": round(rate, 3),
            "facilities_failed": bad_facilities, "buildings": buildings, "tickets": tickets,
            "gaps": [{"want": k, "buildings": v} for k, v in sorted(gaps.items(), key=lambda kv: -len(kv[1]))]}


# --- files -----------------------------------------------------------------------------------------------------------

def g3_dir(cell_id: str) -> Path:
    return G.gate_path(cell_id, "g3").parent / "g3"


def review_plan(cell_id: str) -> dict[str, Any]:
    path = common.resolve(G.BUILD_DIR) / cell_id / "review.json"
    if not path.exists():
        raise FileNotFoundError(f"{path}: run estimate.py plan --cells {cell_id} first (it needs the judgements)")
    return json.loads(path.read_text(encoding="utf-8"))


def facility_ids(cfg: Mapping[str, Any], cell_id: str) -> set[str]:
    """Buildings that a facility of the cell's region builds (regions/<region>/facilities.json, `build`)."""
    try:
        folder, _ = common.region_of(cfg, cell_id)
    except ValueError:
        return set()
    path = folder / "facilities.json"
    if not path.exists():
        return set()
    return {str(b) for f in json.loads(path.read_text(encoding="utf-8")).get("facilities", []) for b in f.get("build") or []}


def make_sheets(cfg: Mapping[str, Any], cell_id: str, captures_file: Path, g: Mapping[str, Any]) -> dict[str, Any]:
    """Outlines, colours and the sheets of a cell; writes g3/slots.json (never shown to the scorer) and g3/score-list.json."""
    pairs = {p["key"]: p for p in plan_pairs(review_plan(cell_id))}
    mapping = json.loads(captures_file.read_text(encoding="utf-8"))
    if not (isinstance(mapping, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items())):
        raise ValueError("captures file must map pair keys to capture file paths")
    items = G.cell_items(cell_id) or []
    for c in [c for c in sorted(h3.grid_disk(cell_id, 1)) if c != cell_id]:  # a neighbour's building may stand in front
        items += G.cell_items(c) or []
    parts = building_parts(items)
    captures = common.resolve(cfg["captures_dir"])
    out_dir = g3_dir(cell_id)
    (out_dir / "sheets").mkdir(parents=True, exist_ok=True)
    images: dict[str, tuple[Image.Image, Image.Image]] = {}
    colours: dict[str, Any] = {}
    warnings = []
    for key in sorted(mapping):
        pair = pairs.get(key)
        if pair is None:
            warnings.append(f"{key[:60]}: not a pair of review.json, skipped")
            continue
        try:
            photo = Image.open(inside(captures, pair["crop"])).convert("RGB").resize(CROP)
            render = render_of(Path(mapping[key]), float(pair["crop_fov_h_deg"]))
        except (ValueError, OSError) as e:
            warnings.append(f"{key}: {e}")
            continue
        visible, whole = outline_masks(pair["building_id"], parts, camera_of(pair))
        edge = edge_of(visible if visible.any() else whole)
        images[key] = (with_outline(photo, edge), with_outline(render, edge))
        m = measure(np.asarray(photo), np.asarray(render), visible, g)
        if m is not None:
            m["visible"] = round(float(visible.sum()) / max(1, int(whole.sum())), 2)
        colours[key] = m
    slots = slot_plan(list(images), cell_id, g["canaries_swap"], g["canaries_dup"])
    sheets = []
    per = int(g["pairs_per_sheet"])
    for n in range(0, len(slots), per):
        rows = []
        for s in slots[n:n + per]:
            left, right = images[s["key"]]
            if s["kind"] == "swap":
                right = images[s["other"]][1]
            rows.append((s["slot"], left, right))
        path = out_dir / "sheets" / f"sheet-{n // per + 1:02d}.jpg"
        sheet(rows).save(path, quality=int(cfg["sheet_jpeg_quality"]))
        sheets.append({"sheet": str(path), "slots": [s["slot"] for s in slots[n:n + per]]})
    G.write_json(out_dir / "slots.json", {"cell": cell_id, "slots": slots})
    G.write_json(out_dir / "colours.json", {"cell": cell_id, "colours": colours})
    listing = {"cell": cell_id, "rubric": ".claude/skills/cycle-verify/lookalike-rubric.md", "sheets": sheets,
               "output": str(out_dir / "scores.json")}
    G.write_json(out_dir / "score-list.json", listing)
    return {"pairs": len(images), "slots": len(slots), "sheets": len(sheets), "warnings": warnings, "list": str(out_dir / "score-list.json")}


def score_cell(cfg: Mapping[str, Any], cell_id: str, scores_file: Path, g: Mapping[str, Any]) -> dict[str, Any]:
    out_dir = g3_dir(cell_id)
    slots = json.loads((out_dir / "slots.json").read_text(encoding="utf-8"))["slots"]
    colours = json.loads((out_dir / "colours.json").read_text(encoding="utf-8"))["colours"]
    rows = check_scores(json.loads(scores_file.read_text(encoding="utf-8")), slots)
    pairs = {p["key"]: p for p in plan_pairs(review_plan(cell_id))}
    canaries = canary_report(rows, slots, g)
    result = judge(rows, slots, pairs, colours, facility_ids(cfg, cell_id), g)
    # every pictured building must be on the sheets: captures left out would pass a cell on the easy ones
    planned = {p["building_id"] for p in pairs.values()}
    coverage = result["buildings_scored"] / len(planned) if planned else 1.0
    if coverage < g["min_coverage"]:
        result = {**result, "pass": False, "fail": result["fail"] + ["coverage"]}
    if not canaries["valid"]:  # a scorer that passes a swapped pair or scores one pair two ways: score again with a fresh agent
        result = {**result, "pass": False, "fail": ["scorer_invalid"] + result["fail"]}
    return {"cell": cell_id, "canaries": canaries, "coverage": round(coverage, 3), **result}


def wall_fixes(result: Mapping[str, Any], items: Sequence[Mapping[str, Any]], chunks_walls: Mapping[str, Sequence[int]],
               g: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Building id -> the corrected wall colour, for the failed buildings whose colour look scored low and measured far off."""
    colour_of = {}
    for i in items:
        if i["k"] == "building" and i.get("c") in chunks_walls:
            colour_of.setdefault(str(i.get("i") or G.root(i["n"])), list(chunks_walls[i["c"]]))
    out = {}
    for t in result.get("tickets", []):
        c, bid = t.get("color"), t["building"]
        if c and bid in colour_of:
            out[bid] = {"rgb": corrected(colour_of[bid], c["photo"], c["render"], g["color_ratio_min"], g["color_ratio_max"]),
                        "was": colour_of[bid], "de": c["de"], "from": "U8 G3 photo against render"}
    return out


def all_gaps(gate_dir: Path) -> list[dict[str, Any]]:
    """The scorer's `rule` fixes over every cell's g3.json (the last score of each cell): want -> buildings and cells, most first."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(gate_dir.glob("*/g3.json")):
        for gap in json.loads(path.read_text(encoding="utf-8")).get("gaps", []):
            row = out.setdefault(gap["want"].lower(), {"want": gap["want"], "buildings": 0, "cells": []})
            row["buildings"] += len(gap["buildings"])
            row["cells"].append(path.parent.name)
    return sorted(out.values(), key=lambda r: (-r["buildings"], r["want"]))


def chunk_walls(cell_id: str) -> dict[str, list[int]]:
    path = common.resolve(G.BUILD_DIR) / cell_id / "chunks.json"
    out: dict[str, list[int]] = {}
    for ch in json.loads(path.read_text(encoding="utf-8"))["chunks"]:
        out.update(ch["looks"].get("walls") or {})
    return out


# --- command line ----------------------------------------------------------------------------------------------------

def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="lookalike.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("gaps").add_argument("--min", type=int, default=1)
    for name in ("plan", "sheets", "score", "walls"):
        p = sub.add_parser(name)
        p.add_argument("--cells", nargs=1, required=True)
        if name == "sheets":
            p.add_argument("--captures", required=True, type=Path)
        if name == "score":
            p.add_argument("--file", required=True, type=Path)
        if name == "walls":
            p.add_argument("--apply", action="store_true")
    return ap.parse_args(list(argv))


def main(cfg: dict[str, Any], argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "gaps":  # a rule is due when one kind reaches about 10 buildings over cells (u8 plan section 4)
        for row in all_gaps(common.resolve(G.GATE_DIR)):
            if row["buildings"] >= args.min:
                print(f"{row['buildings']:4d}  {row['want']}  ({len(row['cells'])} cells)")
        return 0
    cell = G._cell_ok(args.cells[0], int(cfg["h3_res"]))
    g = G.load_gate()["g3"]
    if args.command == "plan":
        pairs = plan_pairs(review_plan(cell))
        plan = {"cell": cell, "studio_fov_v_deg": round(review.STUDIO_FOV_V_DEG, 2),
                "captures": [{"key": p["key"], "camera_position": p["camera"]["position"], "look_at_position": p["camera"]["look_at"]} for p in pairs]}
        path = G.write_json(g3_dir(cell) / "plan.json", plan)
        print(f"{len(pairs)} captures -> {path}; set Studio's field of view to {plan['studio_fov_v_deg']}, capture one at a time")
        return 0
    if args.command == "sheets":
        out = make_sheets(cfg, cell, args.captures, g)
        print(f"{out['pairs']} pairs, {out['slots']} slots on {out['sheets']} sheets -> {out['list']}")
        for w in out["warnings"]:
            print("warning:", w)
        return 0
    if args.command == "score":
        out = {"gate": G.gate_digest(), "at": common.now_iso(), **score_cell(cfg, cell, args.file, g)}
        G.write_json(G.gate_path(cell, "g3"), out)
        print(cell, "PASS" if out["pass"] else "FAIL " + ",".join(out["fail"]), f"failed {len(out['failed'])}/{out['buildings_scored']}")
        return 0 if out["pass"] else 1
    result = G.read_part(cell, "g3")
    if result is None:
        raise FileNotFoundError(f"no g3.json for {cell}: score it first")
    fixes = wall_fixes(result, G.cell_items(cell) or [], chunk_walls(cell), g)
    print(json.dumps(fixes, ensure_ascii=False, indent=1))
    if args.apply and fixes:
        path = common.cell_file(cfg, cell, "walls")
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"walls": {}}
        old.setdefault("walls", {}).update(fixes)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(old, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{len(fixes)} wall colours -> {path}")
    return 0


if __name__ == "__main__":
    common.run_cli(main, "lookalike")
