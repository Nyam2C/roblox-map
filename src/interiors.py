"""U7 D: building interiors. Hollow shell walls, floors, a switchback stairwell (up to the roof on flat roofs), an elevator for
apartments and tall commercial blocks, rooms and furniture kits chosen by building use and sign word, ceiling panels and lights.

No input or output. Every number is computed here in metres in the box-local frame of layout_details (u along the box's long side,
local +X; v along the short side, local +Z; faces f = -Z, b = +Z, l = -X, r = +X) and handed to layout.Item in studs.
Rules: aidlc-docs/construction/u7-interiors/functional-design/business-rules.md (BR-I1 to BR-I16). Variety comes only from
details_rules.pick.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from shapely.geometry import Point

import details_rules as R
from layout import Frame, Item
from layout_details import D, OPPOSITE, SIDES, Body, _box_part, _box_poly, _door_along, _longest_span, _name, _wall_part, _world, face_of

Rect = tuple[float, float, float, float]  # u0, u1, v0, v1 in box-local metres

WALL_T = 0.25          # shell wall (BR-I2)
SLAB_T = 0.2           # floor slab (BR-I5)
LIFT = D["band_h"] / 2 + 0.01  # an upper floor sits just over the facade floor band (a full-footprint slab) so the band hides inside it
PLINTH_LIFT = 0.02     # the ground floor sits just over the plinth's top (no two faces in one plane)
FLIGHT_W = 1.1         # one flight of the switchback; the stairwell is two flights wide (BR-I6)
LANDING = 1.1
STAIR_DEG = (38.0, 45.0)
START_CLEAR = 1.2      # free floor in front of the stairwell's start edge
CORE = 2.0             # elevator core (BR-I7)
DOOR = (1.2, 2.2)      # entrance width, height (BR-I4)
SHOP_DOOR_W = 2.0
GARAGE_DOOR = (2.6, 2.4)
FRAME_T = 0.1
HUT_H, HUT_T = 2.4, 0.2  # roof stair hut (BR-I8)
PARTITION_T = 0.12
GAP = 0.9              # door gap in a partition (BR-I12.4)
MIN_ROOM = 2.5
SAMPLE = 0.25          # sibling-box sampling step along a face (BR-I3)
LIGHT_RANGE_M = 5.0    # PointLight range (BR-I13)
FLOOR_CAP, SCHOOL_FLOOR_CAP = 25, 60  # kit parts per floor (BR-I14)

PALETTE: dict[str, tuple[int, int, int]] = {
    "floor_home": (170, 130, 95), "floor_shop": (215, 215, 210), "floor_school": (150, 165, 150), "floor_concrete": (150, 150, 145),
    "stair": (165, 165, 160), "frame": (90, 70, 55), "wood": (150, 110, 75), "white": (235, 235, 230), "gray": (160, 160, 165),
    "dark": (60, 60, 65), "black": (30, 30, 32), "metal": (175, 175, 180), "fabric_a": (90, 110, 140), "fabric_b": (150, 80, 70),
    "fabric_c": (110, 130, 90), "board": (40, 80, 60), "mirror": (190, 210, 220), "red": (180, 50, 45), "plant": (60, 110, 50),
    "panel": (255, 244, 220), "line": (235, 235, 230), "elevator": (150, 155, 160), "unit_door": (80, 60, 50),
}
FABRICS = ("fabric_a", "fabric_b", "fabric_c")


# --- the plan of one building (BR-I1, BR-I4 to BR-I8) ------------------------------------------------------------------------

@dataclass(frozen=True)
class Stair:
    bi: int
    rect: Rect
    run: str         # "u" or "v": the axis the flights run along
    land: int        # +1 / -1: the landing is at that end of the run axis
    closed: int      # +1 / -1: the long side touching a wall is at that end of the cross axis
    deg: float


@dataclass(frozen=True)
class Plan:
    tier: int
    y0: float                       # top of the ground floor
    levels: tuple[float, ...]       # top of floor k, k = 0 .. F-1
    roof_y: float | None            # the roof floor the stairs reach (flat roofs), else None
    cap: bool                       # the flat roof has the #cap slab (else a ceiling slab at H)
    stair: Stair | None
    core: tuple[int, Rect, str] | None  # (box, rect, side of the rect the door is on)
    door: tuple[float, float, float]  # entrance on the front box's facing face: (along, width, top)
    shop: tuple[float, float] | None    # storefront span on the facing face (along s0, s1)
    covered: tuple[tuple[tuple[str, tuple[tuple[float, float], ...]], ...], ...]  # per box: (side, shared along-intervals)

    def hut(self) -> Rect | None:
        if self.stair is None or self.roof_y is None:
            return None
        u0, u1, v0, v1 = self.stair.rect
        return (u0 - HUT_T, u1 + HUT_T, v0 - HUT_T, v1 + HUT_T)


def wanted(body: Body, cfg: Mapping[str, Any], tier: int) -> bool:
    """BR-I1: tier 1 and 2 cells with interiors on, buildings with a body and a road-facing side."""
    return bool(cfg.get("interiors")) and tier in (1, 2) and body.is_body and body.facing is not None and body.floors >= 1


def flat_roof(body: Body) -> bool:
    return body.archetype == "school" or body.roof_shape not in ("gable", "hip", "shed")


def plan_of(body: Body, cfg: Mapping[str, Any], tier: int = 1) -> Plan | None:
    if not wanted(body, cfg, tier):
        return None
    F, fh, H = body.floors, body.fh, body.height_m
    plinth = body.archetype in ("villa", "public") and not body.shop
    y0 = D["plinth_h"] + PLINTH_LIFT if plinth else 0.15
    if fh - y0 < 2.3:
        y0 = 0.15
    levels = (y0,) + tuple(k * fh + LIFT for k in range(1, F))
    flat = flat_roof(body)
    cap = flat and body.details["rooftop"] != "railing"
    roof_y = (H + D["cap_h"] - D["cap_sink"] if cap else H) if flat else None
    rises = [levels[k + 1] - levels[k] for k in range(F - 1)] + ([roof_y - levels[-1]] if roof_y is not None else [])
    door = _entrance(body)
    shop = None
    if body.shop:
        span = _longest_span(body)
        if span is not None and span[1] - span[0] >= D["span_min"]:
            shop = span
    stair = _place_stair(body, max(rises), door) if rises else None
    core = _place_core(body, stair) if stair is not None and (body.archetype == "apartment" or (body.archetype == "commercial" and F >= 6)) else None
    covered = tuple(tuple((side, tuple(_covered(body, bi, side))) for side in SIDES) for bi in range(len(body.boxes)))
    return Plan(tier, y0, levels, roof_y, cap, stair, core, door, shop, covered)


def _entrance(body: Body) -> tuple[float, float, float]:
    """(along, width, top) of the ground-floor opening on the facing face (BR-I4). A shop without room for a storefront gets a
    plain door."""
    y0 = D["plinth_h"] if body.archetype in ("villa", "public") and not body.shop else 0.15
    if body.shop:
        span = _longest_span(body)
        if span is not None and span[1] - span[0] >= D["span_min"]:
            return (span[0] + D["front_door_along"], SHOP_DOOR_W, body.fh - D["front_drop"] + D["front_y"])
    a = _door_along(body)
    if a is None:
        a = 0.0
    garage = body.details["ground_use"] == "garage" and body.archetype not in ("school", "apartment")
    w, h = GARAGE_DOOR if garage else DOOR
    return (a, w, min(y0 + h, body.fh - 0.3))


def inner(body: Body, bi: int) -> Rect:
    box = body.boxes[bi]
    return (-box.width_m / 2 + WALL_T, box.width_m / 2 - WALL_T, -box.depth_m / 2 + WALL_T, box.depth_m / 2 - WALL_T)


def _local_of(body: Body, bi: int, east: float, north: float) -> tuple[float, float]:
    box = body.boxes[bi]
    t = math.radians(box.yaw_deg)
    dx, dy = east - box.cx_m, north - box.cy_m
    return dx * math.cos(t) + dy * math.sin(t), dx * math.sin(t) - dy * math.cos(t)


def _face_point(body: Body, bi: int, side: str, along: float) -> tuple[float, float]:
    f = face_of(body.boxes[bi], side)
    return f.c[0] + f.t[0] * along, f.c[1] + f.t[1] * along


def _door_world(body: Body, door: tuple[float, float, float] | None) -> tuple[float, float]:
    u, v = _face_point(body, body.front, body.facing.side, door[0] if door else 0.0)  # type: ignore[union-attr]
    return _world(body.boxes[body.front], u, v)


def _rear_side(body: Body, bi: int) -> str:
    """The side of box bi facing away from the road: the one whose outward normal is most opposite the facing face's.
    An apartment's rear is always a long face (f or b), so its corridor runs along the block (BR-I10b)."""
    if bi == body.front and not (body.archetype == "apartment" and body.facing.side in ("l", "r")):  # type: ignore[union-attr]
        return OPPOSITE[body.facing.side]  # type: ignore[union-attr]
    fb = body.boxes[body.front]
    fn = face_of(fb, body.facing.side).n  # type: ignore[union-attr]
    t = math.radians(fb.yaw_deg)
    wn = (fn[0] * math.cos(t) + fn[1] * math.sin(t), fn[0] * math.sin(t) - fn[1] * math.cos(t))
    box = body.boxes[bi]
    tb = math.radians(box.yaw_deg)

    def dot(side: str) -> float:
        n = face_of(box, side).n
        return (n[0] * math.cos(tb) + n[1] * math.sin(tb)) * wn[0] + (n[0] * math.sin(tb) - n[1] * math.cos(tb)) * wn[1]
    sides = ("f", "b") if body.archetype == "apartment" else SIDES
    return min(sides, key=lambda s: (dot(s), SIDES.index(s)))


