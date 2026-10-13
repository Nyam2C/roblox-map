"""U4 review.py: the blind view (P4-10), the order and the batches (P4-11), field-of-view and camera values (P4-13, P4-14),
the agreement statistics (P4-15) and the capture crop box."""
from __future__ import annotations

import math
import random

import pytest
from hypothesis import given, strategies as st

import common
import judgement as J
import layout
import review as R
from generators import BASE, offset, rect

CFG = common.DEFAULTS
FRAME = layout.Frame.from_cfg(CFG)

hidden_values = st.one_of(st.none(), st.integers(0, 40), st.floats(0, 500), st.text(max_size=8))


def building(i, **kw):
    return {"building_id": f"gis:{i}", "name": f"name {i}", "centroid": list(offset(BASE, 20 * i, 5)),
            "outline": [list(p) for p in rect(offset(BASE, 20 * i, 5), 14, 9)], "floors_above": 3, "floors_below": 0, "height_m": 10.0,
            "osm_height_m": None, "osm_levels": None, "usability_code": "01000", "building_area": 120.0, **kw}


VIEWS = [{"rank": 2, "heading_deg": 100.0, "yaw_deg": -30.0}, {"rank": 1, "heading_deg": 10.0, "yaw_deg": 5.0}]


# --- P4-10: the blind view (BR-1.3) ----------------------------------------------------------------------

@given(st.fixed_dictionaries({k: hidden_values for k in R.HIDDEN_FIELDS}))
def test_p4_10_the_blind_item_does_not_change_with_the_hidden_fields_and_does_not_carry_them(hidden):
    base = R.blind_item(building(1), VIEWS, FRAME)
    changed = R.blind_item(building(1, **hidden), VIEWS, FRAME)
    assert base == changed
    assert set(base) == {"building_id", "name", "lat", "lon", "box_m", "views"}
    assert not set(R.HIDDEN_FIELDS) & (set(base) | {k for v in base["views"] for k in v})


def test_the_blind_item_lists_what_a_judge_may_know():
    item = R.blind_item(building(1), VIEWS, FRAME)
    assert item["building_id"] == "gis:1" and item["name"] == "name 1"
    assert item["box_m"] == pytest.approx([14.0, 9.0], abs=0.3)
    assert [v["rank"] for v in item["views"]] == [1, 2]  # in rank order
    assert [v["facing"] for v in item["views"]] == ["N", "E"]  # 10 + 5 = 15 degrees, 100 - 30 = 70 degrees


@given(st.lists(st.tuples(st.sampled_from([None, 0, 3, 5]), st.sampled_from([None, 0.0, 12.5])), min_size=1, max_size=12, unique=False),
       st.randoms(use_true_random=False), st.sets(st.integers(0, 11)))
def test_p4_10_p4_11_the_judging_order_uses_only_whether_the_register_has_data_and_does_not_depend_on_row_order(specs, rnd, school):
    rows = [building(i, floors_above=f, height_m=h) for i, (f, h) in enumerate(specs)]
    school_ids = {f"gis:{i}" for i in school}
    order = R.pending_order(rows, school_ids)
    shuffled = list(rows)
    rnd.shuffle(shuffled)
    assert order == R.pending_order(shuffled, school_ids)
    assert sorted(order) == sorted(r["building_id"] for r in rows)  # every building exactly once
    by_id = {r["building_id"]: r for r in rows}
    group = [0 if not R._has_register_data(by_id[i]) else 1 if i in school_ids else 2 for i in order]
    assert group == sorted(group)
    for g in (0, 1, 2):  # inside a group by id
        ids = [i for i, x in zip(order, group) if x == g]
        assert ids == sorted(ids)
    # changing a register number that is already there does not move anything
    bumped = [{**r, "floors_above": 9} if r["floors_above"] else r for r in rows]
    assert R.pending_order(bumped, school_ids) == order


# --- P4-11: review batches (BR-7.2) ---------------------------------------------------------------------------

