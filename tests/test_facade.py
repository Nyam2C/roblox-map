"""Facade tracing (2026-10-18): pieces -> parts and kits (facade_parts.py), the unfold homography (facade.py), build_luau.py and
the gate with a traced cell."""
from __future__ import annotations

import json
import math
import re

import numpy as np
import pytest

import build_luau as B
import facade
import facade_parts as FP
import gate as G
from test_build_luau import CELL, CFG, building

SPM = 3.6
BOX = {"x": 10.0, "y": 20.0, "z": -5.0, "w": 40.0, "h": 36.0, "d": 30.0, "r": 30.0}
WINDOW = {"kind": "window", "u0": 1.0, "u1": 3.0, "y0": 3.5, "y1": 5.5, "mullions_u": [2.0], "rgb": [60, 70, 80],
          "bars": {"du": 0.3, "y": [4.5]}}
BAND = {"kind": "slab", "u0": 0.0, "u1": 2.5, "y0": 3.0, "y1": 3.4, "depth_m": 0.4, "rgb": [200, 200, 200]}


def entry(**kw):
    return {"source": "trace", "face": {"axis": "z", "sign": -1}, "L_m": 40.0 / SPM, "H_m": 10.0, "floors": 3,
            "pieces": [WINDOW, BAND, {**WINDOW, "u0": 7.0, "u1": 9.0, "mullions_u": [8.0]}], **kw}


def test_repeat_writes_a_piece_once_for_every_floor():
    out = FP.expand([{**WINDOW, "repeat_dy": [3.0, 6.0]}, BAND])
    assert [p["y0"] for p in out] == [3.5, 6.5, 9.5, 3.0]
    assert out[2]["bars"]["y"] == [10.5] and "repeat_dy" not in out[0]


def test_a_stretched_window_keeps_its_size_and_a_band_stretches():
    w, b = FP.scale([WINDOW, BAND], 1.5, 2.0)
    assert w["u1"] - w["u0"] == pytest.approx(2.0) and (w["u0"] + w["u1"]) / 2 == pytest.approx(3.0)
    assert w["mullions_u"] == [pytest.approx(3.0)] and w["y1"] - w["y0"] == pytest.approx(2.0)
    assert b["u1"] == pytest.approx(3.75) and b["y1"] == pytest.approx(6.8)


def test_the_walls_face_out_and_run_left_to_right_as_seen_from_outside():
    ws = FP.walls(BOX, "z", -1, SPM)
    centre = (BOX["x"], BOX["z"])
    for side in FP.SIDES:
        w = ws[side]
        o, t, n = w["origin"], w["t"], w["n"]
        assert t == pytest.approx((n[2], 0.0, -n[0]))  # (-n) x up
        mid = (o[0] + t[0] * w["L_m"] * SPM / 2, o[2] + t[2] * w["L_m"] * SPM / 2)
        out = (mid[0] - centre[0], mid[1] - centre[1])
        assert out[0] * n[0] + out[1] * n[2] > 0  # the wall's middle is on its outward side
        assert o[1] == pytest.approx(BOX["y"] - BOX["h"] / 2)
    assert ws["front"]["L_m"] == pytest.approx(BOX["w"] / SPM) and ws["left"]["L_m"] == pytest.approx(BOX["d"] / SPM)
    # the left wall ends where the front starts (u = 0), the right wall starts where the front ends
    f, left, right = ws["front"], ws["left"], ws["right"]
    left_end = [left["origin"][i] + left["t"][i] * left["L_m"] * SPM for i in (0, 2)]
    assert left_end == pytest.approx([f["origin"][0], f["origin"][2]])
    front_end = [f["origin"][i] + f["t"][i] * f["L_m"] * SPM for i in (0, 2)]
    assert [right["origin"][0], right["origin"][2]] == pytest.approx(front_end)


def test_a_normal_names_its_wall():
    ax, az = FP.axes(BOX)
    assert FP.face_of_normal(BOX, ax) == ("x", 1) and FP.face_of_normal(BOX, [-v for v in az]) == ("z", -1)


