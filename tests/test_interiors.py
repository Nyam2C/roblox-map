"""U7 interiors (BR-I1 to BR-I16): P7-1 walls, P7-2 floors, P7-3 stairs, P7-4 reach, P7-5 overlap, P7-6 budget, P7-7
determinism, P7-8 off switch, P7-13 trade table, P7-14 elevator doors. Geometry is checked on the items themselves (studs,
Roblox frame: a part's local X turns by yaw about Y, then by px about its own X)."""
from __future__ import annotations

import math

import pytest
from hypothesis import given, settings

import common
import details_rules as R
import interiors as I
import layout_details as LD
from generators import body_cases, offset
from test_layout_u5 import CENTER, FRAME, S, all_items, resolve, street, villa

CFG = {**common.DEFAULTS, "interiors": True}
ROAD = [street()]
NEAR = offset(CENTER, 0, 22)  # body_cases centre: 22 m north of the east-west road


def build(row, est, detail=None, cfg=CFG, tier=1):
    body, eff = resolve(row, est, detail, features=ROAD, cfg=cfg)
    plan = I.plan_of(body, cfg, tier)
    return body, eff, plan, I.interior_items(body, plan, FRAME)


def to_local(item, x, y, z):
    """A point in studs -> the item's own frame (studs)."""
    r, p = math.radians(item.yaw_deg), math.radians(item.pitch_deg)
    dx, dy, dz = x - item.cx, y - item.cy, z - item.cz
    lx, lz = dx * math.cos(r) - dz * math.sin(r), dx * math.sin(r) + dz * math.cos(r)
    ly, lz = dy * math.cos(p) + lz * math.sin(p), -dy * math.sin(p) + lz * math.cos(p)
    return lx, ly, lz


def contains(item, x, y, z, eps=0.02):
    lx, ly, lz = to_local(item, x, y, z)
    return abs(lx) <= item.sx / 2 + eps and abs(ly) <= item.sy / 2 + eps and abs(lz) <= item.sz / 2 + eps


def world(body, bi, u, v, y):
    """Box-local metres and a height in metres -> studs."""
    e, n = LD._world(body.boxes[bi], u, v)
    return e * S, y * S, -n * S


def face_point(body, bi, side, along, inward, y):
    f = LD.face_of(body.boxes[bi], side)
    u, v = f.c[0] + f.t[0] * along - f.n[0] * inward, f.c[1] + f.t[1] * along - f.n[1] * inward
    return world(body, bi, u, v, y)


def code(item):
    return item.name.split("#i", 1)[1].rsplit("-", 1)[0] if "#i" in item.name else ""


def flight_ends(item):
    """The two ends (studs) of a flight's top centre line."""
    out = []
    for s in (-1, 1):
        lz = s * item.sz / 2
        ly = item.sy / 2
        p = math.radians(item.pitch_deg)
        y, z = ly * math.cos(p) - lz * math.sin(p), ly * math.sin(p) + lz * math.cos(p)  # rotate back about X
        r = math.radians(item.yaw_deg)
        out.append((item.cx + z * math.sin(r), item.cy + y, item.cz + z * math.cos(r)))
    return out


CASES = body_cases(center=NEAR)


# --- P7-1 walls ----------------------------------------------------------------------------------------------------------------

@settings(max_examples=40)
@given(CASES)
def test_p7_1_every_face_is_walled_except_the_entrance(case):
    row, est, detail = case
    body, eff, plan, items = build(row, est, detail)
    if plan is None:
        return
    walls = [i for i in items if i.kind == "wall" and code(i) == "w"]
    for side in LD.SIDES:
        L = LD.face_of(body.boxes[0], side).length
        for j in range(9):
            a = -L / 2 + 0.2 + (L - 0.4) * j / 8
            y = 1.0 + plan.y0
            hole = None
            if side == body.facing.side:
                hole = (plan.shop[0], plan.shop[1]) if plan.shop else (plan.door[0] - plan.door[1] / 2, plan.door[0] + plan.door[1] / 2)
            pt = face_point(body, 0, side, a, I.WALL_T / 2, y)
            hit = any(contains(w, *pt) for w in walls)
            in_hole = hole is not None and hole[0] - 0.05 < a < hole[1] + 0.05 and y < (plan.door[2] if plan.door else 9)
            if hole is not None and hole[0] + 0.05 < a < hole[1] - 0.05:
                assert not hit, f"{side} {a}: wall inside the entrance"
            elif not in_hole:
                assert hit, f"{side} {a}: no wall"


