"""U4 judgement.py: the floors table (P4-1), height rules (P4-2), override priority (P4-3), review flags (P4-12),
validation (P4-9) and the export file format (P4-7, P4-8)."""
from __future__ import annotations

import json
import random

import pytest
from hypothesis import given, strategies as st

import common
import judgement as J
from generators import COLOR_NAMES, REASONS, TIMES, building_cases, judgements, override_pairs, override_sets, register_buildings

CFG = common.DEFAULTS
FLOOR_H, DEFAULT_H = CFG["floor_height_m"], CFG["default_height_m"]
LO, HI = CFG["floor_height_min_m"], CFG["floor_height_max_m"]


def reg_floors(b):
    v = b["floors_above"]
    return int(v) if v and v > 0 else None


def reg_height(b):
    v = b["height_m"]
    return float(v) if v and v > 0 else None


# --- P4-1: floors (BR-3) ---------------------------------------------------------------------------------

@given(register_buildings(), st.one_of(st.none(), judgements()))
def test_p4_1_floors_follow_the_table_in_the_functional_design(b, j):
    e = J.effective_building(b, j, None, CFG)
    reg, photo, conf = reg_floors(b), j and j["floors_seen"], j and j["confidence"]
    if j is None:
        want = (reg, "register" if reg else None, "unjudged")
    elif reg and photo:
        if photo == reg:
            want = (reg, "register", "verified" if conf in ("high", "medium") else "unverified")
        elif conf == "high":
            want = (photo, "photo_count", "changed")
        else:
            want = (reg, "register", "conflict")
    elif reg:
        want = (reg, "register", "unverified")
    elif photo:
        want = (photo, "photo_count", "filled")
    else:
        want = (None, None, "none")
    assert (e.floors_above, e.floors_basis, e.floors_status) == want
    assert e.floors_above in (None, reg, photo)  # never a value nobody gave


@given(st.integers(1, 30), st.sampled_from(J.CONFIDENCES))
def test_p4_1_a_photo_that_agrees_keeps_the_register_value_whatever_the_confidence(n, conf):
    b = {"building_id": "gis:1", "floors_above": n, "height_m": None}
    j = {"floors_seen": n, "confidence": conf}
    e = J.effective_building(b, j, None, CFG)
    assert (e.floors_above, e.floors_basis) == (n, "register")
    assert (e.floors_status == "verified") == (conf != "low")


def test_p4_1_register_values_of_zero_count_as_missing():
    e = J.effective_building({"building_id": "gis:1", "floors_above": 0, "height_m": 0.0}, None, None, CFG)
    assert (e.floors_above, e.height_m, e.height_basis) == (None, DEFAULT_H, "default")


# --- P4-2: height (BR-4) ---------------------------------------------------------------------------------

@given(building_cases())
def test_p4_2_height_is_positive_and_follows_the_rules(case):
    b, j, ov = case
    e = J.effective_building(b, j, ov, CFG)
    assert e.height_m > 0
    if "height_m" in ov:
        assert (e.height_m, e.height_basis) == (float(ov["height_m"]), "override")
        return
    floors, reg_f, reg_h = e.floors_above, reg_floors(b), reg_height(b)
    same = reg_f is None or floors == reg_f
    band = reg_h is not None and floors is not None and LO <= reg_h / floors <= HI
    if reg_h is not None and floors is not None and same and band:
        assert (e.height_m, e.height_basis) == (reg_h, "register")
    elif reg_h is not None and floors is not None and reg_f is not None and floors < reg_f and e.floors_basis == "photo_count":
        assert (e.height_m, e.height_basis) == (reg_h, "register")  # fewer floors seen: a tall floor, the measured height stands
    elif reg_h is not None and floors is None:
        assert (e.height_m, e.height_basis) == (reg_h, "register")
    elif floors is not None:
        assert (e.height_m, e.height_basis) == (floors * FLOOR_H, "from_floors")
    elif j and j["height_est_m"]:
        assert (e.height_m, e.height_basis) == (float(j["height_est_m"]), "photo_geometry")
    else:
        assert (e.height_m, e.height_basis) == (float(DEFAULT_H), "default")


@given(st.integers(1, 99))
def test_p4_2_without_a_register_height_each_floor_adds_one_floor_height(n):
    b = {"building_id": "gis:1", "floors_above": None, "height_m": None}
    h = [J.effective_building(b, None, {"floors_above": k}, CFG).height_m for k in (n, n + 1)]
    assert h[1] - h[0] == pytest.approx(FLOOR_H)