def _axes(rear: str) -> tuple[str, int]:
    """(axis perpendicular to the rear wall, sign of the rear wall on it)."""
    return {"f": ("v", -1), "b": ("v", 1), "l": ("u", -1), "r": ("u", 1)}[rear]


def _rect(axis_a: str, a0: float, a1: float, b0: float, b1: float) -> Rect:
    """A rect from ranges on axis_a and on the other axis."""
    lo_a, hi_a, lo_b, hi_b = min(a0, a1), max(a0, a1), min(b0, b1), max(b0, b1)
    return (lo_a, hi_a, lo_b, hi_b) if axis_a == "u" else (lo_b, hi_b, lo_a, hi_a)


def _range(r: Rect, axis: str) -> tuple[float, float]:
    return (r[0], r[1]) if axis == "u" else (r[2], r[3])


def _place_stair(body: Body, max_rise: float, door: tuple[float, float, float] | None) -> Stair | None:
    """BR-I6: front box first, then the biggest boxes; 38 degrees, then 45; landing on the rear wall, else on the side wall."""
    order = [body.front] + sorted((i for i in range(len(body.boxes)) if i != body.front),
                                  key=lambda i: (-body.boxes[i].width_m * body.boxes[i].depth_m, i))
    de, dn = _door_world(body, door)
    for deg in STAIR_DEG:
        L = (max_rise / 2) / math.tan(math.radians(deg)) + LANDING
        for bi in order:
            rect = inner(body, bi)
            rear = _rear_side(body, bi)
            perp, rs = _axes(rear)
            par = "v" if perp == "u" else "u"
            p0, p1 = _range(rect, perp)
            q0, q1 = _range(rect, par)
            rear_edge = p1 if rs > 0 else p0
            du, dv = _local_of(body, bi, de, dn)
            door_q = du if par == "u" else dv
            cs = -1 if door_q >= (q0 + q1) / 2 else 1  # the corner end away from the door
            corner = q1 if cs > 0 else q0
            W = 2 * FLIGHT_W
            a_fits = (p1 - p0) >= L + START_CLEAR and (q1 - q0) >= W + 0.5
            b_fits = (q1 - q0) >= L + START_CLEAR and (p1 - p0) >= W + 0.5
            # B first for an apartment: flights along the rear wall keep its corridor narrow (BR-I10b)
            for config in (("B", "A") if body.archetype == "apartment" else ("A", "B")):
                # A: flights perpendicular to the rear wall, landing on it, one long side on the corner's side wall
                if config == "A" and a_fits:
                    return Stair(bi, _rect(perp, rear_edge, rear_edge - rs * L, corner, corner - cs * W), perp, rs, cs, deg)
                # B: flights along the rear wall, landing on the corner's side wall, one long side on the rear wall
                if config == "B" and b_fits:
                    return Stair(bi, _rect(par, corner, corner - cs * L, rear_edge, rear_edge - rs * W), par, cs, rs, deg)
    return None


def _place_core(body: Body, stair: Stair) -> tuple[int, Rect, str] | None:
    """BR-I7: a 2 x 2 m core on the rear wall next to the stairwell, else at the rear wall's other end."""
    bi = stair.bi
    rect = inner(body, bi)
    rear = _rear_side(body, bi)
    perp, rs = _axes(rear)
    par = "v" if perp == "u" else "u"
    p0, p1 = _range(rect, perp)
    q0, q1 = _range(rect, par)
    rear_edge = p1 if rs > 0 else p0
    s0, s1 = _range(stair.rect, par)
    door_side = {("v", -1): "b", ("v", 1): "f", ("u", -1): "r", ("u", 1): "l"}[(perp, rs)]  # the core's face toward the room
    candidates = []
    if stair.run == perp:  # A: the stairwell takes [s0, s1] of the rear wall
        candidates += [(s1, s1 + CORE), (s0 - CORE, s0)]
    candidates += [(q0, q0 + CORE), (q1 - CORE, q1)]
    for c0, c1 in candidates:
        if c0 < q0 - 1e-6 or c1 > q1 + 1e-6 or (p1 - p0) < CORE + START_CLEAR:
            continue
        r = _rect(par, c0, c1, rear_edge, rear_edge - rs * CORE)
        if not _overlap(r, _stair_zone(stair)):
            return (bi, r, door_side)
    return None


def _stair_zone(stair: Stair) -> Rect:
    """The stairwell plus the free floor in front of its start edge."""
    u0, u1, v0, v1 = stair.rect
    if stair.run == "u":
        return (u0 - START_CLEAR, u1, v0, v1) if stair.land > 0 else (u0, u1 + START_CLEAR, v0, v1)
    return (u0, u1, v0 - START_CLEAR, v1) if stair.land > 0 else (u0, u1, v0, v1 + START_CLEAR)


def _overlap(a: Rect, b: Rect, eps: float = 1e-6) -> bool:
    return a[0] < b[1] - eps and b[0] < a[1] - eps and a[2] < b[3] - eps and b[2] < a[3] - eps


def _area(r: Rect) -> float:
    return max(0.0, r[1] - r[0]) * max(0.0, r[3] - r[2])


def rect_minus(r: Rect, hole: Rect) -> list[Rect]:
    """r minus hole as up to four rects: the strips left and right of the hole (full height), then below and above it."""
    if not _overlap(r, hole):
        return [r]
    u0, u1, v0, v1 = r
    hu0, hu1, hv0, hv1 = max(hole[0], u0), min(hole[1], u1), max(hole[2], v0), min(hole[3], v1)
    out = [(u0, hu0, v0, v1), (hu1, u1, v0, v1), (hu0, hu1, v0, hv0), (hu0, hu1, hv1, v1)]
    return [x for x in out if x[1] - x[0] > 0.05 and x[3] - x[2] > 0.05]


def _largest_free(r: Rect, obstacles: Sequence[Rect]) -> Rect | None:
    hit = next((o for o in obstacles if _overlap(r, o)), None)
    if hit is None:
        return r
    strips = [(r[0], hit[0], r[2], r[3]), (hit[1], r[1], r[2], r[3]), (r[0], r[1], r[2], hit[2]), (r[0], r[1], hit[3], r[3])]
    best = None
    for s in strips:
        if s[1] - s[0] < MIN_ROOM or s[3] - s[2] < MIN_ROOM:
            continue
        got = _largest_free(s, obstacles)
        if got is not None and (best is None or _area(got) > _area(best)):
            best = got
    return best


# --- sibling boxes (BR-I3) -------------------------------------------------------------------------------------------------