def test_the_same_window_is_the_same_kit_on_another_building_and_mirrored_or_not():
    parts, kits = FP.parts_of(entry(), BOX, SPM)
    other = {**BOX, "x": 333.3, "z": 4501.7, "r": 79.756, "w": 47.0}
    parts2, kits2 = FP.parts_of(entry(), other, SPM)
    front_keys = {p["kit"] for p in parts[:10] if p["kit"]}
    assert front_keys <= set(kits2)  # the unit's own frame, not where the building stands
    assert all(isinstance(v, float) and math.copysign(1, v) > 0 for rows in kits.values() for r in rows for v in r[:3] if v == 0)
    kit_parts = [p for p in parts if p["kit"]]
    assert kit_parts and all(p["material"] == "SmoothPlastic" for p in kit_parts)


def test_wrap_carries_bands_round_and_mirrors_the_back():
    sides = FP.wrap([WINDOW, BAND, {**WINDOW, "u0": 7.0, "u1": 9.0}], 10.0, 6.0)
    band = [p for p in sides["left"] if p["kind"] == "slab"][0]
    assert band["u0"] == pytest.approx(-0.4) and band["u1"] == pytest.approx(6.4)  # past both corners by the band depth
    assert len([p for p in sides["left"] if p["kind"] == "window"]) == 2
    back = sorted((p["u0"], p["u1"]) for p in sides["back"] if p["kind"] == "window")
    assert back == [(1.0, 3.0), (7.0, 9.0)]


def test_rule_parts_of_the_traced_box_go_and_the_cap_plinth_and_back_yard_stay():
    front = FP.walls(BOX, "z", -1, SPM)["front"]
    out = (front["origin"][0] + front["n"][0] * 20 + front["t"][0] * 10, front["origin"][2] + front["n"][2] * 20 + front["t"][2] * 10)
    back = (BOX["x"] - front["n"][0] * 40, BOX["z"] - front["n"][2] * 40)
    f = {"axis": "z", "sign": -1}
    assert not FP.keep_rule_part({"name": "gis:1#w0f0-0", "kind": "facade", "x": BOX["x"], "z": BOX["z"]}, BOX, f, SPM)
    assert FP.keep_rule_part({"name": "gis:1#cap0", "kind": "facade", "x": BOX["x"], "z": BOX["z"]}, BOX, f, SPM)
    assert FP.keep_rule_part({"name": "gis:1", "kind": "building", "x": BOX["x"], "z": BOX["z"]}, BOX, f, SPM)
    assert not FP.keep_rule_part({"name": "gis:1#yw0", "kind": "prop", "x": out[0], "z": out[1]}, BOX, f, SPM)
    assert FP.keep_rule_part({"name": "gis:1#yw1", "kind": "prop", "x": back[0], "z": back[1]}, BOX, f, SPM)


def test_a_bad_piece_is_refused():
    with pytest.raises(ValueError):
        FP.check_piece({**WINDOW, "kind": "spaceship"})
    with pytest.raises(ValueError):
        FP.check_piece({**WINDOW, "u1": 0.5})
    with pytest.raises(ValueError):
        FP.check_piece({**WINDOW, "rgb": [300, 0, 0]})


def test_unfolding_and_folding_back_meet_within_a_pixel():
    geo = {"L_m": 8.4, "H_m": 13.6}
    corners = [(240.0, 690.0), (808.0, 668.0), (737.0, 95.0), (305.0, 175.0)]
    h, _ = facade.unfold_h(geo, corners, None)
    s = facade.PX_PER_M
    flat = np.array([[(0 + facade.MARGIN_M) * s, (13.6 + facade.ABOVE_M - 0) * s],
                     [(8.4 + facade.MARGIN_M) * s, (13.6 + facade.ABOVE_M - 13.6) * s]])
    back = facade.apply_h(h, flat)
    assert np.abs(back - np.array([corners[0], corners[2]])).max() < 1.0