def l_building():
    """An L: a 16 x 8 m wing along the road and an 8 x 10 m wing behind its west end, as one outline."""
    c = offset(CENTER, 0, 19)
    o = lambda e, n: list(offset(c, e, n))  # noqa: E731
    outline = [o(-8, -4), o(8, -4), o(8, 4), o(0, 4), o(0, 14), o(-8, 14)]
    row, est, _ = villa(i=7, w=16, d=8, floors=3)
    row = {**row, "outline": outline, "building_area": 208.0}
    return row, est


def test_p7_1_boxes_of_one_building_have_no_wall_where_they_meet():
    row, est = l_building()
    body, eff, plan, items = build(row, est)
    assert plan is not None and len(body.boxes) == 2
    assert any(spans for box in plan.covered for _, spans in box)
    walls = [i for i in items if i.kind == "wall" and code(i) == "w"]
    for bi, box in enumerate(plan.covered):
        for side, spans in box:
            for s0, s1 in spans:
                if s1 - s0 < 0.6:
                    continue
                pt = face_point(body, bi, side, (s0 + s1) / 2, I.WALL_T / 2, 1.5)
                assert not any(contains(w, *pt) for w in walls), (bi, side, s0, s1)


# --- P7-2 floors -----------------------------------------------------------------------------------------------------------------

@settings(max_examples=40)
@given(CASES)
def test_p7_2_a_slab_tops_every_floor(case):
    row, est, detail = case
    body, eff, plan, items = build(row, est, detail)
    if plan is None:
        return
    assert len(plan.levels) == body.floors and plan.levels[0] in (0.15, D_PLINTH + I.PLINTH_LIFT)
    assert all(abs(plan.levels[k] - k * body.fh - I.LIFT) < 1e-9 for k in range(1, body.floors))
    # the facade floor band hides inside the floor slab and leaves the stair hole open
    ext = [i for bi in range(len(body.boxes)) for i in LD.body_items(body, bi, FRAME, CFG, [], plan)]
    for band in (i for i in ext if "#fl" in i.name):
        k = int(band.name.split("#fl", 1)[1].split("-")[1])
        assert (band.cy + band.sy / 2) / S < plan.levels[k] - 0.005
        if plan.stair is not None and plan.stair.bi == 0 and plan.roof_y is not None:
            r = plan.stair.rect
            assert not contains(band, *world(body, 0, (r[0] + r[1]) / 2, (r[2] + r[3]) / 2, (band.cy / S)))
    for k, y in enumerate(plan.levels):
        slabs = [i for i in items if code(i) == f"f{k}"]
        assert slabs and all(abs((i.cy + i.sy / 2) / S - y) < 0.01 for i in slabs)
        # the room centre has floor under it
        r = I.inner(body, 0)
        pt = world(body, 0, (r[0] + r[1]) / 2, (r[2] + r[3]) / 2, y - 0.05)
        assert any(contains(i, *pt) for i in slabs) or (plan.stair and k > 0 and I._overlap(plan.stair.rect, (r[0], r[1], r[2], r[3])))
    assert plan.levels[1] - plan.levels[0] >= 2.3 - 1e-9 if body.floors > 1 else True


D_PLINTH = LD.D["plinth_h"]


# --- P7-3 stairs and P7-4 reach -----------------------------------------------------------------------------------------------