def _covered(body: Body, bi: int, side: str) -> list[tuple[float, float]]:
    """Along-intervals of a face that touch a sibling box (a point 0.15 m outside lies in it) or lie inside one."""
    if len(body.boxes) == 1:
        return []
    box = body.boxes[bi]
    face = face_of(box, side)
    sib = [_box_poly(b) for i, b in enumerate(body.boxes) if i != bi]
    shrunk = [p.buffer(-0.05) for p in sib]
    L = face.length
    n = max(1, int(L / SAMPLE))
    hits: list[tuple[float, float]] = []
    for j in range(n):
        a = -L / 2 + (j + 0.5) * L / n
        u, v = face.c[0] + face.t[0] * a, face.c[1] + face.t[1] * a
        out = Point(_world(box, u + face.n[0] * 0.15, v + face.n[1] * 0.15))
        on = Point(_world(box, u, v))
        if any(p.covers(out) for p in sib) or any(p.covers(on) for p in shrunk if not p.is_empty):
            lo, hi = a - L / n / 2, a + L / n / 2
            if hits and abs(hits[-1][1] - lo) < 1e-6:
                hits[-1] = (hits[-1][0], hi)
            else:
                hits.append((lo, hi))
    return hits


def _minus(spans: list[tuple[float, float]], cut: tuple[float, float]) -> list[tuple[float, float]]:
    out = []
    for s0, s1 in spans:
        if cut[1] <= s0 or cut[0] >= s1:
            out.append((s0, s1))
            continue
        if cut[0] > s0:
            out.append((s0, cut[0]))
        if cut[1] < s1:
            out.append((cut[1], s1))
    return out


# --- items ---------------------------------------------------------------------------------------------------------------

class _Out:
    """Collects the items of one building with unique names and a running order."""

    def __init__(self, frame: Frame, body: Body) -> None:
        self.frame, self.body, self.items, self.n = frame, body, [], 0

    def _tail(self, code: str) -> str:
        self.n += 1
        return f"i{code}-{self.n}"

    def look(self, color: str) -> dict[str, Any]:
        """Interior colours are sent as in_<name> so they never clash with a wall colour of the same name in a chunk's table."""
        if color in PALETTE:
            return {"color": PALETTE[color], "color_name": f"in_{color}"}
        return {"color": self.body.wall_rgb, "color_name": color}

    def box(self, kind: str, bi: int, code: str, u: float, v: float, y: float, size: tuple[float, float, float], color: str,
            material: str = "SmoothPlastic", yaw_add: float = 0.0, **extra: Any) -> Item:
        item = _box_part(self.frame, self.body, bi, kind, self._tail(code), 5000 + self.n, u, v, y, size, yaw_add, material=material,
                         **self.look(color), **extra)
        self.items.append(item)
        return item

    def rect(self, kind: str, bi: int, code: str, r: Rect, y: float, h: float, color: str, material: str = "SmoothPlastic", **extra: Any) -> Item | None:
        if r[1] - r[0] < 0.05 or r[3] - r[2] < 0.05 or h <= 0:
            return None
        return self.box(kind, bi, code, (r[0] + r[1]) / 2, (r[2] + r[3]) / 2, y, (r[1] - r[0], h, r[3] - r[2]), color, material, **extra)

    def wall(self, bi: int, side: str, code: str, along: float, y: float, length: float, h: float, *, out: float = 0.0, depth: float = WALL_T,
             color: str | None = None, material: str | None = None, kind: str = "wall", min_len: float = 0.1, **extra: Any) -> None:
        if length < min_len - 1e-9 or h <= 0:
            return
        tail = self._tail(code)
        self.items.append(_wall_part(self.frame, self.body, bi, side, kind, tail, 5000 + self.n, along, y, out, (length, h, depth),
                                     material=material or self.body.material, **self.look(color or self.body.wall_color), **extra))


def interior_items(body: Body, plan: Plan | None, frame: Frame) -> list[Item]:
    """All interior items of one building (BR-I2 to BR-I13), in a fixed order. None plan = nothing."""
    if plan is None:
        return []
    o = _Out(frame, body)
    _shell(body, plan, o)
    _entrance_items(body, plan, o)
    _floors(body, plan, o)
    _stairs(body, plan, o)
    _elevator(body, plan, o)
    _rooms(body, plan, o)
    return o.items


def _shell(body: Body, plan: Plan, o: _Out) -> None:
    """BR-I2: walls on every face, minus the sibling intervals, the entrance and the storefront."""
    H = body.height_m
    for bi, box in enumerate(body.boxes):
        covered = dict(plan.covered[bi])
        for side in SIDES:
            face = face_of(box, side)
            L = face.length
            spans = [(-L / 2, L / 2)] if side in ("f", "b") else [(-L / 2 + WALL_T, L / 2 - WALL_T)]
            for c in covered[side]:
                spans = _minus(spans, c)
            holes: list[tuple[float, float, float]] = []  # (a0, a1, top)
            if bi == body.front and side == body.facing.side:  # type: ignore[union-attr]
                if plan.shop is not None:
                    holes.append((plan.shop[0], plan.shop[1], body.fh - D["front_drop"] + D["front_y"]))
                elif plan.door is not None:
                    a, w, top = plan.door
                    holes.append((a - w / 2, a + w / 2, top))
            for s0, s1 in spans:
                pieces = [(s0, s1, 0.0)]
                for h0, h1, top in holes:
                    nxt = []
                    for p0, p1, y in pieces:
                        if y > 0 or h1 <= p0 or h0 >= p1:
                            nxt.append((p0, p1, y))
                            continue
                        if h0 > p0:
                            nxt.append((p0, h0, 0.0))
                        nxt.append((max(p0, h0), min(p1, h1), top))
                        if h1 < p1:
                            nxt.append((h1, p1, 0.0))
                    pieces = nxt
                for p0, p1, y in pieces:
                    o.wall(bi, side, "w", (p0 + p1) / 2, y, p1 - p0, H - y)


def _entrance_items(body: Body, plan: Plan, o: _Out) -> None:
    """BR-I4: door frame (not for a storefront) and two steps up to a plinth floor."""
    if plan.door is None or plan.shop is not None:
        return
    a, w, top = plan.door
    bi, side = body.front, body.facing.side  # type: ignore[union-attr]
    depth = WALL_T + 0.1
    for s in (-1, 1):
        o.wall(bi, side, "df", a + s * (w / 2 - FRAME_T / 2), 0.0, FRAME_T, top, out=0.05, depth=depth, color="frame", material="Wood", min_len=0)
    o.wall(bi, side, "dh", a, top, w + 2 * FRAME_T, FRAME_T, out=0.05, depth=depth, color="frame", material="Wood")
    if plan.y0 > 0.3:
        for i, (h, d) in enumerate(((plan.y0 / 3, 0.6), (2 * plan.y0 / 3, 0.3))):
            o.wall(bi, side, "ds", a, 0.0, w + 0.2, h, out=d, depth=d, color="stair", material="Concrete")


def _floors(body: Body, plan: Plan, o: _Out) -> None:
    """BR-I5: a slab per floor and box (the ground one fills up to y0), split around the stairwell; the ceiling or roof slab."""
    st = plan.stair
    floor_color = {"school": "floor_school"}.get(body.archetype, "floor_home")
    for bi in range(len(body.boxes)):
        base = _slab_rect(body, plan, bi)
        for k, y in enumerate(plan.levels):
            color = "floor_shop" if (k == 0 and (body.shop or body.archetype in ("commercial", "public"))) else \
                "floor_concrete" if (k == 0 and body.details["ground_use"] == "garage") else floor_color
            rects = [base]
            if k > 0 and st is not None and st.bi == bi:
                rects = rect_minus(base, st.rect)
            t = y if k == 0 else SLAB_T
            for r in rects:
                o.rect("wall", bi, f"f{k}", r, y - t, t, color, "WoodPlanks" if color == "floor_home" else "SmoothPlastic", shadow=False)
            if k > 0 and st is not None and st.bi == bi:
                _hole_rail(body, plan, o, y)
        if not plan.cap:  # pitched roof: a ceiling slab; railing roof: the roof slab (with the stair hole)
            rects = [base]
            if plan.roof_y is not None and st is not None and st.bi == bi:
                rects = rect_minus(base, st.rect)
            for r in rects:
                o.rect("wall", bi, "c", r, body.height_m - SLAB_T, SLAB_T, "floor_concrete", "Concrete", shadow=False)