def test_build_luau_swaps_a_traced_box_for_its_pieces_and_lists_its_kits():
    plain = B.plan_cell(CELL, [building(0)], [], CFG)
    bid = [i.name for i in plain.items if i.kind == "building"][0]
    plan = B.plan_cell(CELL, [building(0)], [], CFG, facade={bid: entry()})
    traced = [i for i in plan.items if i.name.startswith(bid + "#tp")]
    assert traced and any(i.kit for i in traced) and plan.counts["traced"] == 1
    kits = json.loads(plan.files["facade-kits.json"])["kits"]
    assert {i.kit for i in traced if i.kit} == set(kits)
    assert all(re.fullmatch(r'\{k="facade".*kt="fu-[0-9a-f]{12}".*\}', B.item_literal(i, CELL)) for i in traced if i.kit)
    assert not any(i.name.startswith(bid + "#w") for i in plan.items)  # the rule windows of that box are gone
    assert B.plan_cell(CELL, [building(0)], [], CFG, facade={bid: entry()}).files == plan.files  # deterministic (BR-14.8)


def test_a_bad_facade_file_refuses_the_build(tmp_path):
    path = tmp_path / "facade.json"
    path.write_text(json.dumps({"buildings": {"gis:1": {**entry(), "face": {"axis": "y", "sign": 1}}}}), encoding="utf-8")
    with pytest.raises(ValueError):
        B.load_facade(path)
    path.write_text(json.dumps({"buildings": {"gis:1": entry(pieces=[{**WINDOW, "rgb": None}])}}), encoding="utf-8")
    with pytest.raises(ValueError):
        B.load_facade(path)
    assert B.load_facade(tmp_path / "none.json") == {}


def test_a_traced_cell_needs_the_trace_check_and_no_cell_needs_g3():
    assert G.needed(1, False, traced=True) == ["g1", "g1_studio", "g2", "trace"]
    assert G.needed(1, False) == ["g1", "g1_studio", "g2"] and G.needed(2, True, traced=True) == ["g1", "g1_studio", "g2", "fps"]
    assert {"edge_threshold", "min_support", "min_piece_support", "min_top", "max_weak_rate", "max_parts_per_building"} \
        <= set(G.load_gate()["trace"])



def test_an_empty_lot_is_not_built_and_finish_sets_the_wall_material():
    plain = B.plan_cell(CELL, [building(0)], [], CFG)
    bid = [i.name for i in plain.items if i.kind == "building"][0]
    empty = B.plan_cell(CELL, [building(0)], [], CFG, facade={bid: {"source": "empty"}})
    assert not any(i.kind == "building" for i in empty.items) and any("no building" in w for w in empty.warnings)
    brick = B.plan_cell(CELL, [building(0)], [], CFG, facade={bid: entry(finish="brick")})
    paint = B.plan_cell(CELL, [building(0)], [], CFG, facade={bid: entry(finish="paint")})
    box = lambda plan: [i for i in plan.items if i.kind == "building"][0]  # noqa: E731
    assert box(brick).material == "Brick" and box(paint).material != "Brick"
    judged = B.plan_cell(CELL, [building(0)], [], CFG, details={bid: {"finish": "paint"}}, facade={bid: entry(finish="brick")})
    assert box(judged).material != "Brick"  # the 7-field judgement wins (mixed, 2026-10-19)


def test_the_bare_wall_colour_leaves_out_the_pieces():
    geo = {"H_m": 6.0, "L_m": 5.0, "floors": 2}
    s = facade.PX_PER_M
    flat = np.zeros((round((6 + facade.ABOVE_M + facade.MARGIN_M) * s), round((5 + 2 * facade.MARGIN_M) * s), 3), np.uint8)
    flat[:] = (150, 80, 60)
    window = {"u0": 1.0, "u1": 4.0, "y0": 3.5, "y1": 5.5}
    flat[round((6 + facade.ABOVE_M - 5.5) * s):round((6 + facade.ABOVE_M - 3.5) * s), round(2 * s):round(5 * s)] = (20, 20, 20)
    assert facade.wall_colour(flat, geo, [window], []) == [150, 80, 60]
    assert facade.wall_colour(flat, geo, [{"u0": 0, "u1": 5, "y0": 0, "y1": 6}], []) is None