def eff(bid, flagged):
    return J.EffectiveBuilding(bid, 3, "register", "unverified", 10.0, "register", "light_gray", "default", "flat", "default",
                               ("conflict",) if flagged else (), 3, 10.0, None, None, None, None)


@given(st.lists(st.booleans(), min_size=0, max_size=30), st.integers(1, 12), st.sets(st.integers(0, 29)), st.randoms(use_true_random=False))
def test_p4_11_batches_hold_every_building_once_in_the_order_flagged_school_rest(flags, size, school, rnd):
    items = [eff(f"gis:{i:03d}", f) for i, f in enumerate(flags)]
    school_ids = {f"gis:{i:03d}" for i in school}
    batches = R.review_batches(items, school_ids, size)
    shuffled = list(items)
    rnd.shuffle(shuffled)
    assert batches == R.review_batches(shuffled, school_ids, size)
    flat = [i for b in batches for i in b]
    assert sorted(flat) == sorted(e.building_id for e in items)
    assert all(0 < len(b) <= size for b in batches) and len(batches) == math.ceil(len(items) / size)
    group = {e.building_id: (0 if e.flags else 1 if e.building_id in school_ids else 2) for e in items}
    assert [group[i] for i in flat] == sorted(group[i] for i in flat)


def test_batch_size_must_be_positive():
    with pytest.raises(ValueError):
        R.review_batches([], set(), 0)


# --- P4-13: field of view (BR-7.4) ----------------------------------------------------------------------------------

@given(st.floats(1, 179))
def test_p4_13_the_vertical_angle_is_narrower_and_converts_back(h):
    v = R.h_to_v_fov(h)
    assert 0 < v < h
    assert R.v_to_h_fov(v) == pytest.approx(h, rel=1e-9)


@given(st.floats(1, 179), st.floats(1, 179))
def test_p4_13_a_wider_horizontal_angle_gives_a_wider_vertical_angle(a, b):
    if a < b:
        assert R.h_to_v_fov(a) < R.h_to_v_fov(b)


def test_the_studio_angle_for_the_widest_crop_is_the_one_used_in_the_feasibility_test():
    assert R.STUDIO_FOV_V_DEG == pytest.approx(83.58, abs=0.005)


# --- P4-14: camera (BR-7.4) ------------------------------------------------------------------------------------------

@given(st.floats(0, 360, exclude_max=True), st.floats(-180, 180, exclude_max=True), st.integers(-3, 3))
def test_p4_14_the_bearing_is_heading_plus_yaw_modulo_a_turn(heading, yaw, turns):
    b = R.camera_bearing(heading, yaw)
    assert 0 <= b < 360
    def gap(x, y):  # distance between two bearings around the circle
        return abs((x - y + 180) % 360 - 180)
    assert gap(b, heading + yaw) < 1e-6
    assert gap(R.camera_bearing(heading, yaw + 360 * turns), b) < 1e-6


@given(st.floats(0, 360, exclude_max=True), st.floats(-60, 60))
def test_p4_14_the_look_direction_is_a_unit_vector_with_the_right_sign_conventions(bearing, pitch):
    dx, dy, dz = R.direction(bearing, pitch)
    assert math.hypot(dx, dy, dz) == pytest.approx(1.0)
    assert (dy > 0) == (pitch > 0) or abs(dy) < 1e-9
    assert R.direction(0, 0) == pytest.approx((0, 0, -1))  # north is -Z
    assert R.direction(90, 0) == pytest.approx((1, 0, 0))  # east is +X


def test_the_camera_repeats_the_feasibility_test_values():
    cam = R.camera_for_view(FRAME, 37.5047247, 126.7767836, 100.863962906631, -82.6855384281503, 15.8459991916378, 2.5)
    assert cam["position"] == pytest.approx([-903.277, 9.0, -222.448], abs=0.01)
    assert cam["look_at"] == pytest.approx([-873.265, 36.305, -313.847], abs=0.01)
    assert cam["bearing_deg"] == pytest.approx(18.178, abs=0.001)