@settings(max_examples=60)
@given(CASES)
def test_p7_3_flights_join_every_floor_and_the_roof_with_head_room(case):
    row, est, detail = case
    body, eff, plan, items = build(row, est, detail)
    if plan is None:
        return
    tops = list(plan.levels) + ([plan.roof_y] if plan.roof_y is not None else [])
    if len(tops) < 2:
        assert plan.stair is None
        return
    assert plan.stair is not None  # P7-4: every generated building fits a stairwell
    flights = [i for i in items if code(i) == "sf"]
    assert len(flights) == 2 * (len(tops) - 1)
    r = plan.stair.rect
    for k in range(len(tops) - 1):
        a, b = flights[2 * k], flights[2 * k + 1]
        lows = sorted([min(flight_ends(a), key=lambda p: p[1])[1], min(flight_ends(b), key=lambda p: p[1])[1]])
        highs = sorted([max(flight_ends(a), key=lambda p: p[1])[1], max(flight_ends(b), key=lambda p: p[1])[1]])
        mid = tops[k] + (tops[k + 1] - tops[k]) / 2
        assert abs(lows[0] / S - tops[k]) < 0.02 and abs(highs[1] / S - tops[k + 1]) < 0.02
        assert abs(highs[0] / S - mid) < 0.02 and abs(lows[1] / S - mid) < 0.02
        for f in (a, b):
            for x, y, z in flight_ends(f):
                e, n = x / S, -z / S
                u, v = I._local_of(body, plan.stair.bi, e, n)
                assert r[0] - 0.05 <= u <= r[1] + 0.05 and r[2] - 0.05 <= v <= r[3] + 0.05
    # head room: the same flight one storey up is at least 2.0 m above, measured at both ends
    for k in range(len(tops) - 2):
        for h in (0, 1):
            low, up = flights[2 * k + h], flights[2 * (k + 1) + h]
            lo_ends = sorted(flight_ends(low), key=lambda p: p[1])
            up_ends = sorted(flight_ends(up), key=lambda p: p[1])
            gap = min(up_ends[0][1] - lo_ends[0][1], up_ends[1][1] - lo_ends[1][1]) / S
            ang = math.radians(abs(up.pitch_deg))
            assert gap - I.SLAB_T / math.cos(ang) >= 2.0 - 1e-6


def test_p7_4_the_real_cells_need_no_building_without_a_stairwell():
    import json
    for c in ("8930e0af13bffff", "8930e0af12bffff", "8930e0af123ffff"):
        path = common.resolve("data/build") / c / "manifest.json"
        if not path.exists():
            pytest.skip("cells not built here")
        counts = json.loads(path.read_text(encoding="utf-8"))["counts"]
        if counts.get("interior_buildings"):
            assert counts["no_stairwell"] == 0


# --- P7-5 overlap ----------------------------------------------------------------------------------------------------------

@settings(max_examples=40)
@given(CASES)
def test_p7_5_furniture_stays_off_walls_stairs_entrance_and_core(case):
    row, est, detail = case
    body, eff, plan, items = build(row, est, detail)
    if plan is None:
        return
    keep = [I._stair_zone(plan.stair)] if plan.stair else []
    if plan.core:
        keep.append(plan.core[1])
    entrance = I._clear_zones(body, plan, 0, 0)[0]
    inner = I.inner(body, 0)
    for it in items:
        if it.kind != "interior" or it.collide is False or code(it) in ("pt", "cw", "ud", "ed", "lp", "hy"):
            continue
        e, n = it.cx / S, -it.cz / S
        u, v = I._local_of(body, 0, e, n)
        assert inner[0] - 0.01 <= u <= inner[1] + 0.01 and inner[2] - 0.01 <= v <= inner[3] + 0.01, it.name
        floor = min(range(len(plan.levels)), key=lambda k: abs((it.cy - it.sy / 2) / S - plan.levels[k]))
        zones = keep + ([entrance] if floor == 0 else [])
        fp = (u - 0.01, u + 0.01, v - 0.01, v + 0.01)  # its centre
        assert not any(I._overlap(fp, z) for z in zones), it.name


# --- P7-6 budget, P7-7 determinism -------------------------------------------------------------------------------------------

@settings(max_examples=40)
@given(CASES)
def test_p7_6_and_7_budget_holds_and_the_same_input_gives_the_same_items(case):
    row, est, detail = case
    body, eff, plan, items = build(row, est, detail)
    F = body.floors
    limit = (70 if body.archetype == "school" else 30) * F + 60
    assert len(items) <= limit
    assert len({i.name for i in items}) == len(items)
    assert build(row, est, detail)[3] == items
    for i in items:
        assert i.material in R.MATERIALS and i.shape in R.SHAPES and i.kind in ("wall", "interior")


# --- P7-8 off --------------------------------------------------------------------------------------------------------------

