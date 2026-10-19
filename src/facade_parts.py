"""Traced facade pieces -> parts (facade tracing, user decision 2026-10-18; aidlc-docs/construction/plans/facade-trace-experiment.md).

No images here (src/facade.py unfolds and measures): build_luau.py reads regions/<region>/cells/<cell>/facade.json and turns each
building's pieces into items on its biggest box. A piece is a rectangle on a wall in metres (u along the wall from the left end
as seen from outside, y up from the bottom of the box). The traced wall is named by the box axis its normal runs along and the
sign; the other three walls get the front's bands, eaves and windows carried round (wrap). A window, door or railing with its
frame, sashes and bars is one unit, built as one Union kit (ServerStorage/Kits/<key>, made by studio/install/facade-kits.luau
before the cell is built); the key is a hash of the unit's parts in its own frame, so the same unit anywhere is the same kit.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

# kind -> (depth out of the wall m, material, transparency); "Glass" is drawn as the rule build draws glass (SmoothPlastic and
# reflectance): Roblox Glass with a photo's dark colour is black (lessons 2026-10-18)
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
FRAMED = ("window", "glass_stair", "door", "shopfront", "bay", "balcony_glazed")
FRAME_M, FRAME_RGB = 0.1, (205, 205, 200)  # aluminium frame around a glass piece
GLASS_REFLECT = 0.25
WRAP_BANDS = ("slab", "band")  # floor bands and eaves go round the corners
SIDES = ("front", "left", "right", "back")
KEEP_TAILS = ("cap", "pl")  # rule parts of a traced box that stay: the roof cap and the plinth (yard parts stay unless in front)
UP = (0.0, 1.0, 0.0)


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def check_piece(p: Mapping[str, Any]) -> None:
    if p.get("kind") not in KINDS:
        raise ValueError(f"not a piece kind: {p.get('kind')!r}")
    if not (p["u0"] < p["u1"] and p["y0"] < p["y1"]):
        raise ValueError(f"empty piece: {p}")
    rgb = p.get("rgb")
    if rgb is not None and not (len(rgb) == 3 and all(isinstance(c, int) and 0 <= c <= 255 for c in rgb)):
        raise ValueError(f"rgb must be three integers 0-255: {p}")


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


def _unit(p: Mapping[str, Any]) -> bool:
    return p["kind"] == "fence_iron" or p["kind"] in FRAMED


def scale(pieces: Sequence[Mapping[str, Any]], ku: float, ky: float) -> list[dict[str, Any]]:
    """Pieces stretched to a box rebuilt a little longer or taller: bands and slabs stretch by ku, ky;
    a window, door or railing keeps its size and moves with its centre, so it stays the same Union kit."""
    out = []
    for p in pieces:
        if _unit(p):
            du = ((p["u0"] + p["u1"]) / 2) * (ku - 1)
            dy = ((p["y0"] + p["y1"]) / 2) * (ky - 1)
            q = {**p, "u0": p["u0"] + du, "u1": p["u1"] + du, "y0": p["y0"] + dy, "y1": p["y1"] + dy}
            if "mullions_u" in p:
                q["mullions_u"] = [u + du for u in p["mullions_u"]]
            if "mullions_y" in p:
                q["mullions_y"] = [y + dy for y in p["mullions_y"]]
            if "bars" in p:
                q["bars"] = {**p["bars"], "y": [y + dy for y in p["bars"].get("y", [])]}
            out.append(q)
            continue
        q = {**p, "u0": p["u0"] * ku, "u1": p["u1"] * ku, "y0": p["y0"] * ky, "y1": p["y1"] * ky}
        if "mullions_u" in p:
            q["mullions_u"] = [u * ku for u in p["mullions_u"]]
        if "mullions_y" in p:
            q["mullions_y"] = [y * ky for y in p["mullions_y"]]
        if "bars" in p:
            q["bars"] = {**p["bars"], "du": p["bars"].get("du", 0.12) * ku, "y": [y * ky for y in p["bars"].get("y", [])]}
        out.append(q)
    return out


def wrap(pieces: Sequence[Mapping[str, Any]], L: float, D: float) -> dict[str, list[dict[str, Any]]]:
    """The front's floor bands, eaves and windows carried round to the walls nobody photographed (user 2026-10-18, option 1):
    a side takes the bands and window rows of the wing next to it (two windows a floor), the back mirrors the two wings."""
    left = [p for p in pieces if p["u1"] <= 0.4 * L]
    right = [p for p in pieces if p["u0"] >= 0.6 * L]

    def plain(p: Mapping[str, Any]) -> bool:
        return p["y0"] > 0.0 and "out_m" not in p

    def side(wing: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for p in wing:
            if not plain(p):
                continue
            if p["kind"] in WRAP_BANDS:
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
        if (plain(p) and p["kind"] in WRAP_BANDS + ("window",)) or (p["kind"] == "fence_iron" and p["y0"] > 0.0):
            q = {**p, "u0": L - p["u1"], "u1": L - p["u0"]}
            if "mullions_u" in p:
                q["mullions_u"] = [L - u for u in p["mullions_u"]]
            back.append(q)
    return {"front": list(pieces), "left": side(left), "right": side(right), "back": back}


# --- the walls of a box ------------------------------------------------------------------------------------------

def axes(box: Mapping[str, Any]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """The box's local X and Z axes (studs), yaw only (CFrame.Angles(0, r, 0)); X runs along w, Z along d."""
    t = math.radians(box.get("r") or 0.0)
    return (math.cos(t), 0.0, -math.sin(t)), (math.sin(t), 0.0, math.cos(t))