@given(st.integers(2, 30), st.integers(1, 30), st.floats(2, 120), st.floats(2, 120))
def test_p4_2_a_register_height_does_not_count_once_the_floors_differ_from_the_register(reg, other, h1, h2):
    if other == reg:
        return
    heights = [J.effective_building({"building_id": "gis:1", "floors_above": reg, "height_m": h}, None, {"floors_above": other}, CFG)
               for h in (h1, h2)]
    assert heights[0].height_m == heights[1].height_m == other * FLOOR_H


def test_p4_2_examples_of_the_register_height_band():
    def eff(floors, height):
        return J.effective_building({"building_id": "gis:1", "floors_above": floors, "height_m": height}, None, None, CFG)
    assert (eff(3, 10.5).height_m, eff(3, 10.5).height_basis, eff(3, 10.5).flags) == (10.5, "register", ("unjudged",))
    out = eff(3, 20.0)  # 6.7 m per floor: out of the band
    assert (out.height_m, out.height_basis, "height_out_of_range" in out.flags) == (3 * FLOOR_H, "from_floors", True)
    assert eff(None, 12.0).height_basis == "register"  # a height without floors is used as it is


# --- P4-3: overrides win (BR-6) ---------------------------------------------------------------------------

@given(building_cases(), override_pairs())
def test_p4_3_an_override_decides_the_field_and_the_basis(case, pair):
    b, j, ov = case
    field, value = pair
    e = J.effective_building(b, j, {**ov, field: value}, CFG)
    got = {"floors_above": (e.floors_above, e.floors_basis), "height_m": (e.height_m, e.height_basis),
           "wall_color": (e.wall_color, e.wall_basis), "roof_shape": (e.roof_shape, e.roof_basis)}[field]
    assert got == ((float(value) if field == "height_m" else value), "override")


@given(building_cases())
def test_p4_3_overriding_one_field_leaves_the_others_to_their_own_rules(case):
    b, j, ov = case
    base = J.effective_building(b, j, None, CFG)
    e = J.effective_building(b, j, {"wall_color": "pink", "roof_shape": "hip"}, CFG)
    assert (e.floors_above, e.height_m, e.floors_status, e.height_basis) == (base.floors_above, base.height_m, base.floors_status, base.height_basis)


# --- P4-12: review flags (BR-7.1) -------------------------------------------------------------------------

@given(building_cases())
def test_p4_12_flags_follow_the_status_and_the_basis(case):
    b, j, ov = case
    e = J.effective_building(b, j, ov, CFG)
    flags = set(e.flags)
    assert e.flags == tuple(f for f in J.FLAGS if f in flags)  # fixed order, no duplicates
    assert ("conflict" in flags) == (e.floors_status == "conflict")
    assert ("changed" in flags) == (e.floors_status == "changed")
    assert ("filled" in flags) == (e.floors_status == "filled")
    assert ("unjudged" in flags) == (j is None)
    assert ("default_height" in flags) == (e.height_basis == "default")
    if "osm_differs" in flags:
        assert "default_height" in flags and (b["osm_height_m"] or b["osm_levels"])
    if "height_out_of_range" in flags:
        assert e.height_basis == "from_floors" and reg_height(b) is not None
    if not flags:
        assert e.floors_status in ("verified", "unverified", "override", "none")
        assert e.height_basis in ("register", "from_floors", "photo_geometry", "override")


def test_p4_12_a_correction_resolves_the_flag_of_its_field():
    b = {"building_id": "gis:1", "floors_above": 3, "height_m": 10.5}
    j = {"floors_seen": 4, "confidence": "medium"}
    assert "conflict" in J.effective_building(b, j, None, CFG).flags
    assert "conflict" not in J.effective_building(b, j, {"floors_above": 4}, CFG).flags


# --- appearance (BR-5) ----------------------------------------------------------------------------------------