@settings(max_examples=25)
@given(CASES)
def test_p7_8_off_or_tier_3_gives_the_u5_items(case):
    row, est, detail = case
    off = {**CFG, "interiors": False}
    body, eff = resolve(row, est, detail, features=ROAD, cfg=off)
    base, _, _ = all_items(body, row, eff, cfg=off)
    for cfg, tier in ((off, 1), (CFG, 3)):
        plan = I.plan_of(body, cfg, tier)
        assert plan is None and I.interior_items(body, plan, FRAME) == []
    on = I.plan_of(body, CFG, 1)
    if on is not None:
        assert any(i.attrs.get("Hollow") for i in LD.box_items(body, row, eff, FRAME, hollow=True))


def test_p7_8_plan_cell_items_are_the_u5_ones_when_off():
    from test_build_luau import CELL as BCELL, building, street as bstreet
    import build_luau as B
    rows, feats = [building(i, center=offset(CENTER, 30 * i - 45, 20)) for i in range(4)], [bstreet()]  # 15 m off the road
    base = B.plan_cell(BCELL, rows, feats, {**common.DEFAULTS})
    assert B.plan_cell(BCELL, rows, feats, {**common.DEFAULTS, "interiors": True}, tier=3).items == base.items
    on = B.plan_cell(BCELL, rows, feats, {**common.DEFAULTS, "interiors": True})
    assert on.counts["items_wall"] > 0 and on.counts["interior_buildings"] > 0


# --- P7-13 trades, P7-14 elevators -----------------------------------------------------------------------------------------

def test_p7_13_every_sign_word_has_a_kit():
    for pool in ("villa_gf", "com_gf", "upper", "medical", "care"):
        for w in R.POOLS[pool]:
            assert w in I.TRADE_KIT, (pool, w)
    assert set(I.TRADE_KIT.values()) <= set(I.KITS)
    assert I.trade_of("한솔영어학원", False) == "academy" and I.trade_of("푸른약국", True) == "store" and I.trade_of("무엇", False) == "office"


@pytest.mark.parametrize("floors", [5, 8, 15])
def test_p7_14_an_apartment_gets_one_elevator_door_a_floor(floors):
    row, est, _ = villa(i=9, w=22, d=10, floors=floors, fh=2.9, code="02000")
    body, eff, plan, items = build(row, est)
    assert body.archetype == "apartment" and plan.core is not None
    doors = [i for i in items if "ElevatorFloor" in i.attrs]
    assert sorted(i.attrs["ElevatorFloor"] for i in doors) == list(range(floors))
    assert {i.attrs["ElevatorFloors"] for i in doors} == {floors} and {i.owner for i in doors} == {body.building_id}
    for d in doors:  # each door stands on its floor
        assert abs((d.cy - d.sy / 2) / S - plan.levels[d.attrs["ElevatorFloor"]]) < 0.01


def test_a_shop_villa_gets_its_kit_from_the_band_sign_and_a_light():
    row, est, _ = villa(i=11, w=12, d=10, floors=3, detail={"building_id": "gis:11", **{f: None for f in R.DETAIL_FIELDS}, "ground_use": "shop", "note": None})
    detail = {"building_id": "gis:11", **{f: None for f in R.DETAIL_FIELDS}, "ground_use": "shop", "note": None}
    body, eff, plan, items = build(row, est, detail)
    assert body.shop and plan.shop is not None
    word_kit = I.trade_of(LD._name(body, "0", "gf", 0), True)
    assert I.kit_for(body, 0) == word_kit
    lights = [i for i in items if "Light" in i.attrs]
    assert lights and all(abs((i.cy / S) - (plan.levels[1] - I.SLAB_T)) < 0.3 for i in lights)


def test_the_flat_roof_cap_opens_over_the_stairwell_and_a_hut_covers_it():
    row, est, _ = villa(i=12, w=14, d=10, floors=3, roof="flat")
    body, eff, plan, items = build(row, est)
    assert plan.roof_y is not None and plan.cap
    ext = LD.body_items(body, plan.stair.bi, FRAME, CFG, [], plan)
    caps = [i for i in ext if "#cap" in i.name]
    assert len(caps) >= 2 and all(i.collide for i in caps)
    r = plan.stair.rect
    centre = world(body, plan.stair.bi, (r[0] + r[1]) / 2, (r[2] + r[3]) / 2, plan.roof_y - 0.3)
    assert not any(contains(c, *centre) for c in caps)
    hut = [i for i in items if code(i) in ("hw", "hr")]
    assert len(hut) >= 5