def _slab_rect(body: Body, plan: Plan, bi: int) -> Rect:
    """BR-I3.2: 0.05 in from walled faces, 0.30 out over faces that meet a sibling box."""
    box = body.boxes[bi]
    covered = dict(plan.covered[bi])
    d = {s: (0.30 if covered[s] else -0.05) for s in SIDES}
    return (-box.width_m / 2 - d["l"], box.width_m / 2 + d["r"], -box.depth_m / 2 - d["f"], box.depth_m / 2 + d["b"])


def _hole_rail(body: Body, plan: Plan, o: _Out, y: float) -> None:
    st = plan.stair
    assert st is not None
    cross = "v" if st.run == "u" else "u"
    c0, c1 = _range(st.rect, cross)
    r0, r1 = _range(st.rect, st.run)
    edge = c0 if st.closed > 0 else c1  # the open long side
    t = 0.05
    r = _rect(st.run, r0, r1, edge - t / 2, edge + t / 2)
    o.rect("wall", st.bi, "hr", r, y, 1.0, "metal", "Metal", shadow=False)


def _stairs(body: Body, plan: Plan, o: _Out) -> None:
    """BR-I6, BR-I8: per rise an up flight A (closed half), a landing, an up flight B (open half); the roof hut."""
    st = plan.stair
    if st is None:
        return
    tops = list(plan.levels) + ([plan.roof_y] if plan.roof_y is not None else [])
    cross = "v" if st.run == "u" else "u"
    r0, r1 = _range(st.rect, st.run)
    c0, c1 = _range(st.rect, cross)
    land_end = r1 if st.land > 0 else r0
    start_end = r0 if st.land > 0 else r1
    land_edge = land_end - st.land * LANDING
    closed_mid = (c1 - FLIGHT_W / 2) if st.closed > 0 else (c0 + FLIGHT_W / 2)
    open_mid = (c0 + FLIGHT_W / 2) if st.closed > 0 else (c1 - FLIGHT_W / 2)
    for k in range(len(tops) - 1):
        ya, yb = tops[k], tops[k + 1]
        mid = ya + (yb - ya) / 2
        _flight(body, o, st, start_end, land_edge, closed_mid, ya, mid)
        lr = _rect(st.run, land_edge, land_end, c0, c1)
        o.rect("wall", st.bi, "sl", lr, mid - SLAB_T, SLAB_T, "stair", "Concrete", shadow=False)
        _flight(body, o, st, land_edge, start_end, open_mid, mid, yb)
    if plan.roof_y is not None:
        _hut(body, plan, o, open_mid)


def _flight(body: Body, o: _Out, st: Stair, a0: float, a1: float, c: float, ya: float, yb: float) -> None:
    """A pitched slab from run-coordinate a0 (height ya) to a1 (height yb), centred on cross-coordinate c (key px)."""
    run = abs(a1 - a0)
    rise = yb - ya
    ang = math.atan2(rise, run)
    length = math.hypot(run, rise)
    direction = 1 if a1 > a0 else -1
    # local Z points along the run: +v at yaw 0, +u at 90, -v at 180, -u at 270 (layout_details frame)
    yaw_add = {("u", 1): 90.0, ("u", -1): 270.0, ("v", 1): 0.0, ("v", -1): 180.0}[(st.run, direction)]
    # the centre sits half a slab below the top centre line, along the slab's normal (which leans back toward the low end)
    am = (a0 + a1) / 2 + direction * math.sin(ang) * SLAB_T / 2
    u, v = (am, c) if st.run == "u" else (c, am)
    yc = (ya + yb) / 2 - math.cos(ang) * SLAB_T / 2
    o.box("wall", st.bi, "sf", u, v, yc, (FLIGHT_W - 0.05, SLAB_T, length), "stair", "Concrete", yaw_add, y_center=True,
          pitch_deg=-math.degrees(ang), shadow=False)


def _hut(body: Body, plan: Plan, o: _Out, door_c: float) -> None:
    """BR-I8.3: walls round the stairwell on the roof, a door on the start edge over the open flight, a roof slab."""
    st = plan.stair
    hut = plan.hut()
    assert st is not None and hut is not None and plan.roof_y is not None
    y = plan.roof_y
    cross = "v" if st.run == "u" else "u"
    r0, r1 = _range(hut, st.run)
    c0, c1 = _range(hut, cross)
    start = r0 if st.land > 0 else r1
    land = r1 if st.land > 0 else r0
    t = HUT_T
    # the two long walls and the landing-end wall
    for cc in (c0 + t / 2, c1 - t / 2):
        o.rect("wall", st.bi, "hw", _rect(st.run, r0, r1, cc - t / 2, cc + t / 2), y, HUT_H, body.wall_color, body.material)
    lw = land - st.land * t / 2
    o.rect("wall", st.bi, "hw", _rect(st.run, lw - t / 2, lw + t / 2, c0 + t, c1 - t), y, HUT_H, body.wall_color, body.material)
    # the start-edge wall with a 1.0 m door over the open flight
    sw = start + st.land * t / 2
    d0, d1 = door_c - 0.5, door_c + 0.5
    for a, b in ((c0 + t, d0), (d1, c1 - t)):
        if b - a > 0.05:
            o.rect("wall", st.bi, "hw", _rect(st.run, sw - t / 2, sw + t / 2, a, b), y, HUT_H, body.wall_color, body.material)
    o.rect("wall", st.bi, "hw", _rect(st.run, sw - t / 2, sw + t / 2, d0, d1), y + 2.1, HUT_H - 2.1, body.wall_color, body.material)
    o.rect("wall", st.bi, "hr", hut, y + HUT_H, 0.15, "floor_concrete", "Concrete")


def _elevator(body: Body, plan: Plan, o: _Out) -> None:
    """BR-I7: three core walls (full height) and a door per floor on the room side, carrying its floor and the floor count."""
    if plan.core is None:
        return
    bi, r, side = plan.core
    H = body.height_m
    t = WALL_T
    u0, u1, v0, v1 = r
    walls = {"f": (u0, u1, v0, v0 + t), "b": (u0, u1, v1 - t, v1), "l": (u0, u0 + t, v0, v1), "r": (u1 - t, u1, v0, v1)}
    rear = {"f": "b", "b": "f", "l": "r", "r": "l"}[side]
    for s in SIDES:
        if s != rear:
            o.rect("wall", bi, "ec", walls[s], 0.0, H, "elevator", "Metal")
    F = len(plan.levels)
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
    n = {"f": (0.0, -1.0), "b": (0.0, 1.0), "l": (-1.0, 0.0), "r": (1.0, 0.0)}[side]
    half = (CORE / 2) + 0.04
    yaw = {"f": 0.0, "b": 180.0, "l": 90.0, "r": 270.0}[side]  # the door's Front (-Z) faces the room
    for k, y in enumerate(plan.levels):
        o.box("interior", bi, "ed", cu + n[0] * half, cv + n[1] * half, y, (1.0, 2.1, 0.08), "elevator", "Metal", yaw,
              attrs={"ElevatorFloor": k, "ElevatorFloors": F})


# --- rooms and kits (BR-I9 to BR-I13) -----------------------------------------------------------------------------------------

# a kit piece: (code, fa, fb, size along a, height, size along b, colour, material, collides, lifted by)
P = tuple[str, float, float, float, float, float, str, str, bool, float]
KITS: dict[str, tuple[tuple[P, ...], int, float]] = {}  # name -> (pieces, how many of them tier 2 keeps, partition at fa or 0)


def _kit(name: str, keep2: int, partition: float, *pieces: P) -> None:
    KITS[name] = (pieces, keep2, partition)