def test_appearance_priority_and_default_color():
    b = {"building_id": "gis:1", "floors_above": 3, "height_m": 10.5}
    j = {"floors_seen": 3, "confidence": "high", "wall_color": "cream", "roof_shape": "gable"}
    assert (J.effective_building(b, None, None, CFG).wall_color, J.effective_building(b, None, None, CFG).roof_shape) == ("light_gray", "flat")
    e = J.effective_building(b, j, None, CFG)
    assert (e.wall_color, e.wall_basis, e.roof_shape, e.roof_basis) == ("cream", "photo", "gable", "photo")
    e = J.effective_building(b, j, {"wall_color": "blue"}, CFG)
    assert (e.wall_color, e.wall_basis) == ("blue", "override")
    assert J.wall_rgb("light_gray", CFG) == (200, 200, 205) and J.wall_rgb("other", CFG) == J.wall_rgb("light_gray", CFG)


# --- P4-9: validation (BR-2.2, BR-6.1, BR-6.2) -----------------------------------------------------------------

@given(st.one_of(st.integers(-5, 120), st.floats(allow_nan=True, allow_infinity=True), st.text(max_size=5), st.none(), st.booleans()))
def test_p4_9_floors_override_accepts_exactly_integers_from_1_to_100(v):
    ok = isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 100
    if ok:
        assert J.validate_override("floors_above", v, "seen", CFG) == (v, "seen")
    else:
        with pytest.raises(ValueError):
            J.validate_override("floors_above", v, "seen", CFG)


@given(st.one_of(st.floats(allow_nan=True, allow_infinity=True), st.integers(-5, 600), st.text(max_size=5), st.none(), st.booleans()))
def test_p4_9_height_override_accepts_exactly_finite_numbers_from_2_to_500(v):
    ok = isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf") and 2 <= v <= 500
    if ok:
        assert J.validate_override("height_m", v, "seen", CFG) == (float(v), "seen")
    else:
        with pytest.raises(ValueError):
            J.validate_override("height_m", v, "seen", CFG)


@pytest.mark.parametrize("field, value, reason", [
    ("floor", 3, "x"), ("wall_color", "neon", "x"), ("wall_color", None, "x"), ("roof_shape", "dome", "x"), ("roof_shape", 3, "x"),
    ("floors_above", 3, ""), ("floors_above", 3, "   "), ("floors_above", 3, None), ("floors_above", 3, "a\\nb".replace("\\n", "\n")),
    ("floors_above", 3, "x" * 501), ("floors_above", 3, 5),
])
def test_p4_9_bad_overrides_are_refused(field, value, reason):
    with pytest.raises(ValueError):
        J.validate_override(field, value, reason, CFG)


@given(override_pairs(), REASONS)
def test_p4_9_good_overrides_pass_with_a_trimmed_reason(pair, reason):
    value, trimmed = J.validate_override(pair[0], pair[1], f"  {reason}  ", CFG)
    assert trimmed == reason.strip() and value == (float(pair[1]) if pair[0] == "height_m" else pair[1])


def good_judgement(**kw):
    return {"building_id": "gis:1", "floors_seen": 3, "confidence": "high", "height_est_m": None, "wall_color": "cream",
            "roof_shape": "flat", "views_used": [2, 1, 1], "note": "plain", **kw}


def test_p4_9_a_good_judgement_is_normalized():
    j = J.validate_judgement(good_judgement(), CFG, {1, 2, 3})
    assert j["views_used"] == [1, 2] and j["height_est_m"] is None


@pytest.mark.parametrize("change", [
    {"building_id": "gis 1"}, {"building_id": None}, {"floors_seen": 0}, {"floors_seen": 101}, {"floors_seen": 2.5},
    {"floors_seen": True}, {"confidence": None}, {"confidence": "sure"},
    {"height_est_m": 12.0}, {"floors_seen": None, "height_est_m": 1.0}, {"floors_seen": None, "height_est_m": 501},
    {"floors_seen": None, "height_est_m": float("nan")}, {"wall_color": "neon"}, {"roof_shape": "dome"}, {"views_used": []},
    {"views_used": [9]}, {"views_used": [0]}, {"views_used": "1"}, {"views_used": [True]}, {"note": "x" * 301},
    {"note": "a\nb"}, {"note": 5}, {"extra": 1},
])
def test_p4_9_bad_judgements_are_refused(change):
    with pytest.raises(ValueError):
        J.validate_judgement(good_judgement(**change), CFG, {1, 2, 3})


def test_p4_9_a_judgement_without_a_count_may_leave_confidence_empty():
    j = J.validate_judgement(good_judgement(floors_seen=None, confidence=None, wall_color=None, roof_shape=None, note=None, views_used=[1]), CFG, {1})
    assert j["floors_seen"] is None and j["confidence"] is None