def face_of_normal(box: Mapping[str, Any], n: Sequence[float]) -> tuple[str, int]:
    """("x" or "z", +1 or -1): the box axis and sign a wall's outward normal runs along."""
    ax, az = axes(box)
    dx, dz = _dot(ax, n), _dot(az, n)
    return ("x", 1 if dx > 0 else -1) if abs(dx) >= abs(dz) else ("z", 1 if dz > 0 else -1)


def walls(box: Mapping[str, Any], axis: str, sign: int, spm: float) -> dict[str, dict[str, Any]]:
    """side -> {origin (bottom corner on the left as seen from outside), t (along, to the right as seen), n (out), L_m} of the
    four walls, front being (axis, sign); studs. The left wall is the one at the front's u = 0 end."""
    ax, az = axes(box)
    n = _mul(ax if axis == "x" else az, sign)
    L, D = (box["d"], box["w"]) if axis == "x" else (box["w"], box["d"])
    bottom = (box["x"], box["y"] - box["h"] / 2, box["z"])

    def wall(nn, length, depth):
        t = (nn[2], 0.0, -nn[0])  # (-n) x up: a viewer facing the wall has it on the right
        return {"origin": _add(_add(bottom, _mul(nn, depth / 2)), _mul(t, -length / 2)), "t": t, "n": nn, "L_m": length / spm}
    tf = (n[2], 0.0, -n[0])
    return {"front": wall(n, L, D), "back": wall(_mul(n, -1), L, D), "left": wall(_mul(tf, -1), D, L), "right": wall(tf, D, L),
            "_": {"L_m": L / spm, "D_m": D / spm, "H_m": box["h"] / spm}}


# --- pieces -> parts -------------------------------------------------------------------------------------------------

WALL_KINDS = ("brick_stair", "fence_brick", "gate_tiled")  # pieces of the wall's own material (wall_rgb, when an entry has one)


def _parts(p: Mapping[str, Any]) -> list[tuple]:
    """A piece's parts on its wall: (u0, u1, y0, y1, out, depth, material, transparency, rgb, reflectance), metres."""
    depth, mat, tr = KINDS[p["kind"]]
    depth = float(p.get("depth_m", depth))
    out = float(p.get("out_m", 0.0))
    u0, u1, y0, y1 = p["u0"], p["u1"], p["y0"], p["y1"]
    rgb = tuple(p["rgb"])
    frame = tuple(p.get("frame_rgb", FRAME_RGB))
    refl = GLASS_REFLECT if mat == "Glass" else 0.0
    mat = "SmoothPlastic" if mat == "Glass" else mat
    rows: list[tuple] = []

    def grille(a0, a1, b0, b1, du, ys, o, w, c):
        k = max(1, round((a1 - a0) / du))
        for j in range(1, k):
            a = a0 + (a1 - a0) * j / k
            rows.append((a - w / 2, a + w / 2, b0, b1, o, w, "Metal", 0.0, c, 0.0))
        for b in ys:
            rows.append((a0, a1, b - w / 2, b + w / 2, o, w, "Metal", 0.0, c, 0.0))
    if p["kind"] == "fence_iron":  # railing: top rail and bottom rail, thin posts
        rows.append((u0, u1, y1 - 0.06, y1, out, 0.06, "Metal", 0.0, rgb, 0.0))
        grille(u0, u1, y0, y1, float(p.get("du", 0.12)), [y0 + 0.03], out, 0.04, rgb)
        return rows
    if p["kind"] in FRAMED:
        rows.append((u0 - FRAME_M, u1 + FRAME_M, max(0.0, y0 - FRAME_M), y1 + FRAME_M, out, depth * 0.6, "SmoothPlastic", 0.0, frame, 0.0))
    rows.append((u0, u1, y0, y1, out, depth, mat, tr, rgb, refl))
    for u in p.get("mullions_u", []):  # sash and pane frames, a little proud of the glass
        rows.append((u - 0.03, u + 0.03, y0, y1, out, depth + 0.03, "SmoothPlastic", 0.0, frame, 0.0))
    for y in p.get("mullions_y", []):
        rows.append((u0, u1, y - 0.03, y + 0.03, out, depth + 0.03, "SmoothPlastic", 0.0, frame, 0.0))
    if "bars" in p:  # window grille in front of the glass
        b = p["bars"]
        grille(u0, u1, y0, y1, float(b.get("du", 0.12)), b.get("y", []), out + depth + 0.06, 0.03, tuple(b.get("rgb", (95, 97, 100))))
    return rows