S, W, M, F_, PL = "SmoothPlastic", "Wood", "Metal", "Fabric", "Plastic"
_kit("home", 3, 0.62,
     ("tb", 0.40, 0.45, 1.2, 0.75, 0.8, "wood", W, True, 0), ("so", 0.18, 0.85, 2.0, 0.45, 0.8, "fab", F_, True, 0),
     ("sb", 0.18, 0.98, 2.0, 0.8, 0.2, "fab", F_, True, 0), ("ct", 0.18, 0.55, 1.0, 0.4, 0.5, "wood", W, True, 0),
     ("tv", 0.18, 0.03, 1.6, 0.5, 0.4, "wood", W, True, 0), ("ts", 0.18, 0.03, 1.2, 0.7, 0.08, "black", S, False, 0.5),
     ("bd", 0.82, 0.75, 1.5, 0.45, 2.0, "wood", W, True, 0), ("bc", 0.82, 0.76, 1.4, 0.15, 1.8, "fab", F_, False, 0.45),
     ("kc", 0.42, 0.03, 2.0, 0.9, 0.6, "white", S, True, 0), ("fr", 0.56, 0.04, 0.7, 1.8, 0.7, "metal", M, True, 0))
_kit("store", 3, 0,
     ("cn", 0.12, 0.2, 0.6, 1.0, 1.6, "white", S, True, 0), ("s1", 0.38, 0.6, 0.5, 1.6, 1.8, "gray", M, True, 0),
     ("s2", 0.56, 0.6, 0.5, 1.6, 1.8, "gray", M, True, 0), ("s3", 0.74, 0.6, 0.5, 1.6, 1.8, "gray", M, True, 0),
     ("s4", 0.90, 0.6, 0.5, 1.6, 1.8, "gray", M, True, 0), ("fd", 0.98, 0.15, 0.7, 2.0, 1.6, "metal", M, True, 0),
     ("bs", 0.03, 0.2, 0.4, 1.8, 1.4, "white", S, True, 0), ("mt", 0.15, 0.8, 1.2, 0.02, 0.8, "dark", F_, False, 0))
_kit("eatery", 3, 0,
     ("cn", 0.10, 0.5, 0.6, 1.0, 2.0, "white", S, True, 0), ("t1", 0.45, 0.3, 1.2, 0.75, 0.8, "wood", W, True, 0),
     ("b1", 0.45, 0.62, 1.2, 0.45, 0.4, "fab", F_, True, 0), ("t2", 0.68, 0.3, 1.2, 0.75, 0.8, "wood", W, True, 0),
     ("b2", 0.68, 0.62, 1.2, 0.45, 0.4, "fab", F_, True, 0), ("t3", 0.90, 0.3, 1.2, 0.75, 0.8, "wood", W, True, 0),
     ("b3", 0.90, 0.62, 1.2, 0.45, 0.4, "fab", F_, True, 0), ("ks", 0.02, 0.5, 0.12, 2.0, 2.4, "white", S, True, 0),
     ("mb", 0.02, 0.85, 0.05, 0.8, 1.4, "black", S, False, 1.5))
_kit("salon", 3, 0,
     ("cn", 0.90, 0.2, 0.6, 1.0, 1.4, "white", S, True, 0), ("c1", 0.35, 0.2, 0.6, 0.9, 0.6, "black", PL, True, 0),
     ("m1", 0.35, 0.02, 0.9, 1.2, 0.05, "mirror", "Glass", False, 0.8), ("c2", 0.60, 0.2, 0.6, 0.9, 0.6, "black", PL, True, 0),
     ("m2", 0.60, 0.02, 0.9, 1.2, 0.05, "mirror", "Glass", False, 0.8), ("so", 0.80, 0.85, 1.6, 0.45, 0.7, "fab", F_, True, 0),
     ("sh", 0.10, 0.92, 1.0, 1.8, 0.4, "white", S, True, 0), ("tw", 0.10, 0.4, 0.5, 1.2, 0.8, "white", S, True, 0))
_kit("agency", 3, 0,
     ("d1", 0.30, 0.25, 1.2, 0.75, 0.6, "wood", W, True, 0), ("h1", 0.30, 0.08, 0.5, 0.9, 0.5, "black", PL, True, 0),
     ("cb", 0.95, 0.3, 0.5, 1.8, 1.0, "gray", M, True, 0), ("d2", 0.58, 0.25, 1.2, 0.75, 0.6, "wood", W, True, 0),
     ("h2", 0.58, 0.08, 0.5, 0.9, 0.5, "black", PL, True, 0), ("ct", 0.58, 0.68, 1.2, 0.75, 0.8, "wood", W, True, 0),
     ("cs", 0.58, 0.9, 1.2, 0.45, 0.4, "fab", F_, True, 0), ("c2", 0.95, 0.65, 0.5, 1.8, 1.0, "gray", M, True, 0))
_kit("academy", 3, 0,
     ("bo", 0.5, 0.02, 2.4, 1.2, 0.05, "board", S, False, 0.9), ("r1", 0.5, 0.35, 3.0, 0.75, 0.5, "white", S, True, 0),
     ("r2", 0.5, 0.55, 3.0, 0.75, 0.5, "white", S, True, 0), ("le", 0.5, 0.14, 1.0, 1.0, 0.5, "wood", W, True, 0),
     ("q1", 0.5, 0.43, 3.0, 0.45, 0.3, "dark", PL, True, 0), ("q2", 0.5, 0.63, 3.0, 0.45, 0.3, "dark", PL, True, 0),
     ("r3", 0.5, 0.75, 3.0, 0.75, 0.5, "white", S, True, 0), ("q3", 0.5, 0.83, 3.0, 0.45, 0.3, "dark", PL, True, 0))
_kit("clinic", 3, 0.45,
     ("rc", 0.15, 0.15, 1.6, 1.0, 0.6, "white", S, True, 0), ("w1", 0.15, 0.6, 1.5, 0.45, 0.45, "fab", F_, True, 0),
     ("b1", 0.68, 0.8, 0.8, 0.6, 1.9, "white", S, True, 0), ("w2", 0.15, 0.85, 1.5, 0.45, 0.45, "fab", F_, True, 0),
     ("b2", 0.90, 0.8, 0.8, 0.6, 1.9, "white", S, True, 0), ("dk", 0.78, 0.2, 1.2, 0.75, 0.6, "wood", W, True, 0),
     ("ch", 0.78, 0.06, 0.5, 0.9, 0.5, "black", PL, True, 0), ("dc", 0.98, 0.45, 0.4, 1.8, 1.0, "white", S, True, 0))
_kit("hall", 3, 0,
     ("st", 0.5, 0.06, 3.0, 0.3, 1.5, "wood", W, True, 0), ("pu", 0.5, 0.1, 0.8, 1.1, 0.5, "wood", W, True, 0.3),
     ("c1", 0.5, 0.35, 3.0, 0.45, 0.45, "fab", F_, True, 0), ("c2", 0.5, 0.47, 3.0, 0.45, 0.45, "fab", F_, True, 0),
     ("c3", 0.5, 0.59, 3.0, 0.45, 0.45, "fab", F_, True, 0), ("c4", 0.5, 0.71, 3.0, 0.45, 0.45, "fab", F_, True, 0),
     ("c5", 0.5, 0.83, 3.0, 0.45, 0.45, "fab", F_, True, 0), ("c6", 0.5, 0.95, 3.0, 0.45, 0.45, "fab", F_, True, 0))
_kit("gym", 3, 0,
     ("m1", 0.3, 0.7, 2.0, 0.05, 1.5, "fab", F_, False, 0), ("e1", 0.2, 0.15, 0.8, 1.3, 1.6, "black", M, True, 0),
     ("e2", 0.4, 0.15, 0.8, 1.3, 1.6, "black", M, True, 0), ("m2", 0.7, 0.7, 2.0, 0.05, 1.5, "fab", F_, False, 0),
     ("e3", 0.6, 0.15, 0.8, 1.3, 1.6, "black", M, True, 0), ("e4", 0.8, 0.15, 0.8, 1.3, 1.6, "black", M, True, 0),
     ("mi", 0.5, 0.99, 3.0, 1.8, 0.05, "mirror", "Glass", False, 0.3), ("rc", 0.95, 0.8, 0.6, 1.0, 1.4, "white", S, True, 0),
     ("lk", 0.05, 0.85, 0.5, 1.8, 1.2, "gray", M, True, 0))
_kit("rooms", 3, 0.5,
     ("s1", 0.25, 0.88, 1.6, 0.45, 0.6, "fab", F_, True, 0), ("t1", 0.25, 0.55, 0.9, 0.5, 0.6, "dark", S, True, 0),
     ("rc", 0.5, 0.1, 1.4, 1.0, 0.6, "white", S, True, 0), ("s2", 0.75, 0.88, 1.6, 0.45, 0.6, "fab", F_, True, 0),
     ("t2", 0.75, 0.55, 0.9, 0.5, 0.6, "dark", S, True, 0), ("tv", 0.75, 0.02, 1.2, 0.7, 0.08, "black", S, False, 1.2))
