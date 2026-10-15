# /// script
# requires-python = ">=3.11"
# dependencies = ["h3==4.5.0", "shapely==2.2.0"]
# ///
"""Detailed models of the facilities the user approved (2026-10-15: "중흥초 본관 ... 1ab 지식산업센터 다 ㄱㄱ") ->
data/build/manual/facilities.json, built in Studio by studio/manual/<region>/Facilities.luau into Manual/Facilities.

Each facility is a spec in regions/<region>/facilities.json (git): the look read off street-view crops, web pages and the satellite
(wall, base, windows, bands, accents, entrance, sign, roof; see the spec there). The shape stays the data's: the V-World outline
cut into boxes (layout_details), floors from the spec. One Model per facility claims its building ids (BuildingId on a
Configuration each), so the Auto building and everything it owns steps aside; settleManual lifts each Model onto the ground.

Usage (repo root): uv run src/facilities.py   (then serve data/build and run Facilities.luau with the JSON, see cycle-build 7)
"""
from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from shapely.geometry import Point

import common
import db
import judgement
import layout
import layout_details as LD
from layout import Frame, Item

SPECS = Path("regions/bucheon-dodang/facilities.json")
OUT = Path("data/build/manual/facilities.json")
FH_DEFAULT = 3.5
TALL = 12  # floors: above this a window grid is a glass band a floor behind full-height piers (few parts)
MAX_COLS = 30
MATERIALS = {"Concrete", "Brick", "Granite", "Marble", "Plaster", "SmoothPlastic", "Glass", "Limestone", "Sandstone", "Metal", "Slate",
             "CeramicTiles", "Fabric", "Wood"}


def _rgb(v: Any, default: Sequence[int] = (200, 200, 200)) -> tuple[int, int, int]:
    if isinstance(v, (list, tuple)) and len(v) == 3 and all(isinstance(c, (int, float)) for c in v):
        return tuple(max(0, min(255, int(c))) for c in v)  # type: ignore[return-value]
    return tuple(default)  # type: ignore[return-value]


def _mat(v: Any, default: str = "Concrete") -> str:
    return v if v in MATERIALS else default


def look(material: Any, rgb: Any, default_rgb: Sequence[int] = (200, 200, 200), **extra: Any) -> dict[str, Any]:
    return dict(material=_mat(material), color=_rgb(rgb, default_rgb), color_name=None, **extra)