def parts_of(entry: Mapping[str, Any], box: Mapping[str, Any], spm: float) -> tuple[list[dict[str, Any]], dict[str, list[list[Any]]]]:
    """A facade.json entry on its box -> (parts, kits). A part is {"pos", "size", "yaw", "material", "rgb", "reflectance",
    "transparency", "kit"} in studs (kit = the Union kit key for a unit, else None); kits = {key: [[x, y, z, sx, sy, sz, material,
    r, g, b, reflectance, transparency], ...]} with each unit's parts around its own centre."""
    face = entry["face"]
    ws = walls(box, face["axis"], int(face["sign"]), spm)
    dims = ws["_"]
    pieces = scale(entry["pieces"], dims["L_m"] / float(entry["L_m"]), dims["H_m"] / float(entry["H_m"]))
    if entry.get("wall_rgb"):
        pieces = [{**p, "rgb": list(entry["wall_rgb"])} if p["kind"] in WALL_KINDS else p for p in pieces]
    by_side = wrap(pieces, dims["L_m"], dims["D_m"]) if entry.get("wrap", True) else {"front": pieces}
    parts: list[dict[str, Any]] = []
    kits: dict[str, list[list[Any]]] = {}
    for side in SIDES:
        w = ws[side]
        o, t, n = w["origin"], w["t"], w["n"]
        yaw = round(math.degrees(math.atan2(-t[2], t[0])) % 360.0, 3)
        for p in by_side.get(side, []):
            rows = _parts(p)
            local = []  # (centre along t, up, n) and size, studs
            for u0, u1, y0, y1, out, depth, mat, tr, rgb, refl in rows:
                local.append(((u0 + u1) / 2 * spm, (y0 + y1) / 2 * spm, (out + depth / 2) * spm,
                              (u1 - u0) * spm, (y1 - y0) * spm, depth * spm, mat, rgb, refl, tr))
            if _unit(p) and len(local) > 1:
                lo = [min(c[i] - c[i + 3] / 2 for c in local) for i in range(3)]
                hi = [max(c[i] + c[i + 3] / 2 for c in local) for i in range(3)]
                mid = [(a + b) / 2 for a, b in zip(lo, hi)]
                # 1e-6 stud: float noise of where the unit sits is far below it, so the same unit hashes alike (a 0.01 rounding
                # put x.xx5 values either way, 2026-10-18)
                shape = [[round(c[0] - mid[0], 6) + 0.0, round(c[1] - mid[1], 6) + 0.0, round(c[2] - mid[2], 6) + 0.0,  # + 0.0: no -0.0
                          round(c[3], 6), round(c[4], 6), round(c[5], 6), c[6], *c[7], c[8], c[9]] for c in local]
                key = "fu-" + hashlib.sha1(json.dumps(shape).encode()).hexdigest()[:12]
                kits[key] = shape
                local = [(mid[0], mid[1], mid[2], hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], "SmoothPlastic", (205, 205, 200), 0.0, 0.0, key)]
            for c in local:
                pos = _add(_add(_add(o, _mul(t, c[0])), _mul(UP, c[1])), _mul(n, c[2]))
                parts.append({"pos": tuple(round(v, 3) for v in pos), "size": (round(c[3], 3), round(c[4], 3), round(c[5], 3)),
                              "yaw": yaw, "material": c[6], "rgb": tuple(c[7]), "reflectance": c[8], "transparency": c[9],
                              "kit": c[10] if len(c) > 10 else None})
    return parts, kits


def keep_rule_part(item: Mapping[str, Any], box: Mapping[str, Any], face: Mapping[str, Any], spm: float, margin_m: float = 1.5) -> bool:
    """Does a rule part of a traced building stay? Parts of the traced box (its footprint plus margin) go, but for the roof cap and
    the plinth; parts of the building's other boxes and its yard stay, but a yard part in front of the traced wall."""
    tail = str(item["name"]).split("#", 1)[1] if "#" in str(item["name"]) else ""
    if item["kind"] in ("building", "roof") or tail.startswith(KEEP_TAILS):
        return True
    ax, az = axes(box)
    rel = (item["x"] - box["x"], 0.0, item["z"] - box["z"])
    lx, lz = _dot(rel, ax), _dot(rel, az)
    m = margin_m * spm
    inside = abs(lx) <= box["w"] / 2 + m and abs(lz) <= box["d"] / 2 + m
    front = walls(box, face["axis"], int(face["sign"]), spm)["front"]
    off = _dot((item["x"] - front["origin"][0], 0.0, item["z"] - front["origin"][2]), front["n"])
    along = _dot((item["x"] - front["origin"][0], 0.0, item["z"] - front["origin"][2]), front["t"])
    in_front = off > -0.5 and -m <= along <= front["L_m"] * spm + m
    if tail.startswith("y"):
        return not in_front
    return not inside
