"""U8 lookalike.py: the crop camera, building outlines, colour difference, canaries and scoring of the look-alike gate (G3)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st
from PIL import Image

import gate as G
import layout
import lookalike as L
import review
from test_build_luau import CELL, CFG

GATE = G.load_gate()["g3"]


def pair(key="gis:1__1", bid="gis:1", bearing=0.0, pitch=0.0, fov=90.0, pos=(0.0, 5.4, 0.0)):
    dx, dy, dz = review.direction(bearing, pitch)
    return {"key": key, "building_id": bid, "rank": 1, "crop_fov_h_deg": fov, "crop": f"{CELL}/crops/{key}.jpg",
            "camera": {"position": list(pos), "look_at": [pos[0] + 100 * dx, pos[1] + 100 * dy, pos[2] + 100 * dz]}}


def bldg(n, x, z, w=40.0, d=40.0, h=36.0, owner=None):
    item = {"k": "building", "n": n, "x": x, "y": h / 2, "z": z, "w": w, "h": h, "d": d, "r": 0.0, "c": "beige"}
    if owner:
        item["i"] = owner
    return item


# --- the camera -----------------------------------------------------------------------------------------------------

def test_a_point_straight_ahead_is_in_the_middle_and_the_edge_of_the_view_at_the_edge():
    cam = L.camera_of(pair(bearing=90.0, fov=90.0))  # looking east (+X)
    mid = cam.to_px(cam.to_cam(np.array([[50.0, 5.4, 0.0]])))[0]
    assert mid == pytest.approx([512, 384], abs=1e-6)
    edge = cam.to_px(cam.to_cam(np.array([[50.0, 5.4, 50.0]])))[0]  # 45 degrees to the right of east is south (+Z)
    assert edge[0] == pytest.approx(1024, abs=1e-6)
    above = cam.to_px(cam.to_cam(np.array([[50.0, 30.0, 0.0]])))[0]
    assert above[1] < 384


@settings(max_examples=40)
@given(st.floats(0, 359.9), st.floats(-20, 30), st.floats(40, 100))
def test_the_camera_looks_where_review_points_the_studio_camera(bearing, pitch, fov):
    p = pair(bearing=bearing, pitch=pitch, fov=fov)
    cam = L.camera_of(p)
    target = np.array([p["camera"]["look_at"]])
    assert cam.to_px(cam.to_cam(target))[0] == pytest.approx([512, 384], abs=1e-6)
    assert abs(float(cam.right[1])) < 1e-9  # no roll: right stays level, like Studio's camera


# --- outlines --------------------------------------------------------------------------------------------------------

def test_a_building_in_front_fills_the_middle_and_one_behind_the_camera_is_not_seen():
    cam = L.camera_of(pair(bearing=0.0))  # looking north (-Z)
    parts = L.building_parts([bldg("gis:1", 0.0, -120.0)])
    visible, whole = L.outline_masks("gis:1", parts, cam)
    assert visible[384, 512] and whole.sum() == visible.sum() > 1000
    parts = L.building_parts([bldg("gis:1", 0.0, 120.0)])
    visible, whole = L.outline_masks("gis:1", parts, cam)
    assert not whole.any()


def test_a_nearer_building_hides_part_of_the_target():
    cam = L.camera_of(pair(bearing=0.0))
    far = bldg("gis:1", 0.0, -200.0, w=80, h=60)
    near = bldg("gis:2", -20.0, -60.0, w=30, h=20)
    visible, whole = L.outline_masks("gis:1", L.building_parts([far, near]), cam)
    assert 0 < visible.sum() < whole.sum()
    hidden, _ = L.outline_masks("gis:2", L.building_parts([far, near]), cam)
    assert hidden.sum() > 0  # the near one is seen whole over the far one


def test_boxes_and_roofs_of_one_building_make_one_outline():
    roof = {"k": "roof", "n": "gis:7#roof0", "i": "gis:7", "x": 0.0, "y": 40.0, "z": -120.0, "w": 40.0, "h": 8.0, "d": 40.0, "r": 0.0}
    parts = L.building_parts([bldg("gis:7#b0", 0.0, -120.0, owner="gis:7"), roof, bldg("gis:8", 300.0, 0.0)])
    assert sorted(parts) == ["gis:7", "gis:8"] and len(parts["gis:7"]) == 2


def test_clip_near_cuts_a_face_that_crosses_the_camera_plane():
    poly = np.array([[-1.0, 0.0, -5.0], [1.0, 0.0, -5.0], [1.0, 0.0, 5.0], [-1.0, 0.0, 5.0]])
    cut = L.clip_near(poly, 0.3)
    assert len(cut) == 4 and (cut[:, 2] >= 0.3 - 1e-9).all()


# --- colour ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("lab1,lab2,want", [  # Sharma, Wu and Dalal (2005), table 1, pairs 1-4 and 7
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
    ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000),
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
])
def test_de2000_matches_the_published_pairs(lab1, lab2, want):
    assert L.de2000(lab1, lab2) == pytest.approx(want, abs=1e-4)
    assert L.de2000(lab2, lab1) == pytest.approx(want, abs=1e-4)


def test_lab_of_white_and_black():
    assert L.srgb_to_lab([255, 255, 255]) == pytest.approx([100.0, 0.0, 0.0], abs=0.01)
    assert L.srgb_to_lab([0, 0, 0]) == pytest.approx([0.0, 0.0, 0.0], abs=0.01)


@given(st.lists(st.integers(0, 255), min_size=3, max_size=3), st.lists(st.integers(1, 255), min_size=3, max_size=3))
def test_a_render_that_already_matches_keeps_its_colour(current, seen):
    assert L.corrected(current, seen, seen, 0.6, 1.6) == pytest.approx(current, abs=1)


def test_the_correction_moves_toward_the_photo_inside_its_bounds():
    brighter = L.corrected([150, 150, 150], [220, 200, 160], [120, 120, 120], 0.6, 1.6)
    assert all(b > 150 for b in brighter)
    capped = L.corrected([100, 100, 100], [255, 255, 255], [10, 10, 10], 0.6, 1.6)  # a 50 times brighter photo: 1.6 at most
    assert capped == [int(round(v)) for v in L.linear_to_srgb(L.srgb_to_linear([100, 100, 100]) * 1.6)]


def test_measure_reads_the_wall_and_leaves_foliage_out():
    mask = np.zeros((768, 1024), bool)
    mask[100:700, 200:800] = True
    photo = np.zeros((768, 1024, 3), np.uint8)
    photo[...] = (214, 192, 156)  # beige wall
    photo[100:300, 200:400] = (60, 140, 50)  # a tree in front of it
    render = np.zeros_like(photo)
    render[...] = (200, 200, 205)
    m = L.measure(photo, render, mask, GATE)
    assert m["photo"] == [214, 192, 156] and m["render"] == [200, 200, 205] and m["de"] > 10
    assert L.measure(photo, render, np.zeros_like(mask), GATE) is None


# --- slots, canaries, scores -----------------------------------------------------------------------------------------

def test_slots_hold_every_pair_once_and_the_canaries_the_same_way_each_time():
    keys = [f"gis:{n}__1" for n in range(10)]
    a, b = L.slot_plan(keys, CELL, 2, 2), L.slot_plan(keys, CELL, 2, 2)
    assert a == b and len(a) == 14 and [s["slot"] for s in a] == [f"S{n:03d}" for n in range(1, 15)]
    assert sorted(s["key"] for s in a if s["kind"] == "pair") == sorted(keys)
    swaps = [s for s in a if s["kind"] == "swap"]
    assert len(swaps) == 2 and all(s["other"] != s["key"] for s in swaps)
    assert L.slot_plan(keys, "another seed", 2, 2) != a
    assert [s["kind"] for s in L.slot_plan(["only"], CELL, 2, 2)].count("swap") == 0


def answer(slot, score=2, same=True, **fix):
    return {"slot": slot, "attrs": {a: score for a in L.ATTRS}, "same_building": same, "fix": [fix] if fix else [], "note": ""}


def test_scores_must_answer_every_slot_with_known_values():
    slots = [{"slot": "S001", "kind": "pair", "key": "k"}]
    assert L.check_scores({"slots": [answer("S001")]}, slots)["S001"]["same_building"]
    with pytest.raises(ValueError, match="expected"):
        L.check_scores({"slots": []}, slots)
    bad = answer("S001")
    bad["attrs"]["roof"] = 3
    with pytest.raises(ValueError, match="0, 1 or 2"):
        L.check_scores({"slots": [bad]}, slots)
    with pytest.raises(ValueError, match="route"):
        L.check_scores({"slots": [answer("S001", attr="roof", route="paint")]}, slots)


def scored_cell(pair_score=2, swap_score=0, swap_same=False, dup_score=None):
    keys = [f"gis:{n}__1" for n in range(6)]
    slots = L.slot_plan(keys, CELL, 2, 2)
    by_key = {}
    rows = {}
    for s in slots:
        if s["kind"] == "pair":
            rows[s["slot"]] = answer(s["slot"], pair_score)
            by_key[s["key"]] = rows[s["slot"]]
    for s in slots:
        if s["kind"] == "swap":
            rows[s["slot"]] = answer(s["slot"], swap_score, swap_same)
        elif s["kind"] == "dup":
            rows[s["slot"]] = answer(s["slot"], pair_score if dup_score is None else dup_score)
    pairs = {k: {"building_id": k.split("__")[0]} for k in keys}
    return rows, slots, pairs


def test_a_scorer_that_misses_a_swap_or_scores_a_pair_two_ways_is_not_believed():
    rows, slots, _ = scored_cell()
    assert L.canary_report(rows, slots, GATE)["valid"]
    rows, slots, _ = scored_cell(swap_score=2, swap_same=True)
    report = L.canary_report(rows, slots, GATE)
    assert not report["valid"] and {m["kind"] for m in report["missed"]} == {"swap"}
    rows, slots, _ = scored_cell(pair_score=2, dup_score=0)
    assert {m["kind"] for m in L.canary_report(rows, slots, GATE)["missed"]} == {"dup"}


def test_judge_fails_low_looks_and_counts_the_cell():
    rows, slots, pairs = scored_cell(pair_score=2)
    out = L.judge(rows, slots, pairs, {}, set(), GATE)
    assert out["pass"] and out["failed"] == [] and out["buildings_scored"] == 6
    weak = next(s["slot"] for s in slots if s["kind"] == "pair")
    rows[weak]["attrs"]["color"] = 0  # a key look at 0 fails the building whatever the total
    rows[weak]["fix"] = [{"attr": "color", "route": "rule", "want": "two-tone facade, dark base"}]
    out = L.judge(rows, slots, pairs, {}, set(), GATE)
    assert len(out["failed"]) == 1 and out["fail_rate"] == pytest.approx(1 / 6, abs=1e-3)
    assert out["pass"] == (1 / 6 <= GATE["max_fail_rate"])
    assert out["gaps"][0]["want"].startswith("color: two-tone") and out["tickets"][0]["low"] == ["color"]


def test_a_facility_needs_the_higher_total():
    rows, slots, pairs = scored_cell(pair_score=1)  # 6 of 12 everywhere
    for r in rows.values():
        r["attrs"].update({"color": 2, "finish": 2})  # 8 of 12: a building passes, a facility does not
    bid = next(iter(pairs.values()))["building_id"]
    out = L.judge(rows, slots, pairs, {}, {bid}, GATE)
    assert out["failed"] == [bid] and out["facilities_failed"] == [bid] and "facilities" in out["fail"]


# --- files end to end ------------------------------------------------------------------------------------------------

def test_sheets_and_score_end_to_end(tmp_path, monkeypatch):
    build, gate_dir, captures = tmp_path / "build", tmp_path / "gate", tmp_path / "captures"
    monkeypatch.setattr(G, "BUILD_DIR", str(build))
    monkeypatch.setattr(G, "GATE_DIR", str(gate_dir))
    cfg = {**CFG, "captures_dir": str(captures)}
    pairs = [pair(f"gis:{n}__1", f"gis:{n}", bearing=0.0, pos=(60.0 * n, 5.4, 0.0)) for n in range(4)]
    (build / CELL).mkdir(parents=True)
    (build / CELL / "review.json").write_text(json.dumps({"cell_id": CELL, "batches": [{"number": 1, "pairs": pairs}]}), encoding="utf-8")
    chunk = {"looks": {"walls": {"beige": [214, 192, 156]}}, "items": [bldg(f"gis:{n}", 60.0 * n, -120.0) for n in range(4)]}
    (build / CELL / "chunks.json").write_text(json.dumps({"cell_id": CELL, "chunks": [chunk]}), encoding="utf-8")
    shots = {}
    for p in pairs:
        crop = captures / p["crop"]
        crop.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1024, 768), (214, 192, 156)).save(crop)
        shot = tmp_path / f"{p['key'].replace(':', '_')}.png"
        Image.new("RGB", (1200, 800), (150, 150, 150)).save(shot)
        shots[p["key"]] = str(shot)
    (tmp_path / "captures.json").write_text(json.dumps(shots), encoding="utf-8")
    made = L.make_sheets(cfg, CELL, tmp_path / "captures.json", GATE)
    assert made["pairs"] == 4 and made["slots"] == 4 + GATE["canaries_swap"] + GATE["canaries_dup"] and made["warnings"] == []
    listing = json.loads((gate_dir / CELL / "g3" / "score-list.json").read_text(encoding="utf-8"))
    assert all(Path(s["sheet"]).is_file() for s in listing["sheets"])
    assert "kind" not in json.dumps(listing)  # the scorer's list never says which slot is a canary
    slots = json.loads((gate_dir / CELL / "g3" / "slots.json").read_text(encoding="utf-8"))["slots"]
    rows = [answer(s["slot"], 0 if s["kind"] == "swap" else 2, s["kind"] != "swap") for s in slots]
    (tmp_path / "scores.json").write_text(json.dumps({"slots": rows}), encoding="utf-8")
    out = L.score_cell(cfg, CELL, tmp_path / "scores.json", GATE)
    assert out["pass"] and out["canaries"]["valid"] and out["buildings_scored"] == 4
    colours = json.loads((gate_dir / CELL / "g3" / "colours.json").read_text(encoding="utf-8"))["colours"]
    assert colours["gis:0__1"]["photo"] == pytest.approx([214, 192, 156], abs=2)  # the crop is a JPEG
    assert colours["gis:0__1"]["render"] == [150, 150, 150]
    assert out["coverage"] == 1.0
    del shots[pairs[0]["key"]], shots[pairs[1]["key"]]  # half the buildings never captured
    (tmp_path / "captures.json").write_text(json.dumps(shots), encoding="utf-8")
    L.make_sheets(cfg, CELL, tmp_path / "captures.json", GATE)
    slots = json.loads((gate_dir / CELL / "g3" / "slots.json").read_text(encoding="utf-8"))["slots"]
    rows = [answer(s["slot"], 0 if s["kind"] == "swap" else 2, s["kind"] != "swap") for s in slots]
    (tmp_path / "scores.json").write_text(json.dumps({"slots": rows}), encoding="utf-8")
    half = L.score_cell(cfg, CELL, tmp_path / "scores.json", GATE)
    assert "coverage" in half["fail"] and half["coverage"] == 0.5
    lenient = [answer(s["slot"]) for s in slots]
    (tmp_path / "lenient.json").write_text(json.dumps({"slots": lenient}), encoding="utf-8")
    assert L.score_cell(cfg, CELL, tmp_path / "lenient.json", GATE)["fail"][0] == "scorer_invalid"


def test_wall_fixes_turn_a_measured_colour_into_a_corrected_wall():
    items = [bldg("gis:1", 0, 0)]
    result = {"tickets": [{"building": "gis:1", "color": {"de": 30.0, "photo": [230, 210, 170], "render": [150, 150, 150], "pixels": 5000}}]}
    fixes = L.wall_fixes(result, items, {"beige": [214, 192, 156]}, GATE)
    assert fixes["gis:1"]["was"] == [214, 192, 156] and fixes["gis:1"]["rgb"] != [214, 192, 156]
    assert L.wall_fixes({"tickets": [{"building": "gis:1", "color": None}]}, items, {"beige": [1, 2, 3]}, GATE) == {}


def test_gaps_are_counted_over_cells(tmp_path):
    for cell, gaps in (("a", [{"want": "finish: stone base", "buildings": ["gis:1", "gis:2"]}]),
                       ("b", [{"want": "Finish: stone base", "buildings": ["gis:9"]}, {"want": "roof: blue tile", "buildings": ["gis:3"]}])):
        (tmp_path / cell).mkdir()
        (tmp_path / cell / "g3.json").write_text(json.dumps({"gaps": gaps}), encoding="utf-8")
    rows = L.all_gaps(tmp_path)
    assert rows[0] == {"want": "finish: stone base", "buildings": 3, "cells": ["a", "b"]} and rows[1]["buildings"] == 1