class Maker:
    """Parts of one body (one building record) in the facility's look."""

    def __init__(self, frame: Frame, body: LD.Body, spec: Mapping[str, Any], main: bool):
        self.frame, self.body, self.spec, self.main = frame, body, spec, main
        self.items: list[Item] = []

    def wall(self, bi: int, side: str, tail: str, along: float, y: float, out: float, size: tuple[float, float, float], lk: Mapping[str, Any],
             kind: str = "facade") -> None:
        self.items.append(LD._wall_part(self.frame, self.body, bi, side, kind, f"{tail}-{len(self.items)}", len(self.items), along, y, out, size, **lk))

    def box(self, bi: int, tail: str, u: float, v: float, y: float, size: tuple[float, float, float], lk: Mapping[str, Any], yaw: float = 0.0,
            kind: str = "facade") -> None:
        self.items.append(LD._box_part(self.frame, self.body, bi, kind, f"{tail}-{len(self.items)}", len(self.items), u, v, y, size, yaw, **lk))

    # --- where things go
    def faces(self, which: str) -> list[tuple[int, str]]:
        b = self._fronted()
        if which == "all" or b.facing is None:
            return [(bi, s) for bi in range(len(b.boxes)) for s in LD.SIDES
                    if not self.hidden(b, bi, s) and LD.face_of(b.boxes[bi], s).length >= 3.0]
        s = b.facing.side
        side = {"street": s, "back": LD.OPPOSITE[s], "right": LD.NEXT_FACE[s][0], "left": LD.NEXT_FACE[s][2]}.get(which, s)
        if self.spec.get("accents_faces_all_towers"):  # twin towers: the same face of each
            return [(bi, side) for bi in range(len(b.boxes))]
        return [(b.front, side)]

    @staticmethod
    def hidden(b: LD.Body, bi: int, side: str) -> bool:
        """A face mostly inside a sibling box: 3 of 5 points along it, pushed out 0.3 m (2026-10-15: the midpoint alone hid the
        whole 약대초 north wing behind a small annex in front of its middle; windows behind a sibling stay hidden inside it)."""
        if side not in (b.occluded[bi] if bi < len(b.occluded) else ()):
            return False
        box, f = b.boxes[bi], LD.face_of(b.boxes[bi], side)
        sib = [LD._box_poly(x) for i, x in enumerate(b.boxes) if i != bi]
        pts = [LD._world(box, f.c[0] + f.t[0] * f.length * a + f.n[0] * 0.3, f.c[1] + f.t[1] * f.length * a + f.n[1] * 0.3)
               for a in (-0.4, -0.2, 0.0, 0.2, 0.4)]
        return sum(any(p.covers(Point(e, n)) for p in sib) for e, n in pts) >= 3

    COMPASS = {"N": (0.0, 1.0), "E": (1.0, 0.0), "S": (0.0, -1.0), "W": (-1.0, 0.0)}

    def _fronted(self) -> LD.Body:
        """The body with its facing set to the spec's `front` compass side (the photos' entrance side) when there is one."""
        want = self.COMPASS.get(str(self.spec.get("front") or "").upper())
        b = self.body
        if want is None:
            return b
        best = None
        for bi, bx in enumerate(b.boxes):
            for side in LD.SIDES:
                f = LD.face_of(bx, side)
                e0, n0 = LD._world(bx, 0.0, 0.0)
                e1, n1 = LD._world(bx, f.n[0], f.n[1])
                dot = (e1 - e0) * want[0] + (n1 - n0) * want[1]
                ec, nc = LD._world(bx, f.c[0], f.c[1])
                outward = round((ec * want[0] + nc * want[1]) / 5.0)  # the outermost face that way (5 m steps), then the longest
                key = (dot > 0.7, outward if dot > 0.7 else 0, f.length if dot > 0.7 else dot)
                if best is None or key > best[0]:
                    best = (key, bi, side, f.length)
        _, bi, side, length = best  # type: ignore[misc]
        facing = LD.Facing(side, length, 0.0, 0.0, b.facing.feature_id if b.facing else "")
        return dataclasses.replace(b, front=bi, facing=facing)

    # --- the parts
    def make(self) -> list[Item]:
        self.body = self._fronted()
        b, sp = self.body, self.spec
        H, F, fh = b.height_m, b.floors, b.fh
        wall = look(sp.get("wall", {}).get("material"), sp.get("wall", {}).get("rgb"), collide=True)
        for bi, bx in enumerate(b.boxes):
            self.box(bi, "m", 0.0, 0.0, 0.0, (bx.width_m, H, bx.depth_m), wall, kind="building")
        base = sp.get("base") or None
        base_h = 0.0
        if base and base.get("floors"):
            base_h = min(F, int(base["floors"])) * fh
            for bi, bx in enumerate(b.boxes):
                self.box(bi, "bs", 0.0, 0.0, 0.0, (bx.width_m + 0.3, base_h, bx.depth_m + 0.3), look(base.get("material"), base.get("rgb"), collide=True))
        self.windows(base_h)
        self.bands()
        if self.main:
            for a in sp.get("accents") or []:
                self.accent(a)
            self.entrance(sp.get("entrance"))
            self.sign(sp.get("sign"))
        self.roof(sp.get("roof") or {})
        return self.items

    def windows(self, base_h: float) -> None:
        b, w = self.body, self.spec.get("windows") or {}
        kind = w.get("type", "grid")
        if kind == "none" or b.fh < 2.0:
            return
        F, fh, H = b.floors, b.fh, b.height_m
        glass = look("SmoothPlastic", w.get("glass_rgb"), (70, 95, 115), reflectance=0.15)
        frame_lk = look("SmoothPlastic", w.get("frame_rgb"), (230, 230, 228))
        pier = look(self.spec.get("wall", {}).get("material"), self.spec.get("wall", {}).get("rgb"))
        ww, wh, pitch = float(w.get("w_m", 1.8)), min(float(w.get("h_m", 1.5)), fh - 0.8), max(1.2, float(w.get("pitch_m", 2.6)))
        door = self.door_span()
        for bi, side in self.faces("all"):
            L = LD.face_of(b.boxes[bi], side).length
            front = b.facing is not None and (bi, side) == (b.front, b.facing.side)
            if kind == "curtain":
                y0 = base_h if base_h else 0.0
                self.wall(bi, side, "cw", 0.0, y0, 0.06, (L - 0.4, H - y0 - 0.3, 0.1), glass)
                for k in range(max(1, int(y0 / fh)), F):
                    self.wall(bi, side, "cm", 0.0, k * fh, 0.12, (L - 0.4, 0.12, 0.08), frame_lk)
                n = min(MAX_COLS, int(L // 1.6))
                for j in range(1, n):
                    self.wall(bi, side, "cv", L * j / n - L / 2, y0, 0.12, (0.1, H - y0 - 0.3, 0.08), frame_lk)
                continue
            ribbon = kind == "ribbon" or F > TALL
            for k in range(F):
                y = k * fh + 0.9
                if kind != "curtain" and k * fh < base_h and front and k == 0 and door:
                    pass
                if ribbon:
                    spans = [(-L / 2 + 0.5, L / 2 - 0.5)]
                    if front and k == 0 and door:
                        spans = [(s0, s1) for s0, s1 in ((-L / 2 + 0.5, door[0] - 0.3), (door[1] + 0.3, L / 2 - 0.5)) if s1 - s0 > 1.0]
                    for s0, s1 in spans:
                        self.wall(bi, side, "rb", (s0 + s1) / 2, y, 0.06, (s1 - s0, wh, 0.1), glass)
                    continue
                n = min(MAX_COLS, max(1, int((L - 1.0) // pitch)))
                for j in range(n):
                    a = L * (j + 0.5) / n - L / 2
                    if front and k == 0 and door and door[0] - ww / 2 < a < door[1] + ww / 2:
                        continue
                    self.wall(bi, side, "wf", a, y - 0.1, 0.05, (ww + 0.2, wh + 0.2, 0.06), frame_lk)
                    self.wall(bi, side, "w", a, y, 0.09, (ww, wh, 0.06), glass)
            if ribbon and kind == "grid":  # full-height piers between the window columns over the glass bands
                n = min(MAX_COLS, max(2, int(L // pitch)))
                for j in range(1, n):
                    self.wall(bi, side, "wp", L * j / n - L / 2, 0.6, 0.15, (max(0.5, pitch - ww), H - 0.9, 0.12), pier)

    def bands(self) -> None:
        bd = self.spec.get("bands")
        if not bd:
            return
        b = self.body
        lk = look("Concrete", bd.get("rgb"), (180, 176, 168))
        step = 1 if bd.get("every_floor", True) else max(1, b.floors // 3)
        for bi, bx in enumerate(b.boxes):
            for k in range(step, b.floors, step):
                self.box(bi, "bd", 0.0, 0.0, k * b.fh - 0.15, (bx.width_m + 0.25, 0.3, bx.depth_m + 0.25), lk)

    def door_span(self) -> tuple[float, float] | None:
        e = self.spec.get("entrance") if self.main else None
        if not e or self.body.facing is None:
            return None
        L = self.body.facing.length
        w = min(float(e.get("width_m", 3.0)), L - 1.0)
        c = max(-0.5, min(0.5, float(e.get("at", 0.0)))) * (L - w)
        return c - w / 2, c + w / 2

    def accent(self, a: Mapping[str, Any]) -> None:
        b = self.body
        F, fh, H = b.floors, b.fh, b.height_m
        kind = a.get("kind")
        f0 = max(0, min(F, int(a.get("from_floor", 0))))
        f1 = max(f0, min(F, int(a.get("to_floor", F))))
        y0, y1 = f0 * fh, min(H, (f1 + (1 if f1 < F else 0)) * fh)
        lk = look(a.get("material", "SmoothPlastic"), a.get("rgb"), (230, 230, 228))
        if a.get("face") == "roof":
            self.roof_accent(a, lk)
            return
        for bi, side in self.faces(a.get("face", "street")):
            L = LD.face_of(b.boxes[bi], side).length
            wdt = min(float(a.get("width_m", 3.0)), L)
            at = max(-0.5, min(0.5, float(a.get("at", 0.0)))) * (L - wdt)
            if kind in ("glass_strip", "panel"):
                lk2 = look("SmoothPlastic", a.get("rgb"), (90, 140, 170), reflectance=0.2) if kind == "glass_strip" else lk
                if a.get("skin"):  # a change of wall skin: flush, the windows stay on top of it (부흥초 plaster thirds, 2026-10-15)
                    self.wall(bi, side, "ac", at, y0, 0.02, (wdt, max(1.0, y1 - y0), 0.03), lk2)
                else:
                    self.wall(bi, side, "ac", at, y0, 0.35, (wdt, max(1.0, y1 - y0), 0.3), lk2)
            elif kind == "fins":
                p = max(0.8, float(a.get("pitch_m", 1.5)))
                n = min(MAX_COLS, max(1, int(wdt // p)))
                for j in range(n):
                    self.wall(bi, side, "fn", at - wdt / 2 + p * (j + 0.5), y0, 0.5, (0.2, max(1.0, y1 - y0), 0.5), lk)
            elif kind == "stripe":
                for k in range(min(f0, F - 1), min(f1, F - 1) + 1):  # a stripe "on floor F" is the top floor's, not above the roof (중흥고)
                    self.wall(bi, side, "sp", 0.0, k * fh + fh - 0.6, 0.12, (L + 0.1, 0.5, 0.12), lk)
            elif kind == "round_windows":
                dia = max(0.8, min(2.4, fh * 0.65))
                n = max(1, int(wdt // (dia + 1.0)))
                for k in range(f0, max(f0 + 1, f1)):
                    for j in range(n):
                        al = at - wdt / 2 + wdt * (j + 0.5) / n
                        self.wall(bi, side, "rw", al, k * fh + (fh - dia) / 2, 0.15, (dia + 0.3, dia + 0.3, 0.12), dict(lk, shape="Disc"))
                        self.wall(bi, side, "rg", al, k * fh + (fh - dia) / 2 + 0.15, 0.2, (dia, dia, 0.1),
                                  look("SmoothPlastic", (60, 80, 100), reflectance=0.2, shape="Disc"))
            elif kind == "arch":
                glass = look("SmoothPlastic", (70, 100, 125), reflectance=0.2)
                rect = max(1.0, y1 - y0 - wdt / 2)
                self.wall(bi, side, "ar", at, y0, 0.12, (wdt + 0.6, rect, 0.15), lk)
                self.wall(bi, side, "ag", at, y0, 0.2, (wdt, rect, 0.1), glass)
                self.wall(bi, side, "ad", at, y0 + rect - wdt / 2 - 0.3, 0.12, (wdt + 0.6, wdt + 0.6, 0.15), dict(lk, shape="Disc"))
                self.wall(bi, side, "ae", at, y0 + rect - wdt / 2, 0.2, (wdt, wdt, 0.1), dict(glass, shape="Disc"))
            elif kind == "clock":
                y = (f0 + 0.5) * fh - 1.0
                self.wall(bi, side, "ck", at, y, 0.15, (2.2, 2.2, 0.12), look("SmoothPlastic", (245, 245, 240), shape="Disc"))
                self.wall(bi, side, "ch", at, y + 1.05, 0.25, (0.12, 0.9, 0.05), look("SmoothPlastic", (30, 30, 30)))
                self.wall(bi, side, "cm", at + 0.3, y + 1.05, 0.25, (0.6, 0.12, 0.05), look("SmoothPlastic", (30, 30, 30)))

    def roof_accent(self, a: Mapping[str, Any], lk: Mapping[str, Any]) -> None:
        b = self.body
        bi = b.front
        bx = b.boxes[bi]
        side = b.facing.side if b.facing else "f"
        face = LD.face_of(bx, side)
        at = max(-0.5, min(0.5, float(a.get("at", 0.0)))) * face.length
        u = face.c[0] - face.n[0] * 2.0 + face.t[0] * at
        v = face.c[1] - face.n[1] * 2.0 + face.t[1] * at
        if a.get("kind") == "mast":  # a lattice radio mast: red and white sections, a thin pole each
            hm = max(4.0, float(a.get("width_m", 12.0)))
            n = max(2, int(hm // 2.5))
            for k in range(n):
                self.box(bi, "ms", u, v, b.height_m + k * hm / n, (0.6, hm / n, 0.6),
                         look("Metal", (200, 50, 45) if k % 2 == 0 else (240, 240, 236)))
            return
        if a.get("kind") == "tower":  # a square bell tower from the ground at a corner of the front face, a cross on top (약대교회)
            size, ht = float(a.get("size_m", 5.0)), float(a.get("height_m", 24.0))
            wl = self.spec.get("wall", {})
            uc = face.c[0] - face.n[0] * (size / 2) + face.t[0] * at
            vc = face.c[1] - face.n[1] * (size / 2) + face.t[1] * at
            self.box(bi, "tw", uc, vc, 0.0, (size, ht, size), look(wl.get("material"), wl.get("rgb"), collide=True))
            self.box(bi, "tc", uc, vc, ht, (size + 0.6, 0.6, size + 0.6), look("Concrete", (200, 196, 190)))
            self.box(bi, "xv", uc, vc, ht + 0.6, (0.35, 4.0, 0.35), lk)
            self.box(bi, "xh", uc, vc, ht + 2.9, (2.2, 0.35, 0.35), lk, yaw=LD.FACE_YAW[side])
            return
        if a.get("kind") == "cross":
            s = max(1.0, float(a.get("width_m", 2.0)))
            self.box(bi, "xt", u, v, b.height_m, (1.6, 2.5 * s, 1.6), look(self.spec.get("wall", {}).get("material"), self.spec.get("wall", {}).get("rgb")))
            self.box(bi, "xv", u, v, b.height_m + 2.5 * s, (0.35, 1.6 * s, 0.35), lk)
            self.box(bi, "xh", u, v, b.height_m + 2.5 * s + 0.9 * s, (1.1 * s, 0.35, 0.35), lk, yaw=LD.FACE_YAW[side])

    def entrance(self, e: Mapping[str, Any] | None) -> None:
        span = self.door_span()
        if not e or span is None:
            return
        b = self.body
        bi, side = b.front, b.facing.side  # type: ignore[union-attr]
        c, w = (span[0] + span[1]) / 2, span[1] - span[0]
        self.wall(bi, side, "dr", c, 0.0, 0.12, (w, min(3.0, b.fh - 0.3), 0.15), look("SmoothPlastic", (45, 60, 70), reflectance=0.2))
        if e.get("canopy"):
            self.wall(bi, side, "cn", c, min(3.4, b.fh), 2.2, (w + 1.6, 0.3, 2.2), look("Concrete", e.get("canopy_rgb"), (90, 92, 96), collide=True))
        if e.get("steps"):
            for k in range(2):
                self.wall(bi, side, "stp", c, 0.0, 1.2 - 0.4 * k + 0.4, (w + 1.0, 0.18 * (k + 1), 1.2 - 0.4 * k), look("Granite", (160, 158, 152), collide=True))

    def sign(self, s: Mapping[str, Any] | None) -> None:
        if not s or not s.get("text") or self.body.facing is None:
            return
        text = str(s["text"])
        if not __import__("details_rules").SIGN_TEXT.fullmatch(text):
            raise ValueError(f"{self.body.building_id}: sign text not allowed: {text!r}")
        b = self.body
        L = b.facing.length
        w = min(0.7 * L, 1.3 * len(text) + 1.0)
        floor = max(0, min(b.floors - 1, int(s.get("floor", 1))))
        y = floor * b.fh + (b.fh - 1.3) / 2 if floor else min(3.6, b.fh) + 0.4
        if floor == 0 and y + 1.3 > b.fh:
            y = b.fh - 1.4
        self.wall(b.front, b.facing.side, "sg", 0.0, y, 0.25, (w, 1.3, 0.12),
                  dict(look("SmoothPlastic", s.get("bg_rgb"), (40, 50, 70)), text=text, ink=None, faces="F",
                       attrs={"MaxDistance": 500, "Ink": list(_rgb(s.get("ink_rgb"), (255, 255, 255)))}), kind="sign")

    def roof(self, r: Mapping[str, Any]) -> None:
        b = self.body
        H = b.height_m
        feats = set(r.get("features") or [])
        par = look("Concrete", r.get("parapet_rgb") or self.spec.get("wall", {}).get("rgb"), (200, 200, 196), collide=True)
        for bi, bx in enumerate(b.boxes):
            w, d = bx.width_m, bx.depth_m
            if "pitched" in feats:
                pitch = math.tan(math.radians(25)) * (d / 2 + 0.5)
                rl = look("Slate", r.get("top_rgb"), (70, 72, 78))
                self.box(bi, "pr", 0.0, -(d / 2 + 0.5) / 2, H, (w + 1.0, pitch, d / 2 + 0.5), dict(rl, shape="Wedge"))
                self.box(bi, "pr", 0.0, (d / 2 + 0.5) / 2, H, (w + 1.0, pitch, d / 2 + 0.5), dict(rl, shape="Wedge"), yaw=180.0)
                continue
            self.box(bi, "tp", 0.0, 0.0, H - 0.1, (w - 0.1, 0.25, d - 0.1), look("Concrete", r.get("top_rgb"), (120, 120, 118)))
            for i, (su, sv, size) in enumerate(((0, -1, (w + 0.2, 1.0, 0.25)), (0, 1, (w + 0.2, 1.0, 0.25)), (-1, 0, (0.25, 1.0, d)), (1, 0, (0.25, 1.0, d)))):
                self.box(bi, "pp", su * (w / 2 - 0.02), sv * (d / 2 - 0.02), H, size, par)
            if "crown" in feats and r.get("crown"):
                ch = float(r["crown"].get("height_m", 3.0))
                cl = look("SmoothPlastic", r["crown"].get("rgb"), (235, 235, 232))
                for i, (su, sv, size) in enumerate(((0, -1, (w + 0.4, ch, 0.4)), (0, 1, (w + 0.4, ch, 0.4)), (-1, 0, (0.4, ch, d)), (1, 0, (0.4, ch, d)))):
                    self.box(bi, "cr", su * (w / 2), sv * (d / 2), H + 1.0, size, cl)
            if bi != b.front:
                continue
            if "stair_box" in feats and w > 8 and d > 8:
                self.box(bi, "sb", w / 2 - 3.0, d / 2 - 3.0, H, (4.0, 3.0, 4.0), look(self.spec.get("wall", {}).get("material"), self.spec.get("wall", {}).get("rgb")))
            if "tank" in feats and w > 10:
                east, north = LD._world(bx, -w / 2 + 3.0, d / 2 - 3.0)
                self.items.append(LD._part(self.frame, "facade", f"{b.building_id}#tk-{len(self.items)}", b.building_id, len(self.items), east, north, H,
                                           (2.2, 2.2, 2.2), bx.yaw_deg, owner=b.building_id, shape="Cylinder", material="SmoothPlastic",
                                           color=(235, 235, 230), color_name=None))
            if "helipad" in feats:
                dia = min(w, d) * 0.75
                east, north = LD._world(bx, 0.0, 0.0)
                self.items.append(LD._part(self.frame, "facade", f"{b.building_id}#hp-{len(self.items)}", b.building_id, len(self.items), east, north, H + 0.15,
                                           (0.12, dia, dia), bx.yaw_deg, owner=b.building_id, shape="Cylinder", material="SmoothPlastic",
                                           color=(60, 130, 90), color_name=None))
                self.box(bi, "hh", 0.0, 0.0, H + 0.27, (dia * 0.45, 0.06, dia * 0.45),
                         dict(look("SmoothPlastic", (60, 130, 90)), text="H", faces="T", attrs={"MaxDistance": 2000, "Ink": [245, 245, 240]}), kind="sign")
            if "court" in feats and r.get("court"):  # a rooftop futsal court: turf, white lines, a tall net fence (이마트 중동점, 2026-10-15)
                c = r["court"]
                cw, cd = min(float(c.get("w_m", 40)), w - 2), min(float(c.get("d_m", 20)), d - 2)
                cu = max(-1.0, min(1.0, float(c.get("at_u", 0.0)) * 2)) * (w - cw) / 2
                turf = look("SmoothPlastic", c.get("rgb"), (60, 130, 70))
                line = look("SmoothPlastic", (240, 240, 236))
                net = look("Metal", (40, 60, 50), transparency=0.6)
                self.box(bi, "ct", cu, 0.0, H + 0.15, (cw, 0.1, cd), turf)
                for i, (u, v, size) in enumerate(((0, -cd / 2 + 0.4, (cw - 0.8, 0.02, 0.1)), (0, cd / 2 - 0.4, (cw - 0.8, 0.02, 0.1)),
                                                  (-cw / 2 + 0.4, 0, (0.1, 0.02, cd - 0.8)), (cw / 2 - 0.4, 0, (0.1, 0.02, cd - 0.8)), (0, 0, (0.1, 0.02, cd - 0.8)))):
                    self.box(bi, "cl", cu + u, v, H + 0.25, size, line)
                for i, (u, v, size) in enumerate(((0, -cd / 2, (cw, 5.0, 0.05)), (0, cd / 2, (cw, 5.0, 0.05)), (-cw / 2, 0, (0.05, 5.0, cd)), (cw / 2, 0, (0.05, 5.0, cd)))):
                    self.box(bi, "cf", cu + u, v, H + 0.15, size, net)
            if "solar" in feats:
                rows, cols = max(1, int((d - 4) // 2.2)), max(1, int((w - 4) // 1.4))
                rows, cols = min(rows, 6), min(cols, 12)
                for i in range(rows):
                    for j in range(cols):
                        u = -w / 2 + 2 + 1.4 * (j + 0.5)
                        v = -d / 2 + 2 + 2.2 * (i + 0.5)
                        self.box(bi, "sl", u, v, H + 0.2, (1.2, 0.1, 1.9), look("SmoothPlastic", (35, 50, 85), reflectance=0.3))


def towers_on_podium(frame: Frame, body: LD.Body, sp: Mapping[str, Any], lines: Any, cfg: Mapping[str, Any]) -> list[Item]:
    """One outline that is a shop podium with point towers on it (16b 901동·902동): the podium over the whole outline, then `count`
    towers of `size_m` side by side along the largest box's long side, `gap_m` apart, from the podium roof up."""
    t = sp["towers"]
    pf = max(1, int(t.get("podium_floors", 3)))
    fh = body.fh
    podium = dataclasses.replace(body, floors=pf, height_m=pf * fh)
    psp = {**sp, "base": None, "windows": {**(sp.get("windows") or {}), "type": "ribbon"}, "roof": {"parapet_rgb": (sp.get("roof") or {}).get("parapet_rgb")},
           "accents": [a for a in sp.get("accents") or [] if a.get("face") != "roof" and int(a.get("to_floor", 0)) < pf]}
    items = Maker(frame, LD.resolve_body(podium, lines, [], cfg), psp, main=True).make()
    from shapely.ops import unary_union
    hull = unary_union([LD._box_poly(x) for x in body.boxes]).convex_hull  # the whole podium, not its largest piece
    bx = layout.box_of_points(list(hull.exterior.coords)[:-1])
    assert bx is not None
    n, gap = max(1, int(t.get("count", 2))), float(t.get("gap_m", 10.0))
    boxes = []
    if t.get("grid"):  # towers at the corners of the podium, cols x rows (101·103 동: four towers round a courtyard)
        cols, rows = t["grid"]
        tw, td = t.get("size_m", [24.0, 30.0])
        tw, td = min(tw, bx.width_m / cols - 2), min(td, bx.depth_m / rows - 2)
        for i in range(cols):
            for j in range(rows):
                u = (i - (cols - 1) / 2) * (bx.width_m - tw - 4) / max(1, cols - 1) if cols > 1 else 0.0
                v = (j - (rows - 1) / 2) * (bx.depth_m - td - 4) / max(1, rows - 1) if rows > 1 else 0.0
                east, north = LD._world(bx, u, v)
                boxes.append(layout.Box(east, north, tw, td, bx.yaw_deg, 1.0))
        n = len(boxes)
    else:
        size = min(float(t.get("size_m", 25.0)), (bx.width_m - gap * (n - 1)) / n, bx.depth_m)
        for j in range(n):
            u = (j - (n - 1) / 2) * (size + gap)
            east, north = LD._world(bx, u, 0.0)
            boxes.append(layout.Box(east, north, size, size, bx.yaw_deg, 1.0))
    if t.get("list"):  # each tower as read off the satellite: centre (studs), size (m), floors
        boxes = []
        out_items: list[Item] = []
        for j, tw in enumerate(t["list"]):
            east, north = tw["x"] / frame.studs_per_m, -tw["z"] / frame.studs_per_m
            bx1 = layout.Box(east, north, float(tw["w_m"]), float(tw["d_m"]), bx.yaw_deg, 1.0)
            tf = max(1, int(tw.get("floors") or body.floors) - pf)
            one = dataclasses.replace(body, boxes=(bx1,), names=(f"{body.building_id}#t{j}",), floors=tf, height_m=tf * fh, occluded=(),
                                      building_id=body.building_id)
            one = LD.resolve_body(one, lines, [], cfg)
            roof_acc = [a for a in sp.get("accents") or [] if a.get("face") == "roof"] if j == 0 else []  # a mast on the (first) tower's roof
            face_acc = [{**a, "from_floor": max(0, int(a.get("from_floor", 0)) - pf), "to_floor": max(0, int(a.get("to_floor", 0)) - pf)}
                        for a in sp.get("accents") or [] if a.get("face") != "roof" and int(a.get("to_floor", 0)) >= pf]
            tsp1 = {**sp, "base": None, "entrance": None, "sign": None, "accents": roof_acc + face_acc}
            for i in Maker(frame, one, tsp1, main=True).make():
                out_items.append(dataclasses.replace(i, name=i.name.replace("#", f"#t{j}", 1), cy=layout.fmt(i.cy + pf * fh * frame.studs_per_m)))
        return items + out_items
    tf = body.floors - pf
    tower = dataclasses.replace(body, boxes=tuple(boxes), names=tuple(f"{body.building_id}#t{j}" for j in range(n)), floors=tf,
                                height_m=tf * fh, occluded=())
    tower = LD.resolve_body(tower, lines, [], cfg)
    tsp = {**sp, "base": None, "entrance": None, "accents": [{**a, "from_floor": max(0, int(a.get("from_floor", 0)) - pf),
                                                               "to_floor": max(0, int(a.get("to_floor", 0)) - pf)}
                                                              for a in sp.get("accents") or [] if int(a.get("to_floor", 0)) >= pf]}
    lift = pf * fh * frame.studs_per_m
    for i in Maker(frame, tower, {**tsp, "accents_faces_all_towers": True}, main=True).make():
        items.append(dataclasses.replace(i, name=i.name.replace("#", "#tw", 1), cy=layout.fmt(i.cy + lift)))
    return items


def item_row(i: Item) -> dict[str, Any]:
    row: dict[str, Any] = {"n": i.name, "x": i.cx, "y": i.cy, "z": i.cz, "w": i.sx, "h": i.sy, "d": i.sz, "r": i.yaw_deg,
                           "m": i.material, "c": list(i.color)}
    if i.shape != "Block":
        row["p"] = i.shape
    if i.transparency:
        row["tr"] = i.transparency
    if i.reflectance:
        row["rf"] = i.reflectance
    if i.text:
        row["t"], row["f"] = i.text, i.faces or "F"
        row["ink"] = i.attrs.get("Ink", [255, 255, 255])
        row["md"] = i.attrs.get("MaxDistance", 300)
    if i.collide:
        row["l"] = 1
    return row


def build(cfg: Mapping[str, Any], specs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    conn = db.connect(common.resolve(cfg["db_path"]))
    out = []
    for sp in specs:
        cell = sp["cell"]
        cells = list(sp.get("cells") or [cell])  # a facility across a cell border (현대백화점: 1db and 0a7)
        ccfg = common.cell_config(cfg, cell)
        frame = Frame.from_cfg(ccfg)
        rows = {b["building_id"]: b for b in db.rows_in_cells(conn, "buildings", cells)}
        est = {e["building_id"]: e for c in cells for e in db.estimates_in_cell(conn, c)}
        ovr = {k: v for c in cells for k, v in db.overrides_by_building(conn, c).items()}
        det = {k: v for c in cells for k, v in db.details_by_building(conn, c).items()}
        features = [f for f in db.rows_in_cells(conn, "street_features", cells) if f["kind"] in ("road", "path")]
        lines = LD._feature_lines(features, frame, ccfg)
        items: list[Item] = []
        if sp.get("custom") in ("market", "golf"):  # 강남종합시장 arcade, the driving range: Folders like the park
            mod = __import__(sp["custom"])
            out.append({"key": sp["key"], "cell": cell, "claims": sorted(sp.get("claims") or []), "folder": True,
                        "parts": [item_row(i) for i in mod.build(frame, sp["key"])]})
            continue
        if sp.get("custom") == "pxpark":  # 안중근공원: a traced ground layout, a Folder so each part settles on the ground
            import anjunggeun
            out.append({"key": sp["key"], "cell": cell, "claims": [], "folder": True,
                        "parts": [item_row(i) for i in anjunggeun.build(frame, sp["key"])]})
            continue
        if sp.get("custom") in ("sopoong", "factory"):  # 부천종합터미널 소풍 (rotunda, bus bays, footbridge), the big factory in 1a7
            bid = sp["build"][0]
            parts = __import__(sp["custom"]).build(frame, bid, LD._poly_m(rows[bid]["outline"], frame))
            out.append({"key": sp["key"], "cell": cell, "claims": sorted(set(sp["build"]) | set(sp.get("claims") or [])),
                        "parts": [item_row(i) for i in parts]})
            continue
        if sp.get("custom") == "hyundai":
            import hyundai
            polys = {bid: LD._poly_m(rows[bid]["outline"], frame) for bid in list(sp["build"]) + list(sp.get("atrium") or [])}
            for bid in sp["build"]:
                b = rows[bid]
                eff = judgement.effective_building(b, est.get(bid), ovr.get(bid), ccfg)
                body = LD.make_body(b, eff, det.get(bid), None, frame, ccfg)
                body = LD.resolve_body(dataclasses.replace(body, is_body=True), lines, [], ccfg)
                others = [p for k2, p in polys.items() if k2 != bid and p is not None]
                items += hyundai.Store(frame, body, sp.get("per_building", {}).get(bid, {}), others).make()
            for bid in sp.get("atrium") or []:
                items += hyundai.atrium(frame, bid, polys[bid], [polys[k] for k in sp["build"] if polys.get(k) is not None])
            out.append({"key": sp["key"], "cell": cell, "claims": sorted(set(sp["build"]) | set(sp.get("atrium") or []) | set(sp.get("claims") or [])),
                        "parts": [item_row(i) for i in items]})
            continue
        for k, bid in enumerate(sp["build"]):
            b = rows[bid]
            own = sp.get("per_building", {}).get(bid, {})
            spk = {**sp, **own}  # a building's own differences (floors, accents, windows ...) over the facility's look
            eff = judgement.effective_building(b, est.get(bid), ovr.get(bid), ccfg)
            body = LD.make_body(b, eff, det.get(bid), (est.get(bid) or {}).get("note"), frame, ccfg)
            if body is None:
                continue
            floors = int(own.get("floors") or (sp.get("floors") if k == 0 else 0) or body.floors)
            height = float(own.get("height_m") or (sp.get("height_m") if k == 0 else 0) or 0)
            if not height:
                height = body.height_m if floors == body.floors else floors * FH_DEFAULT
            body = dataclasses.replace(body, floors=floors, fh=height / floors, height_m=height, is_body=True)
            body = LD.resolve_body(body, lines, [], ccfg)
            main = k == 0 or "accents" in own or bool(sp.get("accents_everywhere"))
            if k == 0 and sp.get("towers"):
                items += towers_on_podium(frame, body, spk, lines, ccfg)
            else:
                items += Maker(frame, body, spk, main=main).make()
        out.append({"key": sp["key"], "cell": cell, "claims": sorted(set(sp["build"]) | set(sp.get("claims") or [])),
                    "parts": [item_row(i) for i in items]})
    return out


def main(cfg: dict[str, Any]) -> int:
    specs = json.loads(SPECS.read_text(encoding="utf-8"))["facilities"]
    data = build(cfg, specs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"facilities": data}, ensure_ascii=False), encoding="utf-8")
    for f in data:
        print(f"{f['key']}: {len(f['parts'])} parts, claims {len(f['claims'])}")
    print(OUT, f"{OUT.stat().st_size / 1000:.0f} KB")
    return 0


if __name__ == "__main__":
    common.run_cli(main, "facilities")