_kit("care", 2, 0,
     ("t1", 0.3, 0.5, 1.2, 0.45, 0.8, "wood", W, True, 0), ("m1", 0.3, 0.85, 1.5, 0.05, 1.0, "fab", F_, False, 0),
     ("t2", 0.6, 0.5, 1.2, 0.45, 0.8, "wood", W, True, 0), ("m2", 0.6, 0.85, 1.5, 0.05, 1.0, "fab", F_, False, 0),
     ("y1", 0.92, 0.3, 0.4, 1.0, 1.2, "white", S, True, 0), ("y2", 0.92, 0.7, 0.4, 1.0, 1.2, "white", S, True, 0),
     ("sc", 0.05, 0.1, 0.4, 1.0, 1.0, "wood", W, True, 0))
_kit("office", 3, 0,
     ("d1", 0.25, 0.3, 1.2, 0.75, 0.6, "white", S, True, 0), ("h1", 0.25, 0.15, 0.5, 0.9, 0.5, "black", PL, True, 0),
     ("cb", 0.95, 0.3, 0.5, 1.8, 1.0, "gray", M, True, 0), ("d2", 0.5, 0.3, 1.2, 0.75, 0.6, "white", S, True, 0),
     ("h2", 0.5, 0.15, 0.5, 0.9, 0.5, "black", PL, True, 0), ("d3", 0.25, 0.62, 1.2, 0.75, 0.6, "white", S, True, 0),
     ("h3", 0.25, 0.47, 0.5, 0.9, 0.5, "black", PL, True, 0), ("d4", 0.5, 0.62, 1.2, 0.75, 0.6, "white", S, True, 0),
     ("h4", 0.5, 0.47, 0.5, 0.9, 0.5, "black", PL, True, 0), ("mt", 0.8, 0.6, 1.6, 0.75, 0.9, "wood", W, True, 0),
     ("c2", 0.95, 0.85, 0.5, 1.8, 1.0, "gray", M, True, 0))
_kit("lobby", 4, 0,
     ("mb", 0.1, 0.97, 1.2, 1.4, 0.3, "metal", M, True, 0), ("be", 0.5, 0.9, 1.5, 0.45, 0.45, "wood", W, True, 0),
     ("pl", 0.92, 0.9, 0.5, 1.0, 0.5, "plant", "LeafyGrass", True, 0), ("gd", 0.85, 0.2, 1.2, 1.0, 0.6, "wood", W, True, 0))
_kit("pilotis", 4, 0,
     ("p1", 0.33, 0.5, 0.5, 2.2, 0.5, "floor_concrete", "Concrete", True, 0), ("p2", 0.66, 0.5, 0.5, 2.2, 0.5, "floor_concrete", "Concrete", True, 0),
     ("l1", 0.5, 0.3, 2.5, 0.02, 0.1, "line", S, False, 0), ("l2", 0.5, 0.7, 2.5, 0.02, 0.1, "line", S, False, 0))
_kit("public", 2, 0,
     ("id", 0.15, 0.2, 1.6, 1.0, 0.6, "white", S, True, 0), ("c1", 0.6, 0.3, 2.4, 0.45, 0.45, "fab", F_, True, 0),
     ("c2", 0.6, 0.5, 2.4, 0.45, 0.45, "fab", F_, True, 0), ("c3", 0.6, 0.7, 2.4, 0.45, 0.45, "fab", F_, True, 0),
     ("t1", 0.88, 0.35, 1.2, 0.75, 0.8, "wood", W, True, 0), ("t2", 0.88, 0.75, 1.2, 0.75, 0.8, "wood", W, True, 0),
     ("bb", 0.99, 0.5, 0.05, 1.0, 1.6, "wood", W, False, 1.0))
_kit("classroom", 4, 0,
     ("bo", 0.5, 0.02, 3.0, 1.2, 0.05, "board", S, False, 0.9), ("le", 0.5, 0.12, 1.0, 1.0, 0.5, "wood", W, True, 0),
     ("r1", 0.5, 0.32, 4.0, 0.7, 0.45, "wood", W, True, 0), ("q1", 0.5, 0.4, 4.0, 0.45, 0.3, "dark", PL, True, 0),
     ("r2", 0.5, 0.5, 4.0, 0.7, 0.45, "wood", W, True, 0), ("q2", 0.5, 0.58, 4.0, 0.45, 0.3, "dark", PL, True, 0),
     ("r3", 0.5, 0.68, 4.0, 0.7, 0.45, "wood", W, True, 0), ("q3", 0.5, 0.76, 4.0, 0.45, 0.3, "dark", PL, True, 0),
     ("r4", 0.5, 0.86, 4.0, 0.7, 0.45, "wood", W, True, 0), ("q4", 0.5, 0.94, 4.0, 0.45, 0.3, "dark", PL, True, 0))

# BR-I11: sign word -> kit. Every word of the sign pools must be here (test P7-13).
TRADE_KIT: dict[str, str] = {}
for _words, _k in ((("편의점", "슈퍼", "문구", "철물", "꽃집", "떡집", "베이커리", "약국", "안경", "휴대폰"), "store"),
                   (("분식", "김밥", "치킨", "피자", "국수", "카페"), "eatery"), (("미용실", "세탁소"), "salon"),
                   (("부동산", "세무사", "법무사"), "agency"), (("영어학원", "수학학원", "피아노학원", "미술학원", "독서실"), "academy"),
                   (("치과", "한의원", "내과", "피부과", "정형외과", "재활의학과", "요양병원"), "clinic"), (("교회",), "hall"),
                   (("헬스", "필라테스", "태권도"), "gym"), (("노래연습장",), "rooms"), (("어린이집", "요양원", "복지관", "유치원"), "care")):
    for _w in _words:
        TRADE_KIT[_w] = _k
SHOP_KITS = frozenset(("store", "eatery", "salon", "agency", "academy", "clinic", "hall", "gym", "rooms", "care"))


def trade_of(name: str, ground: bool) -> str:
    """The kit of a sign name (prefix + trade word): the longest word of TRADE_KIT it ends with."""
    for w in sorted(TRADE_KIT, key=lambda x: (-len(x), x)):
        if name.endswith(w):
            return TRADE_KIT[w]
    return "store" if ground else "office"


def kit_for(body: Body, k: int, unit: int = 0) -> str:
    """BR-I10: the kit of floor k (unit = storefront unit on a shop ground floor)."""
    code = body.usability or ""
    if body.archetype == "school":
        return "classroom"
    if code == "09000":
        return "clinic"
    if code == "11000":
        return "care"
    if body.archetype == "apartment":
        if k == 0:
            return "pilotis" if body.details["ground_use"] == "garage" else "lobby"
        return "corridor"
    if k == 0:
        if body.shop:
            return trade_of(_name(body, str(unit), "gf", 0), True)
        if body.details["ground_use"] == "garage":
            return "pilotis"
        if body.archetype == "public":
            return "public"
        return "home"
    if body.archetype == "commercial":
        F = body.floors
        if F >= int(D["sign_floor_min_floors"]) and k <= min(F - 1, int(D["sign_floor_max"])):
            return trade_of(_name(body, f"f{k}-0", "upper", k), False)
        return ("academy", "office", "clinic")[R.pick(body.building_id, f"use{k}", 3)]
    if body.archetype == "public":
        return "office"
    return "home"


def _clear_zones(body: Body, plan: Plan, bi: int, k: int) -> list[Rect]:
    """BR-I9.2: entrance, stair start, elevator door front, openings to sibling boxes."""
    zones: list[Rect] = []
    box = body.boxes[bi]
    if k == 0 and bi == body.front and plan.door is not None:
        a, w, _ = plan.door
        f = face_of(box, body.facing.side)  # type: ignore[union-attr]
        zones.append(_face_zone(f, a - w / 2, a + w / 2, 1.5))
    if plan.stair is not None and plan.stair.bi == bi:
        zones.append(_stair_zone(plan.stair))
    if plan.core is not None and plan.core[0] == bi:
        _, r, side = plan.core
        f = {"f": (r[0], r[1], r[2] - 1.5, r[2]), "b": (r[0], r[1], r[3], r[3] + 1.5), "l": (r[0] - 1.5, r[0], r[2], r[3]),
             "r": (r[1], r[1] + 1.5, r[2], r[3])}[side]
        zones += [r, f]
    for side, spans in plan.covered[bi]:
        f = face_of(box, side)
        for s0, s1 in spans:
            zones.append(_face_zone(f, s0, s1, 1.0))
    return zones