def test_compass_names_the_eight_directions():
    assert [R.compass(b) for b in (0, 44, 46, 90, 180, 270, 315, 359, 360)] == ["N", "NE", "NE", "E", "S", "W", "NW", "N", "N"]


# --- the capture crop box (N-U4-4) ---------------------------------------------------------------------------------------

@given(st.integers(300, 3000), st.integers(300, 2000), st.floats(20, 100))  # crops use 60 to 100 degrees; tiny angles round badly
def test_the_crop_box_is_inside_the_capture_four_to_three_and_centered(w, h, fov):
    if w < round(h * 4 / 3) - 1:  # one pixel of rounding is allowed
        with pytest.raises(ValueError):
            R.capture_crop_box(w, h, fov)
        return
    left, top, right, bottom = R.capture_crop_box(w, h, fov)
    assert 0 <= left < right <= w and 0 <= top < bottom <= h
    cw, ch = right - left, bottom - top
    assert abs(cw / ch - 4 / 3) < 0.03
    assert abs((left + right) / 2 - w / 2) <= 1 and abs((top + bottom) / 2 - h / 2) <= 1


@given(st.integers(600, 2000), st.integers(450, 1500), st.floats(1, 100), st.floats(1, 100))
def test_a_narrower_crop_angle_cuts_a_smaller_part(w, h, a, b):
    if w < round(h * 4 / 3) or a >= b:
        return
    small, big = R.capture_crop_box(w, h, a), R.capture_crop_box(w, h, b)
    assert small[2] - small[0] <= big[2] - big[0] and small[3] - small[1] <= big[3] - big[1]


def test_the_widest_crop_uses_the_whole_four_to_three_middle():
    assert R.capture_crop_box(1437, 882, 100) == (130, 0, 1306, 882)
    with pytest.raises(ValueError):
        R.capture_crop_box(800, 800, 100)  # a square window is narrower than 4:3


# --- P4-15: agreement (S4-2) --------------------------------------------------------------------------------------

rows_st = st.lists(st.tuples(st.integers(0, 40).map(lambda n: f"gis:{n}"), st.one_of(st.none(), st.integers(1, 6)),
                             st.one_of(st.none(), st.integers(1, 6)), st.sampled_from(["high", "medium", "low", None])), max_size=40)


@given(rows_st, st.sets(st.integers(0, 40).map(lambda n: f"gis:{n}")))
def test_p4_15_agreement_adds_up_and_leaves_out_the_broken_buildings(rows, broken):
    a = R.agreement(rows, broken)
    both = [r for r in rows if r[1] and r[2]]
    kept = [r for r in both if r[0] not in broken]
    assert a["compared"] == len(kept) and a["excluded"] == len(both) - len(kept)
    assert a["agree"] == sum(1 for r in kept if r[1] == r[2])
    assert sum(s["compared"] for s in a["by_confidence"].values()) == a["compared"]
    assert sum(s["agree"] for s in a["by_confidence"].values()) == a["agree"]
    assert all(0 <= s["agree"] <= s["compared"] for s in a["by_confidence"].values())
    if a["compared"]:
        assert 0 <= a["rate"] <= 1 and a["rate"] == a["agree"] / a["compared"]
    else:
        assert a["rate"] is None


def test_agreement_example():
    rows = [("gis:1", 3, 3, "high"), ("gis:2", 3, 4, "high"), ("gis:3", 3, 3, "low"), ("gis:4", None, 3, "high"), ("gis:5", 3, None, None),
            ("gis:6", 2, 2, "high")]
    a = R.agreement(rows, ["gis:6"])
    assert (a["compared"], a["agree"], a["excluded"]) == (3, 2, 1)
    assert a["by_confidence"] == {"high": {"compared": 2, "agree": 1}, "low": {"compared": 1, "agree": 1}}