# --- P4-7, P4-8: export file ------------------------------------------------------------------------------------

@st.composite
def export_rows(draw):
    ids = draw(st.lists(st.integers(1, 50).map(lambda n: f"gis:{n}"), unique=True, max_size=8))
    overrides, estimates = [], []
    for bid in ids:
        for field, value in draw(override_sets()).items():
            v, reason = J.validate_override(field, value, draw(REASONS), CFG)
            overrides.append({"building_id": bid, "field": field, "value": v, "reason": reason, "set_at": draw(TIMES)})
        if draw(st.booleans()):
            j = J.validate_judgement(draw(judgements(bid)), CFG, None)
            estimates.append({**j, "judged_at": draw(TIMES)})
    return overrides, estimates


CELL = "8930e0af13bffff"


@given(export_rows(), st.randoms(use_true_random=False))
def test_p4_8_the_export_text_does_not_depend_on_the_order_of_the_rows(rows, rnd):
    overrides, estimates = rows
    shuffled_o, shuffled_e = list(overrides), list(estimates)
    rnd.shuffle(shuffled_o)
    rnd.shuffle(shuffled_e)
    text = J.export_payload(CELL, overrides, estimates)
    assert text == J.export_payload(CELL, shuffled_o, shuffled_e)
    assert text.endswith("}\n") and not text.endswith("\n\n")
    data = json.loads(text)
    assert data["overrides"] == sorted(data["overrides"], key=lambda o: (o["building_id"], o["field"]))
    assert data["estimates"] == sorted(data["estimates"], key=lambda e: e["building_id"])


@given(export_rows())
def test_p4_7_parsing_an_export_gives_back_the_rows_and_exporting_again_gives_the_same_text(rows):
    overrides, estimates = rows
    text = J.export_payload(CELL, overrides, estimates)
    cell, o2, e2 = J.parse_export(text, CFG)
    assert cell == CELL
    assert o2 == sorted(overrides, key=lambda o: (o["building_id"], o["field"]))
    assert e2 == sorted(estimates, key=lambda e: e["building_id"])
    assert J.export_payload(cell, o2, e2) == text


def good_export(**kw):
    data = {"version": 1, "cell_id": CELL, "overrides": [{"building_id": "gis:1", "field": "floors_above", "value": 4, "reason": "seen",
                                                          "set_at": "2026-10-13T01:00:00+00:00"}], "estimates": [], **kw}
    return json.dumps(data)


def test_a_good_export_parses_and_bad_ones_are_refused_whole():
    assert J.parse_export(good_export(), CFG)[1][0]["value"] == 4
    one = {"building_id": "gis:1", "field": "floors_above", "value": 4, "reason": "seen", "set_at": "2026-10-13T01:00:00+00:00"}
    bad = [
        "not json", "[]", good_export(version=2), good_export(cell_id="xyz"), good_export(extra=1),
        good_export(overrides=[{**one, "value": 0}]), good_export(overrides=[{**one, "field": "color"}]),
        good_export(overrides=[{**one, "reason": ""}]), good_export(overrides=[{**one, "set_at": "yesterday"}]),
        good_export(overrides=[{**one, "building_id": "../x"}]), good_export(overrides=[{**one, "extra": 1}]),
        good_export(overrides=[one, one]), good_export(overrides=[one, {"building_id": "gis:2"}]),
        good_export(estimates=[{"building_id": "gis:1"}]), good_export(overrides="x"),
        good_export(estimates=[{"building_id": "gis:1", "floors_seen": 3, "confidence": "high", "height_est_m": None, "wall_color": "neon",
                                "roof_shape": None, "views_used": [1], "note": None, "judged_at": "2026-10-13T01:00:00+00:00"}]),
    ]
    for text in bad:
        with pytest.raises(ValueError):
            J.parse_export(text, CFG)
    with pytest.raises(ValueError):
        J.parse_export(" " * (J.MAX_EXPORT_BYTES + 1) + good_export(), CFG)


def test_a_photo_with_fewer_floors_keeps_the_register_height_of_a_tall_hall():
    b = {"building_id": "gis:1", "floors_above": 2, "height_m": 8.8}
    j = {"building_id": "gis:1", "floors_seen": 1, "confidence": "high", "height_est_m": None, "wall_color": None, "roof_shape": None}
    e = J.effective_building(b, j, None, CFG)
    assert (e.floors_above, e.height_m, e.height_basis) == (1, 8.8, "register")