def _face_zone(f: Any, a0: float, a1: float, depth: float) -> Rect:
    """A rect inside the box against a face, over along-range [a0, a1], `depth` deep."""
    pts = []
    for a in (a0, a1):
        for dd in (0.0, depth + WALL_T):
            pts.append((f.c[0] + f.t[0] * a - f.n[0] * dd, f.c[1] + f.t[1] * a - f.n[1] * dd))
    return (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))


def _rooms(body: Body, plan: Plan, o: _Out) -> None:
    """BR-I9 to BR-I13: per floor and box the largest free rect gets the floor's kit (tier 2 column off the front box)."""
    for k, y in enumerate(plan.levels):
        ceiling = (plan.levels[k + 1] - SLAB_T) if k + 1 < len(plan.levels) else (body.height_m - D["cap_sink"] if plan.cap else body.height_m - SLAB_T)
        before = len(o.items)
        for bi in range(len(body.boxes)):
            obstacles = []
            if plan.stair is not None and plan.stair.bi == bi:
                obstacles.append(_stair_zone(plan.stair))
            if plan.core is not None and plan.core[0] == bi:
                obstacles.append(plan.core[1])
            room = _largest_free(inner(body, bi), obstacles)
            if room is None:
                continue
            zones = _clear_zones(body, plan, bi, k)
            kit = kit_for(body, k)
            tier = plan.tier if bi == body.front else 2
            if kit == "corridor":
                if bi == (plan.stair.bi if plan.stair else body.front):
                    _corridor(body, plan, o, bi, room, y, ceiling)
                continue
            if kit == "classroom":
                _classrooms(body, plan, o, bi, room, y, ceiling, zones, k)
                continue
            if k == 0 and body.shop and bi == body.front and plan.shop is not None and body.archetype == "commercial":
                _shop_units(body, plan, o, bi, room, y, ceiling, zones, tier)
                continue
            _split_rooms(body, o, bi, room, y, ceiling, kit, tier, zones, f"{k}-{bi}", _lit(body, kit, k, tier))
        cap = SCHOOL_FLOOR_CAP if body.archetype == "school" else FLOOR_CAP
        cap += 6 * len(body.boxes)  # partitions and ceiling panels on top of the kit parts
        if len(o.items) - before > cap:
            del o.items[before + cap:]


ROOM_MAX = 14.0  # a floor longer than this is cut into rooms of about 10 m (at most 3)


def _split_rooms(body: Body, o: _Out, bi: int, room: Rect, y: float, ceiling: float, kit: str, tier: int, zones: list[Rect], key: str,
                 light: bool) -> None:
    """BR-I9.4: a long floor gets partitions with door gaps; the first room takes the kit, the others its tier 2 column."""
    u0, u1, v0, v1 = room
    long_u = (u1 - u0) >= (v1 - v0)
    a0, a1 = (u0, u1) if long_u else (v0, v1)
    n = 1 if a1 - a0 <= ROOM_MAX else min(3, round((a1 - a0) / 10.0))
    if n == 1:
        _place_kit(body, o, bi, room, y, ceiling, kit, tier, zones, key, light=light)
        return
    zones = list(zones)
    placed: list[Rect] = []
    for i in range(1, n):
        _partition(o, bi, room, long_u, i / n, y, ceiling, zones, placed)
    for i in range(n):
        c0, c1 = a0 + (a1 - a0) * i / n + PARTITION_T, a0 + (a1 - a0) * (i + 1) / n - PARTITION_T
        sub = (c0, c1, v0, v1) if long_u else (u0, u1, c0, c1)
        _place_kit(body, o, bi, sub, y, ceiling, kit, tier if i == 0 else 2, zones, f"{key}-{i}", light=light and i == 0)


def _lit(body: Body, kit: str, k: int, tier: int) -> bool:
    """BR-I13.2: real lights only in ground-floor shops, lobbies and classrooms, tier 1."""
    return tier == 1 and ((k == 0 and kit in SHOP_KITS) or kit in ("lobby", "classroom"))


def _shop_units(body: Body, plan: Plan, o: _Out, bi: int, room: Rect, y: float, ceiling: float, zones: list[Rect], tier: int) -> None:
    """BR-I10: a commercial ground floor with several storefront units: partitions at the unit borders, a kit per unit."""
    s0, s1 = plan.shop  # type: ignore[misc]
    units = max(1, min(int(D["shop_units_max"]), int((s1 - s0) // D["shop_unit_m"])))
    f = face_of(body.boxes[bi], body.facing.side)  # type: ignore[union-attr]
    axis = "u" if abs(f.t[0]) > 0.5 else "v"
    lo, hi = _range(room, axis)
    cuts = []
    for i in range(units + 1):
        a = s0 + (s1 - s0) * i / units
        c = f.c[0] + f.t[0] * a if axis == "u" else f.c[1] + f.t[1] * a
        cuts.append(min(hi, max(lo, c)))
    cuts = sorted(cuts)
    cuts[0], cuts[-1] = lo, hi
    for i in range(units):
        a0, a1 = cuts[i], cuts[i + 1]
        if a1 - a0 < MIN_ROOM:
            continue
        sub = (a0, a1, room[2], room[3]) if axis == "u" else (room[0], room[1], a0, a1)
        if i > 0:
            pr = (a0 - PARTITION_T / 2, a0 + PARTITION_T / 2, room[2], room[3]) if axis == "u" else (room[0], room[1], a0 - PARTITION_T / 2, a0 + PARTITION_T / 2)
            if not any(_overlap(pr, z) for z in zones):
                o.rect("interior", bi, "pt", pr, y, ceiling - y, "white", "Plaster")
        unit = units - 1 - i if (f.t[0] if axis == "u" else f.t[1]) < 0 else i
        kit = kit_for(body, 0, unit)
        _place_kit(body, o, bi, sub, y, ceiling, kit, tier, zones, f"0-{bi}-{i}", light=_lit(body, kit, 0, tier))


def _place_kit(body: Body, o: _Out, bi: int, room: Rect, y: float, ceiling: float, kit: str, tier: int, zones: list[Rect], key: str,
               light: bool) -> None:
    """BR-I12: pieces at fixed fractions of the room (a = its long axis), clamped inside, dropped when they meet a zone or a piece."""
    pieces, keep2, partition = KITS[kit]
    if tier == 2:
        pieces = pieces[:keep2]
    u0, u1, v0, v1 = room
    long_u = (u1 - u0) >= (v1 - v0)
    mirror = R.pick(body.building_id, f"mir{key}", 2) == 1
    placed: list[Rect] = []
    zones = list(zones)
    if partition and tier == 1 and max(u1 - u0, v1 - v0) >= 5.0:
        _partition(o, bi, room, long_u, (1 - partition) if mirror else partition, y, ceiling, zones, placed)
    for code, fa, fb, sa, h, sb, color, material, collide, lift in pieces:
        if mirror:
            fa = 1 - fa
        if y + lift + h > ceiling:
            continue
        on_top = 0 < lift < 0.9  # sits on the piece under it (a TV on its stand, a cover on a bed); 0.9 and up hangs on a wall
        for ga, gb in ((fa, fb), (fa, 1 - fb), (1 - fa, fb), (1 - fa, 1 - fb)):  # blocked: try the opposite wall, then the other end
            su, sv, fu, fv = (sa, sb, ga, gb) if long_u else (sb, sa, gb, ga)
            if su > u1 - u0 - 0.2 or sv > v1 - v0 - 0.2:
                break
            cu = min(u1 - 0.1 - su / 2, max(u0 + 0.1 + su / 2, u0 + fu * (u1 - u0)))
            cv = min(v1 - 0.1 - sv / 2, max(v0 + 0.1 + sv / 2, v0 + fv * (v1 - v0)))
            fp = (cu - su / 2, cu + su / 2, cv - sv / 2, cv + sv / 2)
            if any(_overlap(fp, z) for z in zones):
                continue
            if on_top:
                if not any(_overlap(fp, p) for p in placed):
                    continue
            elif lift < 0.9 and any(_overlap(fp, p) for p in placed):
                continue
            c = FABRICS[R.pick(body.building_id, f"fab{key}{code}", len(FABRICS))] if color == "fab" else color
            o.box("interior", bi, code, cu, cv, y + lift, (su, h, sv), c, material, collide=collide)
            if (collide or h > 0.1) and lift == 0:
                placed.append(fp)
            break
    _panel(o, bi, room, ceiling, light)


def _partition(o: _Out, bi: int, room: Rect, long_u: bool, frac: float, y: float, ceiling: float, zones: list[Rect], placed: list[Rect]) -> None:
    """A partition across the room's long axis at `frac`, with a door gap in the middle (BR-I12.4)."""
    u0, u1, v0, v1 = room
    if long_u:
        a = u0 + frac * (u1 - u0)
        mid = (v0 + v1) / 2
        parts = [(a - PARTITION_T / 2, a + PARTITION_T / 2, v0, mid - GAP / 2), (a - PARTITION_T / 2, a + PARTITION_T / 2, mid + GAP / 2, v1)]
        gap = (a - 1.0, a + 1.0, mid - GAP / 2, mid + GAP / 2)
    else:
        a = v0 + frac * (v1 - v0)
        mid = (u0 + u1) / 2
        parts = [(u0, mid - GAP / 2, a - PARTITION_T / 2, a + PARTITION_T / 2), (mid + GAP / 2, u1, a - PARTITION_T / 2, a + PARTITION_T / 2)]
        gap = (mid - GAP / 2, mid + GAP / 2, a - 1.0, a + 1.0)
    pieces = []
    for p in parts:  # trimmed where it would cross a keep-clear zone (an opening to a sibling box, the stair start)
        along = (p[2], p[3]) if long_u else (p[0], p[1])
        spans = [along]
        for z in zones:
            if (_overlap((p[0], p[1], -1e9, 1e9), z) if long_u else _overlap((-1e9, 1e9, p[2], p[3]), z)):
                spans = _minus(spans, (z[2], z[3]) if long_u else (z[0], z[1]))
        pieces += [(p[0], p[1], s0, s1) if long_u else (s0, s1, p[2], p[3]) for s0, s1 in spans if s1 - s0 >= 0.5]
    for p in pieces:
        o.rect("interior", bi, "pt", p, y, ceiling - y, "white", "Plaster")
        placed.append(p)
    if pieces:
        zones.append(gap)


def _panel(o: _Out, bi: int, room: Rect, ceiling: float, light: bool) -> None:
    """BR-I13: one glowing ceiling panel per room, a real PointLight only when asked."""
    cu, cv = (room[0] + room[1]) / 2, (room[2] + room[3]) / 2
    attrs = {"Light": round(LIGHT_RANGE_M * o.frame.studs_per_m, 1)} if light else {}
    o.box("interior", bi, "lp", cu, cv, ceiling - 0.1, (1.2, 0.05, 0.6), "panel", "Neon", collide=False, attrs=attrs)


def _corridor(body: Body, plan: Plan, o: _Out, bi: int, room: Rect, y: float, ceiling: float) -> None:
    """BR-I10b: a 1.5 m corridor in front of the stairwell, a wall with unit doors on the far side, a hydrant, a panel."""
    st = plan.stair
    rect = inner(body, bi)
    rear = _rear_side(body, bi)
    perp, rs = _axes(rear)
    par = "v" if perp == "u" else "u"
    p0, p1 = _range(rect, perp)
    q0, q1 = _range(rect, par)
    rear_edge = p1 if rs > 0 else p0
    depth = (abs(_range(st.rect, perp)[1] - _range(st.rect, perp)[0]) if st and st.run == perp else 2 * FLIGHT_W) + START_CLEAR + 0.3
    depth = min(depth, (p1 - p0) - 2.0)
    if depth < 1.5:
        _panel(o, bi, room, ceiling, False)
        return
    line = rear_edge - rs * depth
    o.rect("interior", bi, "cw", _rect(perp, line - PARTITION_T / 2, line + PARTITION_T / 2, q0, q1), y, ceiling - y, "white", "Plaster")
    n = max(1, int((q1 - q0) // 5.5))
    for i in range(n):
        q = q0 + (q1 - q0) * (i + 0.5) / n
        face_out = line + rs * (PARTITION_T / 2 + 0.04)
        o.rect("interior", bi, "ud", _rect(perp, face_out - 0.04, face_out + 0.04, q - 0.5, q + 0.5), y, 2.1, "unit_door", "Wood")
    hq = q0 + 0.6
    face_out = line + rs * (PARTITION_T / 2 + 0.1)
    o.rect("interior", bi, "hy", _rect(perp, face_out - 0.1, face_out + 0.1, hq - 0.3, hq + 0.3), y + 0.8, 0.8, "red", "Metal", collide=False)
    corridor = _rect(perp, rear_edge, line, q0, q1)
    _panel(o, bi, corridor, ceiling, False)


def _classrooms(body: Body, plan: Plan, o: _Out, bi: int, room: Rect, y: float, ceiling: float, zones: list[Rect], k: int) -> None:
    """BR-I10a: a 2.4 m corridor on the long side nearer the stairwell when the room is 6.5 m deep, 8 m classrooms on the rest."""
    u0, u1, v0, v1 = room
    long_u = (u1 - u0) >= (v1 - v0)
    a0, a1 = (u0, u1) if long_u else (v0, v1)
    b0, b1 = (v0, v1) if long_u else (u0, u1)
    if b1 - b0 < 4.0:
        _place_kit(body, o, bi, room, y, ceiling, "office", plan.tier, zones, f"{k}-{bi}", light=False)
        return
    corridor_side = 0
    if b1 - b0 >= 6.5:
        sc = ((plan.stair.rect[2] + plan.stair.rect[3]) / 2 if long_u else (plan.stair.rect[0] + plan.stair.rect[1]) / 2) if plan.stair and plan.stair.bi == bi else b0
        corridor_side = -1 if abs(sc - b0) <= abs(sc - b1) else 1
    cb0, cb1 = (b0 + 2.4, b1) if corridor_side < 0 else (b0, b1 - 2.4) if corridor_side > 0 else (b0, b1)

    def R_(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> Rect:
        return (a_lo, a_hi, b_lo, b_hi) if long_u else (b_lo, b_hi, a_lo, a_hi)
    n = max(1, int((a1 - a0) // 8.0))
    start = len(o.items)
    for i in range(n):
        c0, c1 = a0 + (a1 - a0) * i / n, a0 + (a1 - a0) * (i + 1) / n
        if len(o.items) - start > SCHOOL_FLOOR_CAP - 12:
            break
        if i > 0:
            pr = R_(c0 - PARTITION_T / 2, c0 + PARTITION_T / 2, cb0, cb1)
            if not any(_overlap(pr, z) for z in zones):
                o.rect("interior", bi, "pt", pr, y, ceiling - y, "white", "Plaster")
        if corridor_side:
            line = cb0 if corridor_side < 0 else cb1
            mid = (c0 + c1) / 2
            for p_lo, p_hi in ((c0, mid - 0.6), (mid + 0.6, c1)):
                if p_hi - p_lo > 0.3:
                    o.rect("interior", bi, "cw", R_(p_lo, p_hi, line - PARTITION_T / 2, line + PARTITION_T / 2), y, ceiling - y, "white", "Plaster")
        cls = R_(c0 + PARTITION_T, c1 - PARTITION_T, cb0 + PARTITION_T, cb1 - PARTITION_T)
        _place_kit(body, o, bi, cls, y, ceiling, "classroom", plan.tier, zones, f"{k}-{bi}-{i}", light=plan.tier == 1)
    if corridor_side:
        cor = R_(a0, a1, b0, cb0) if corridor_side < 0 else R_(a0, a1, cb1, b1)
        _panel(o, bi, cor, ceiling, False)

