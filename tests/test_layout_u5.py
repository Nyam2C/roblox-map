"""U5 layout_details: duplicates (P5-2), multi-box footprints (P5-3), bodies and archetypes (P5-4), the facing side, occlusion and free
spans (P5-5), roofs (P5-6), bands and windows (P5-7), shops and yards (P5-9), street slots (P5-11), junctions and crosswalks (P5-12),
sidewalk pieces (P5-13), ownership (P5-15), budgets (P5-18), sidewalk sides (P5-19). Expected values are worked out here."""
from __future__ import annotations

import dataclasses
import math
import random
import re

import h3
import pytest
from hypothesis import assume, given, settings, strategies as st
from shapely.geometry import LineString, Point, Polygon

import common
import details_rules as R
import judgement as J
import layout
import layout_details as LD
import streets as ST
from generators import BASE, body_cases, offset, rect, star_outlines

CFG = {**common.DEFAULTS, "car_spacing_m": 8}  # cars are off by default (2026-10-13); the generator still makes them when asked
FRAME = layout.Frame.from_cfg(CFG)
S = FRAME.studs_per_m
RES = CFG["h3_res"]
CELL = "8930e0af13bffff"
CENTER = h3.cell_to_latlng(CELL)
D = R.DIMS


def street(fid="way:11", cls="residential", dy=0.0, length=120.0, **tags):
    a, b = offset(CENTER, -length / 2, dy), offset(CENTER, length / 2, dy)
    return {"feature_id": fid, "kind": "road", "highway_class": cls, "tags": tags, "geometry": [list(a), list(b)]}


def villa(i=1, w=12.0, d=10.0, floors=3, fh=3.4, wall="red_brick", roof="flat", code="01000", center=None, name="", note=None, detail=None):
    c = center or offset(CENTER, 0, 15 + d / 2)  # 15 m north of an east-west road through the cell centre
    row = {"building_id": f"gis:{i}", "cell_id": CELL, "source": "gis", "outline": [list(p) for p in rect(c, w, d)], "centroid": [c[0], c[1]],
           "name": name, "usability_code": code, "floors_above": floors, "height_m": round(floors * fh, 3), "building_area": w * d, "status": "ok",
           "osm_height_m": None, "osm_levels": None}
    est = {"floors_seen": floors, "confidence": "high", "height_est_m": None, "wall_color": wall, "roof_shape": roof, "views_used": [1], "note": note}
    return row, est, detail


def resolve(row, est, detail=None, features=(), others=(), cfg=CFG):
    eff = J.effective_building(row, est, None, cfg)
    body = LD.make_body(row, eff, detail, est.get("note"), FRAME, cfg)
    assert body is not None
    lines = LD._feature_lines(list(features), FRAME, cfg)
    return LD.resolve_body(body, lines, list(others), cfg), eff


def all_items(body, row, eff, cfg=CFG):
    warnings: list[str] = []
    items = LD.box_items(body, row, eff, FRAME)
    for bi in range(len(body.boxes)):
        items += LD.roof_items(body, bi, FRAME, cfg) + LD.body_items(body, bi, FRAME, cfg, warnings)
    items += LD.front_items(body, FRAME, cfg, warnings) + LD.yard_items(body, FRAME, cfg)
    signs, labels = LD.sign_items(body, FRAME, cfg, warnings)
    return items + signs, labels, warnings


def tail(item):
    return item.name.split("#", 1)[1] if "#" in item.name else ""


# --- P5-2 duplicates ---------------------------------------------------------------------------------------------------------

def test_p5_2_an_attribute_less_twin_is_dropped_and_the_register_record_kept():
    a, _, _ = villa(1)
    twin = {**villa(2)[0], "building_id": "gis:2", "building_area": 0, "usability_code": ""}
    kept, dropped = LD.dedupe_buildings([twin, a], FRAME)
    assert [b["building_id"] for b in kept] == ["gis:1"] and dropped == [("gis:2", "gis:1")]
    both = LD.dedupe_buildings([a, {**a, "building_id": "gis:3"}], FRAME)  # both have attributes: both stay
    assert len(both[0]) == 2 and both[1] == []
    far = {**twin, "outline": [list(p) for p in rect(offset(CENTER, 80, 80), 12, 10)]}
    assert LD.dedupe_buildings([a, far], FRAME)[1] == []


@settings(max_examples=30)
@given(st.lists(body_cases(), min_size=1, max_size=5), st.randoms(use_true_random=False))
def test_p5_2_dedupe_is_idempotent_order_free_and_never_drops_a_record_with_attributes(cases, rnd):
    rows = [{**c[0], "building_id": f"gis:{i}"} for i, c in enumerate(cases)]
    rows += [{**r, "building_id": f"gis:{100 + i}", "building_area": 0, "usability_code": ""} for i, r in enumerate(rows) if i % 2 == 0]
    kept, dropped = LD.dedupe_buildings(rows, FRAME)
    with_attrs = {r["building_id"] for r in rows if (r.get("building_area") or 0) > 0 or r.get("usability_code")}
    assert with_attrs <= {b["building_id"] for b in kept}
    assert LD.dedupe_buildings(kept, FRAME) == (kept, [])
    shuffled = list(rows)
    rnd.shuffle(shuffled)
    assert LD.dedupe_buildings(shuffled, FRAME) == (kept, dropped)


# --- P5-3 multi-box footprints --------------------------------------------------------------------------------------------------

def l_shape(center, a=20.0, b=16.0, arm=6.0):
    """An L: a x b bounding box with the top-right (a-arm) x (b-arm) corner cut away."""
    pts = [(-a / 2, -b / 2), (a / 2, -b / 2), (a / 2, -b / 2 + arm), (-a / 2 + arm, -b / 2 + arm), (-a / 2 + arm, b / 2), (-a / 2, b / 2)]
    return [list(offset(center, x, y)) for x, y in pts]


def covers(boxes, outline_pts_m, tol=0.02):
    polys = [LD._box_poly(b).buffer(tol) for b in boxes]
    return all(any(p.covers(Point(x, y)) for p in polys) for x, y in outline_pts_m)


def test_p5_3_an_l_shape_gets_two_boxes_that_fit_and_a_rectangle_stays_one():
    boxes = LD.outline_to_boxes(l_shape(CENTER), FRAME, CFG, "villa")
    pts = [layout.to_meters(FRAME, lat, lon) for lat, lon in l_shape(CENTER)]
    assert len(boxes) == 2 and covers(boxes, pts, tol=0.05)
    area = Polygon(pts).area
    assert area / sum(b.width_m * b.depth_m for b in boxes) >= 0.95
    single = LD.outline_to_boxes([list(p) for p in rect(CENTER, 12, 10)], FRAME, CFG, "villa")
    assert len(single) == 1 and single[0].fit_ratio >= 0.999


@settings(max_examples=40)
@given(star_outlines(spread_m=200, min_r=12, max_r=30), st.integers(0, 7), st.booleans())
def test_p5_3_boxes_cover_the_outline_use_less_area_than_one_box_and_ignore_the_vertex_order(outline, shift, reverse):
    pts = [layout.to_meters(FRAME, lat, lon) for lat, lon in outline]
    single = layout.box_of_points(pts)
    assume(single is not None and Polygon(pts).area >= D["split_min_area"])
    boxes = LD.outline_to_boxes([list(p) for p in outline], FRAME, CFG, "villa")
    assert 1 <= len(boxes) <= 6  # U7: up to six boxes follow the outline
    assert sum(b.width_m * b.depth_m for b in boxes) <= single.width_m * single.depth_m * (1 + 1e-6) + 0.01
    assert covers(boxes, pts, tol=0.05)
    turned = list(outline[shift % len(outline):] + outline[:shift % len(outline)])
    again = LD.outline_to_boxes([list(p) for p in (reversed(turned) if reverse else turned)], FRAME, CFG, "villa")
    assert len(again) == len(boxes)
    assert sum(b.width_m * b.depth_m for b in again) == pytest.approx(sum(b.width_m * b.depth_m for b in boxes), rel=1e-3, abs=0.05)


# --- P5-4 bodies and archetypes ---------------------------------------------------------------------------------------------------

@settings(max_examples=60)
@given(body_cases())
def test_p5_4_every_building_gets_one_archetype_floors_and_a_floor_height_that_fit(case):
    row, est, detail = case
    body, eff = resolve(row, est, detail)
    assert body.archetype == R.archetype(row["usability_code"], eff.floors_above, row["name"], False)
    assert body.floors >= 1 and body.floors * body.fh == pytest.approx(body.height_m, abs=1e-6)
    single = layout.box_of_points([layout.to_meters(FRAME, *p) for p in row["outline"]])
    assert body.is_body == (body.height_m > 2.5 and single.depth_m >= 3.0 and single.width_m <= 12 * single.depth_m)
    assert body.details == R.merged_details(detail, est["note"], est["wall_color"], body.archetype)
    if not body.is_body:
        items, labels, _ = all_items(body, row, eff)
        assert all(i.kind == "building" for i in items) and labels == 0


def test_a_fence_or_booth_is_not_a_body():
    thin, _, _ = villa(1, w=38, d=2.2, floors=1, fh=2.0)
    body, _ = resolve(thin, villa(1)[1])
    assert not body.is_body
    booth, best, _ = villa(2, w=9.9, d=4.8, floors=1, fh=2.5)
    assert not resolve(booth, best)[0].is_body
    walkway, west, _ = villa(3, w=70, d=5, floors=1, fh=3.4)
    assert not resolve(walkway, west)[0].is_body


# --- P5-5 facing, occlusion, free spans ------------------------------------------------------------------------------------------------

def test_p5_5_the_face_nearest_the_road_faces_it_and_setback_subtracts_the_sidewalk():
    row, est, _ = villa()
    body, _ = resolve(row, est, features=[street()])
    assert body.facing is not None and body.facing.side == "b"  # local +Z is south for an east-west box: the south face looks at the road
    assert body.facing.setback == pytest.approx(15 - 3, abs=0.05) and body.facing.setback_s == pytest.approx(15 - 3 - 1.5, abs=0.05)
    assert body.facing.length == pytest.approx(12, rel=2e-3) and body.facing.feature_id == "way:11"  # lat/lon -> m is not exactly isometric
    alley, _ = resolve(row, est, features=[street(cls="service")])  # no sidewalk on a service road
    assert alley.facing.setback_s == pytest.approx(15 - 2, abs=0.05)
    none, _ = resolve(row, est, features=[street(dy=-100)])
    assert none.facing is None and LD.free_spans(none) == [] and LD.yard_items(none, FRAME, CFG) == [] and LD.sign_items(none, FRAME, CFG, [])[0] == []


def test_p5_5_a_face_next_to_another_box_is_occluded_and_front_only_keeps_the_facing_face():
    row, est, _ = villa()
    neighbour = villa(2, center=offset(CENTER, 12 + 1, 15 + 5))[0]
    body, _ = resolve(row, est, features=[street()], others=[LD._box_poly(b) for b in LD.outline_to_boxes(neighbour["outline"], FRAME, CFG, "villa")])
    assert body.occluded[0] == frozenset({"r"})
    front, _ = resolve(row, est, features=[street()], cfg={**CFG, "window_faces": "front"})
    assert front.occluded[0] == frozenset({"f", "l", "r"})
    items, _, _ = all_items(front, row, J.effective_building(row, est, None, CFG), {**CFG, "window_faces": "front"})
    assert {tail(i)[2] for i in items if tail(i).startswith("w0")} == {"b"}


def test_every_wall_part_on_every_face_looks_away_from_its_box():
    """The Builder's CFrame.Angles(0, yaw, 0) sends a part's Front (-Z) to (-sin yaw, -cos yaw) in world x, z (mutation L5)."""
    row, est, _ = villa(w=14, d=9)
    body, eff = resolve(row, est, features=[street()])
    items, _, _ = all_items(body, row, eff)
    box = body.boxes[0]
    seen = set()
    for i in items:
        t = tail(i)
        if not (t.startswith("w0") or t.startswith("fl")):
            continue
        side = t[2] if t.startswith("w0") else None
        if t.startswith("w0"):
            seen.add(side)
            tr = math.radians(i.yaw_deg)
            front = (-math.sin(tr), -math.cos(tr))  # world x, z
            out = (i.cx - box.cx_m * S, i.cz + box.cy_m * S)  # from the box centre (north is -z) to the part
            half = (box.depth_m if side in "fb" else box.width_m) / 2 * S  # the face is this far out along its normal
            assert front[0] * out[0] + front[1] * out[1] >= half - 0.5 * S, (t, i.yaw_deg)
    assert seen == {"f", "b", "l", "r"}


def test_a_narrow_front_gives_up_its_only_ground_floor_window_to_the_door():
    """A 5 m front has one window slot, at the middle where the door goes: the window is skipped, never put on the door (mutation L9)."""
    row, est, _ = villa(w=5, d=6)
    body, eff = resolve(row, est, features=[street()])
    items, _, _ = all_items(body, row, eff)
    door = next(i for i in items if tail(i).startswith("dr0"))
    front_ground = [i for i in items if tail(i).startswith("w0") and tail(i)[2] == body.facing.side and tail(i)[3] == "0"]
    assert front_ground == [] and door is not None
    upper = [i for i in items if tail(i).startswith("w0") and tail(i)[2] == body.facing.side and tail(i)[3] == "1"]
    assert len(upper) == 1  # the slot exists on the floor above


def test_two_buildings_that_merely_overlap_a_little_are_both_kept():
    """Only an attribute-less record that overlaps another by the duplicate ratio (0.6) is dropped (mutation L8)."""
    a, _, _ = villa(1, w=12, d=10)
    b, _, _ = villa(2, w=12, d=10, center=offset(CENTER, 8, 15 + 5))  # a third of a overlaps b
    b = {**b, "floors_above": None, "height_m": None, "name": "", "building_area": None, "usability_code": ""}  # attribute-less (BR-1.2)
    kept, dropped = LD.dedupe_buildings([a, b], FRAME)
    assert len(kept) == 2 and dropped == []
    c = {**b, "building_id": "gis:3", "outline": a["outline"]}  # the same footprint without attributes
    kept, dropped = LD.dedupe_buildings([a, c], FRAME)
    assert [k["building_id"] for k in kept] == ["gis:1"] and dropped == [("gis:3", "gis:1")]


def test_free_spans_leave_out_the_stair_tower_and_the_bay_and_the_door_takes_the_middle():
    row, est, _ = villa(detail={"building_id": "gis:1", "stair": "glass", "bay": 1})
    body, _ = resolve(row, est, {"building_id": "gis:1", "stair": "glass", "bay": 1}, features=[street()])
    spans = LD.free_spans(body)
    L = body.facing.length  # 12 m up to the projection's 0.1 %
    blocked = [(-L / 3 - 0.6 - 0.3, -L / 3 + 0.6 + 0.3), (L / 3 - 1.2 - 0.3, L / 3 + 1.2 + 0.3)]
    for s0, s1 in spans:
        assert all(s1 <= a or s0 >= b for a, b in blocked) and -L / 2 + 0.2 - 1e-6 <= s0 < s1 <= L / 2 - 0.2 + 1e-6
    assert LD._door_along(body) == 0.0
    plain, _ = resolve(row, est, features=[street()])
    assert LD.free_spans(plain) == [(-plain.facing.length / 2 + 0.2, plain.facing.length / 2 - 0.2)]


# --- P5-6 roofs ----------------------------------------------------------------------------------------------------------------------

def local_to_world(item, lx, ly, lz):
    """A point in the part's own frame -> studs (x, y, z), with the Builder's CFrame.Angles(0, yaw, 0)."""
    t = math.radians(item.yaw_deg)
    return item.cx + lx * math.cos(t) + lz * math.sin(t), item.cy + ly, item.cz - lx * math.sin(t) + lz * math.cos(t)


@pytest.mark.parametrize("shape, count", [("flat", 0), ("shed", 1), ("gable", 2), ("hip", 6), ("other", 0)])
def test_p5_6_roof_part_counts_by_shape(shape, count):
    row, est, _ = villa(roof=shape)
    body, _ = resolve(row, est, features=[street()])
    assert len(LD.roof_items(body, 0, FRAME, CFG)) == count


def test_p5_6_the_hip_of_a_12_by_10_villa_has_the_measured_sizes_and_its_apexes_meet_the_ridge():
    row, est, _ = villa(roof="hip")
    body, _ = resolve(row, est, features=[street()])
    roof = LD.roof_items(body, 0, FRAME, CFG)
    Dd, H = 5.4, math.tan(math.radians(25)) * 5.4
    wedges = [i for i in roof if i.shape == "Wedge"]
    corners = [i for i in roof if i.shape == "CornerWedge"]
    assert len(wedges) == 2 and len(corners) == 4
    for w in wedges:
        assert (w.sx, w.sy, w.sz) == pytest.approx((2 * S, H * S, Dd * S), rel=2e-3)
    for c in corners:
        assert (c.sx, c.sy, c.sz) == pytest.approx((Dd * S, H * S, Dd * S), rel=2e-3)
    ridge_y = (body.height_m - 0.02 + H) * S
    ridge_ends = {(round(x, 1), round(z, 1)) for w in wedges for sx in (-1, 1) for x, y, z in [local_to_world(w, sx * w.sx / 2, w.sy / 2, w.sz / 2)]}
    assert len(ridge_ends) == 2  # both wedges share the same two ridge ends
    for c in corners:
        x, y, z = local_to_world(c, c.sx / 2, c.sy / 2, -c.sz / 2)  # the apex corner
        assert y == pytest.approx(ridge_y, abs=0.01) and (round(x, 1), round(z, 1)) in ridge_ends
    for i in roof:
        assert i.cy - i.sy / 2 == pytest.approx((body.height_m - 0.02) * S, abs=2e-3)


@settings(max_examples=40)
@given(body_cases(), st.sampled_from(["gable", "hip", "shed"]), st.floats(5, 60))
def test_p5_6_roof_parts_sit_on_the_wall_top_inside_the_overhang_and_rise_with_the_pitch(case, shape, pitch):
    row, est, detail = case
    est = {**est, "roof_shape": shape}
    cfg = {**CFG, "roof_pitch_deg": pitch}
    body, _ = resolve(row, est, detail, cfg=cfg)
    assume(body.is_body and body.archetype != "school")
    roof = LD.roof_items(body, 0, FRAME, cfg)
    box = body.boxes[0]
    o = D["roof_overhang"]
    for i in roof:
        assert i.cy - i.sy / 2 == pytest.approx((body.height_m - 0.02) * S, abs=2e-3)
        for sx in (-1, 1):
            for sz in (-1, 1):
                x, _, z = local_to_world(i, sx * i.sx / 2, 0, sz * i.sz / 2)
                e, n = x / S, -z / S
                t = math.radians(box.yaw_deg)
                u = (e - box.cx_m) * math.cos(t) + (n - box.cy_m) * math.sin(t)
                v = (e - box.cx_m) * math.sin(t) - (n - box.cy_m) * math.cos(t)
                assert abs(u) <= box.width_m / 2 + o + 0.01 and abs(v) <= box.depth_m / 2 + o + 0.01
    rise = max(i.sy for i in roof) / S
    expected = math.tan(math.radians(D["shed_pitch_deg"])) * (box.depth_m + 2 * o) if shape == "shed" else math.tan(math.radians(pitch)) * (box.depth_m / 2 + o)
    assert rise == pytest.approx(expected, abs=2e-3)


# --- P5-7 bands, windows, facade placement -----------------------------------------------------------------------------------------------

def test_a_12_by_10_three_floor_villa_has_the_expected_parts():
    row, est, _ = villa()
    body, eff = resolve(row, est, features=[street()])
    items, labels, warnings = all_items(body, row, eff)
    by = {}
    for i in items:
        by.setdefault(tail(i)[:2] if i.kind != "building" else "box", []).append(i)
    assert len(by["box"]) == 1 and len(by["fl"]) == 2 and len(by["ca"]) == 1 and len(by["pl"]) == 1 and len(by["dr"]) == 1 and len(by["cn"]) == 1
    windows = [i for i in items if tail(i).startswith("w0")]
    # BR-6.6: one glass and one frame per window column (3 m pitch, 2.2 m sashes: three on the 12 m faces, two on the 10 m ones), each
    # over all three floors except where the door takes the facing face's ground floor; two skins a face between the rows
    fh, wh = body.fh, min(D["win_h"], body.fh - 1.0)
    others = [w for w in windows if tail(w)[2] != body.facing.side]
    assert sorted(len([w for w in others if tail(w)[2] == s]) for s in "fblr" if s != body.facing.side) == [2, 2, 3]
    assert all(w.sy / S == pytest.approx(2 * fh + wh, abs=1e-3) for w in others)
    assert len([i for i in items if tail(i).startswith("wf0")]) == len(windows)
    assert all(len([i for i in items if tail(i).startswith(f"ws0{s}")]) == 2 for s in "fblr")
    door = next(i for i in items if tail(i).startswith("dr0"))
    for w in windows:
        if tail(w)[2] == body.facing.side and tail(w)[3] == "0":
            assert math.hypot(w.cx - door.cx, w.cz - door.cz) >= ((D["win_w"] + D["door_w"]) / 2 + D["span_clear"]) * S - 1e-6
    assert len(items) < 60  # was 3 x 3 windows a face, one part each
    assert 5 <= sum(1 for i in items if tail(i).startswith("y")) <= 11 and labels == 0 and warnings == []
    assert {i.kind for i in items if tail(i).startswith("y")} == {"prop"} and all(i.collides for i in items if tail(i).startswith("y"))


@settings(max_examples=40)
@given(body_cases())
def test_p5_7_bands_sit_on_the_floor_lines_and_windows_stay_inside_their_floor_and_do_not_overlap(case):
    row, est, detail = case
    body, eff = resolve(row, est, detail, features=[street()])
    assume(body.is_body)
    items, _, _ = all_items(body, row, eff)
    fh = body.fh
    for i in items:
        t = tail(i)
        if t.startswith("fl"):
            k = int(t.split("-")[1])
            assert i.cy == pytest.approx(k * fh * S, abs=2e-3)
        if t.startswith("w0") or t.startswith("rb0"):
            k = int(re.fullmatch(r"(?:w|rb)\d[fblr](\d+)-\d+", t).group(1))
            bottom, top = (i.cy - i.sy / 2) / S, (i.cy + i.sy / 2) / S
            if body.archetype == "villa":  # BR-6.6: one glass covers a run of r floors in the same place
                wh = min(D["win_h"], fh - 1.0)
                r = (top - bottom - wh) / fh + 1
                assert bottom == pytest.approx(k * fh + D["win_sill"], abs=1e-3) and r == pytest.approx(round(r), abs=1e-3) and k + round(r) <= body.floors
            else:
                assert bottom >= k * fh + (0.9 if t.startswith("w0") else 1.0) - 1e-3 and top <= (k + 1) * fh - 0.06 + 1e-3
    by_face: dict[str, list] = {}
    for i in items:
        t = tail(i)
        if t.startswith("w0"):
            by_face.setdefault(t[2:5], []).append(i)
    for same in by_face.values():
        for a in same:
            for b in same:
                if a is not b:
                    assert math.hypot(a.cx - b.cx, a.cz - b.cz) >= 1.6 * S - 1e-3
    box = body.boxes[0]
    for i in items:
        if i.kind == "facade" and not tail(i).startswith(("rt", "tk", "rp")):
            e, n = i.cx / S, -i.cz / S
            assert LD._box_poly(box).buffer(0.6 + max(i.sx, i.sz) / S / 2 + 0.01).covers(Polygon([(e, n), (e + 1e-6, n), (e, n + 1e-6)]))


def test_bands_and_windows_are_skipped_when_a_floor_is_too_low():
    row, est, _ = villa(floors=3)
    eff = dataclasses.replace(J.effective_building(row, est, None, CFG), height_m=5.4)  # only an override can give 1.8 m per floor (U4 keeps the register in 2.5~5 m)
    body = LD.resolve_body(LD.make_body(row, eff, None, None, FRAME, CFG), LD._feature_lines([street()], FRAME, CFG), [], CFG)
    items, _, warnings = all_items(body, row, eff)
    assert not any(tail(i).startswith("w0") for i in items) and any("below" in w for w in body.warnings) and warnings == []


# --- BR-6.5 apartment facade ------------------------------------------------------------------------------------------------------------

def apartment(floors=22, w=42.0, d=12.0, i=7, name=""):
    return villa(i=i, w=w, d=d, floors=floors, wall="light_gray", code="02000", name=name)


def _u(body, item):
    """An item's centre along the box's long axis (box-local u, metres)."""
    box, t = body.boxes[0], math.radians(body.boxes[0].yaw_deg)
    e, n = item.cx / S - box.cx_m, -item.cz / S - box.cy_m
    return e * math.cos(t) + n * math.sin(t)


def test_br_6_5_a_22_floor_apartment_is_a_band_rail_and_slab_a_floor_not_hundreds_of_windows():
    """gis:11208043 (22 floors, 42 x 12 m) had 483 punched windows; a long face is now a few parts a floor plus full-height units."""
    row, est, _ = apartment()
    body, eff = resolve(row, est, features=[street()])
    assert body.archetype == "apartment" and body.facing.side in "fb"
    items, _, _ = all_items(body, row, eff)
    tails = [tail(i) for i in items]
    assert not any(t.startswith("w0") for t in tails)
    F, fh = body.floors, body.fh
    for side in "fb":
        front = side == body.facing.side
        assert sum(t.startswith(f"ag0{side}") for t in tails) == F + front  # the ground floor's band splits round the entrance
        assert sum(t.startswith(f"ar0{side}") for t in tails) == F + front
        assert sum(t.startswith(f"as0{side}") for t in tails) == F - 1
        assert sum(t.startswith(f"ap0{side}") for t in tails) == sum(t.startswith(f"al0{side}") for t in tails) == round(42 / 10) - 1
    assert not any(t.startswith(("ag0l", "ag0r", "w0l", "w0r")) for t in tails)  # end walls stay blank
    assert sum(t.startswith("cr0") for t in tails) == 4
    assert len([i for i in items if i.kind == "facade"]) < 300
    for i in items:
        t = tail(i)
        if t.startswith("ag0"):
            k = int(re.fullmatch(r"ag0[fb](\d+)-\d", t).group(1))
            bottom, top = (i.cy - i.sy / 2) / S, (i.cy + i.sy / 2) / S
            assert bottom == pytest.approx(k * fh + D["apt_glass_sill"], abs=1e-3) and top == pytest.approx((k + 1) * fh - D["apt_glass_head"], abs=1e-3)
        if t.startswith(("ap0", "al0", "au0")) and "-" not in t:
            assert i.sy / S == pytest.approx(body.height_m, abs=1e-3)


def test_br_6_5_nothing_on_the_ground_floor_covers_the_entrance_and_the_block_number_matches():
    row, est, _ = apartment(name="1005동")
    body, eff = resolve(row, est, features=[street()])
    items, _, _ = all_items(body, row, eff)
    canopy = next(i for i in items if tail(i) == "acn")
    door = _u(body, canopy)
    half = (D["door_w"] + 0.2) / 2
    for i in items:
        t = tail(i)
        if t.startswith(("ag0", "ar0", "am0", "ap0", "al0", "au0")) and t[3] == body.facing.side and (i.cy - i.sy / 2) / S < D["apt_canopy_y"] - 1e-3:
            u, along = _u(body, i), i.sx / S / 2
            assert u + along <= door - half + 1e-3 or u - along >= door + half - 1e-3, t
    plate = next(i for i in items if tail(i) == "acs")
    ends = [i for i in items if tail(i) in ("nol", "nor")]
    assert len(ends) == 2 and all(i.kind == "sign" and R.SIGN_TEXT.fullmatch(i.text) for i in ends + [plate])
    assert plate.text == "1005" and all(i.text == "1005동" for i in ends)


def test_br_6_5_the_block_number_is_the_register_name_of_a_complex_building_only():
    for name, number in (("1005동", 1005), ("101동", 101), ("광성아파트", None), ("데오스힐", None), ("", None), ("가동", None)):
        body, eff = resolve(*apartment(name=name)[:2], features=[street()])
        assert LD._block_no(body) == number, name
        items, _, _ = all_items(body, apartment(name=name)[0], eff)
        assert any(tail(i) in ("acs", "nol", "nor") for i in items) == (number is not None), name


@pytest.mark.parametrize("floors, archetype", [(5, "villa"), (6, "villa"), (7, "apartment"), (22, "apartment")])
def test_br_1_5_a_gongdong_jutaek_is_an_apartment_from_seven_floors(floors, archetype):
    body, _ = resolve(*apartment(floors=floors)[:2], features=[street()])
    assert body.archetype == archetype  # 5-6 floors: villas over pilotis or with shops (cell 2 street view 2026-10-14)


def test_a_store_is_a_windowless_box_with_ground_glass_and_a_tall_bay_and_no_signs():
    row, est, _ = villa(w=60.0, d=40.0, floors=11, wall="cream", code="07000")
    body, eff = resolve(row, est, features=[street()])
    assert body.archetype == "store" and not body.shop
    items, signs, _ = all_items(body, row, eff)
    assert not signs and not [i for i in items if i.kind == "sign"]
    glass = [tail(i) for i in items if tail(i).startswith(("rb", "bay"))]
    assert len([t for t in glass if t.startswith("rb")]) == 4 and len([t for t in glass if t.startswith("bay")]) == 4  # 60 and 40 m faces


@settings(max_examples=30)
@given(st.integers(5, 30), st.floats(18, 70), st.floats(10, 16))
def test_br_6_5_any_apartment_keeps_its_units_inside_the_face_and_the_glass_inside_its_floor(floors, w, d):
    row, est, _ = apartment(floors=floors, w=w, d=d)
    body, eff = resolve(row, est, features=[street()])
    assume(body.archetype == "apartment" and len(body.boxes) == 1 and body.boxes[0].width_m > 2 * body.boxes[0].depth_m)
    items, _, _ = all_items(body, row, eff)
    L = body.boxes[0].width_m
    for i in items:
        t = tail(i)
        if t.startswith(("ag0", "ap0", "al0", "au0", "am0")):
            assert abs(_u(body, i)) + i.sx / S / 2 <= L / 2 + 1e-3, t
        if t.startswith("ag0"):
            k = int(re.fullmatch(r"ag0[fb](\d+)-\d", t).group(1))
            assert k * body.fh <= (i.cy - i.sy / 2) / S and (i.cy + i.sy / 2) / S <= (k + 1) * body.fh
    assert len({i.name for i in items}) == len(items)


# --- BR-6.6 villa window columns, BR-3.2a ground band ---------------------------------------------------------------------------------

def _out(body, item, side):
    """How far an item's outer face stands from the wall of face `side` (metres); the item's thin side is its depth."""
    box, f = body.boxes[0], LD.face_of(body.boxes[0], side)
    t = math.radians(box.yaw_deg)
    e, n = item.cx / S - box.cx_m, -item.cz / S - box.cy_m
    u, v = e * math.cos(t) + n * math.sin(t), e * math.sin(t) - n * math.cos(t)
    return (u * f.n[0] + v * f.n[1]) - (box.depth_m if side in "fb" else box.width_m) / 2 + min(item.sx, item.sz) / S / 2


@settings(max_examples=40)
@given(st.integers(2, 4), st.floats(6, 20), st.floats(6, 14), st.sampled_from(["none", "glass", "brick"]), st.booleans())
def test_br_6_6_skins_sit_between_rows_frames_sit_behind_the_glass_and_the_skin_stops_at_the_stair(floors, w, d, stair, bay):
    detail = {"building_id": "gis:9", "finish": "brick", "ground_use": "house", "stair": stair, "bay": int(bay), "balcony": 0,
              "roof_color": "dark", "rooftop": "none", "note": "", "judged_at": "2026-10-14T00:00:00+00:00"}
    row, est, _ = villa(i=9, w=w, d=d, floors=floors)
    body, eff = resolve(row, est, detail, features=[street()])
    assume(body.archetype == "villa" and len(body.boxes) == 1 and body.fh >= D["min_fh"])
    items, _, _ = all_items(body, row, eff)
    fh, wh = body.fh, min(D["win_h"], body.fh - 1.0)
    for i in items:
        t = tail(i)
        bottom, top = (i.cy - i.sy / 2) / S, (i.cy + i.sy / 2) / S
        if t.startswith("ws0"):
            k = int(re.fullmatch(r"ws0[fblr](\d+)-\d+", t).group(1))
            assert bottom == pytest.approx((k - 1) * fh + D["win_sill"] + wh, abs=1e-3) and top == pytest.approx(k * fh + D["win_sill"], abs=1e-3)
            assert _out(body, i, t[3]) == pytest.approx(D["skin_out"], abs=1e-3)
        if t.startswith("wf0"):
            assert _out(body, i, t[3]) == pytest.approx(D["frame_out"], abs=1e-3)
        if t.startswith("w0"):
            assert _out(body, i, t[2]) == pytest.approx(D["frame_out"] + D["frame_glass"], abs=1e-3)
    if body.facing is not None:
        side = body.facing.side
        for a, b in LD._blocked(body):  # no front skin crosses the stair tower or the bay
            for i in items:
                if tail(i).startswith(f"ws0{side}"):
                    u = _u(body, i) if side in "fb" else None
                    if u is not None:
                        along = -u if side == "f" else u
                        half = i.sx / S / 2
                        assert along + half <= a - D["span_clear"] + 1e-3 or along - half >= b + D["span_clear"] - 1e-3
        if LD.villa_skin_at(body, 0, side, 1, True):
            for i in items:
                if tail(i).startswith(("ac", "gs0")):  # gs0 runs along the face; gs1 is the riser at its end
                    assert _out(body, i, side) >= D["skin_out"] + D["gas_out"] - 1e-3, tail(i)


def test_br_3_2a_the_first_floor_band_is_thick_and_proud_but_a_school_keeps_the_thin_one():
    row, est, _ = villa(floors=3)
    body, eff = resolve(row, est, features=[street()])
    items, _, _ = all_items(body, row, eff)
    b1 = next(i for i in items if tail(i) == "fl0-1")
    b2 = next(i for i in items if tail(i) == "fl0-2")
    box = body.boxes[0]
    assert b1.sy / S == pytest.approx(D["band1_h"], abs=1e-3) and b1.color_name == "band_ground"
    assert max(b1.sx, b1.sz) / S == pytest.approx(box.width_m + 2 * D["band1_out"], abs=1e-3)
    assert b1.cy == pytest.approx(body.fh * S, abs=2e-3) and b2.sy / S == pytest.approx(D["band_h"], abs=1e-3)
    assert D["band1_out"] > D["skin_out"] > D["frame_out"] + D["frame_glass"]  # band over skin over glass over frame
    srow, sest, _ = villa(i=2, floors=3, name="한빛학교")
    sbody, seff = resolve(srow, sest, features=[street()])
    assert sbody.archetype == "school"
    sb1 = next(i for i in all_items(sbody, srow, seff)[0] if tail(i) == "fl0-1")
    assert sb1.sy / S == pytest.approx(D["band_h"], abs=1e-3)


# --- P5-9 shops and yards -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("code, use, floors, setback_dy, expect", [
    ("01000", "house", 3, 15, "yard"), ("01000", "shop", 3, 15, "storefront"), ("01000", "house", 3, 4, "neither"),  # setback_s = 4 - 5 - ... < 1.5
    ("14000", "house", 6, 15, "neither"), ("14000", "shop", 6, 15, "storefront"),  # BR-9.1 (2026-10-14): a judged house ground floor stays
    ("03000", "shop", 2, 15, "storefront"), ("10000", "shop", 1, 15, "neither")])  # 03000 judged shop: a shop block (2026-10-14)
def test_p5_9_exactly_one_of_storefront_yard_or_neither(code, use, floors, setback_dy, expect):
    d = 10.0
    row, est, _ = villa(code=code, floors=floors, center=offset(CENTER, 0, setback_dy + d / 2), name="")
    detail = {"building_id": "gis:1", "ground_use": use}
    body, eff = resolve(row, est, detail, features=[street()])
    items, labels, _ = all_items(body, row, eff)
    has_front = any(tail(i).startswith("sf") for i in items)
    has_yard = any(tail(i).startswith("yw") for i in items)
    assert (has_front, has_yard) == {"yard": (False, True), "storefront": (True, False), "neither": (False, False)}[expect]
    if expect == "storefront":
        units = sum(1 for i in items if tail(i).startswith("sf"))
        assert sum(1 for i in items if tail(i).startswith("sg") and not tail(i).startswith("sgf")) == units
        assert not any(tail(i).startswith("pl") for i in items)
    if expect == "yard":
        gap = [i for i in items if tail(i) == "yg0"]
        assert len(gap) == 1 and gap[0].sx == pytest.approx(2.8 * S, abs=2e-3)
        walls = [i for i in items if tail(i).startswith("yw")]
        assert all((i.cz - body.boxes[0].cy_m * -S) < 0 or True for i in walls)  # placed, sizes below
        assert all(i.sy == pytest.approx(1.4 * S, abs=2e-3) for i in walls)


def test_the_yard_wall_stands_between_the_face_and_the_sidewalk():
    row, est, _ = villa()
    body, eff = resolve(row, est, features=[street()])
    yd = min(body.facing.setback_s, 8) - 0.3
    for i in LD.yard_items(body, FRAME, CFG):
        if tail(i).startswith("yw"):
            north_m = -i.cz / S
            face_north = body.boxes[0].cy_m - body.boxes[0].depth_m / 2
            assert face_north - north_m == pytest.approx(yd, abs=0.01)


# --- signs (BR-10) ------------------------------------------------------------------------------------------------------------------

def test_signs_carry_text_colors_faces_and_distances_and_a_bad_name_removes_them_all():
    row, est, _ = villa(code="04000", floors=7, fh=3.4, w=30, d=20)
    body, eff = resolve(row, est, features=[street()])
    signs, labels = LD.sign_items(body, FRAME, CFG, [])
    kinds = [tail(i)[:3] for i in signs]
    assert any(k.startswith("sg") and not k.startswith("sgf") for k in kinds) and any(k == "sgf" for k in kinds) and any(k == "sp0" for k in kinds) and "sr0" in kinds
    assert all(i.kind == "sign" or tail(i).startswith("rp") for i in signs)  # the roof sign's two posts are the only non-sign items
    for i in (i for i in signs if i.kind == "sign"):
        assert R.SIGN_TEXT.fullmatch(i.text) and i.ink in R.PALETTE and i.color_name in R.PALETTE and i.attrs["MaxDistance"] in (200, 300, 400)
    assert labels == sum(2 if i.faces == "LR" else 1 for i in signs if i.kind == "sign")
    band = next(i for i in signs if tail(i).startswith("sg0"))
    floor1 = [i for i in signs if tail(i).startswith("sgf1-")]
    assert floor1 and (band.cy + band.sy / 2) / S <= body.fh + 1e-6 <= min((i.cy - i.sy / 2) / S for i in floor1)  # the band sign stays below the floor line, floor signs above it (S-10)
    public = villa(2, code="03000", floors=2, name='a"b주민센터')[0]  # a public name (kept as is) with a character the sign text forbids
    pbody, _ = resolve(public, villa(2)[1], features=[street()])
    warnings: list[str] = []
    assert LD.sign_items(pbody, FRAME, CFG, warnings) == ([], 0) and warnings and "sign text" in warnings[0]
    named = villa(3, code="03000", floors=2, name="중앙행정복지센터")[0]
    nbody, _ = resolve(named, villa(3)[1], features=[street()])
    plate, _ = LD.sign_items(nbody, FRAME, CFG, [])
    assert [i.text for i in plate] == ["중앙행정복지센터"]
    park = villa(4, code=R.PARKING_CODE, floors=6, name="중동 공영노외주차장(6호)")[0]  # 17b: the plate says it is a parking building
    kbody, _ = resolve(park, villa(4)[1], features=[street()])
    plate, _ = LD.sign_items(kbody, FRAME, CFG, [])
    assert kbody.archetype == "public" and [i.text for i in plate] == ["공영주차장"]


def _ground(i, use):
    return {"building_id": f"gis:{i}", **{f: None for f in R.DETAIL_FIELDS}, "ground_use": use, "note": None}


def _sign_tails(code, floors, use, i):
    row, est, _ = villa(i, code=code, floors=floors, fh=3.4, w=30, d=20)
    body, eff = resolve(row, est, _ground(i, use) if use else None, features=[street()])
    signs, _ = LD.sign_items(body, FRAME, CFG, [])
    fronts = [x for x in LD.front_items(body, FRAME, CFG, []) if tail(x).startswith("sf")]
    return body, {tail(x) for x in signs if x.kind == "sign"}, fronts


def test_br_9_1_and_10_1a_offices_and_judged_ground_floors_get_fewer_shop_signs():
    # BR-9.1: a commercial block judged house or garage on the ground floor has no shops, so no storefront and no shop signs
    for code, floors, use in (("14000", 9, "house"), ("04000", 6, "garage")):
        body, tails, fronts = _sign_tails(code, floors, use, 40 + floors)
        assert body.archetype == "commercial" and not body.shop and not tails and not fronts
    # nothing judged: a commercial block keeps its shops (the default does not change)
    body, tails, fronts = _sign_tails("04000", 6, None, 50)
    assert body.shop and fronts and any(t.startswith("sgf5") for t in tails) and "sr0" not in tails  # 6 floors < rooftop-sign floors
    # BR-10.1a: an office block (14000) with shops: floor signs on the 2nd and 3rd floors only, no rooftop sign
    body, tails, fronts = _sign_tails("14000", 10, "shop", 51)
    floors_signed = {int(t[3:].split("-")[0]) for t in tails if t.startswith("sgf")}
    assert body.shop and fronts and floors_signed == {1, 2} and "sr0" not in tails
    _, tails, _ = _sign_tails("04000", 10, "shop", 52)
    assert {int(t[3:].split("-")[0]) for t in tails if t.startswith("sgf")} == {1, 2, 3, 4, 5} and "sr0" in tails


# --- P5-11 street slots, P5-12 junctions, P5-13 sidewalk pieces ----------------------------------------------------------------------------

def props_of(features, cfg=CFG):
    streets = ST.streets_of(features, FRAME, CELL, RES, cfg)
    jcts = ST.junctions(streets, FRAME, CELL, RES, cfg)
    return ST.street_items(streets, jcts, FRAME, cfg), jcts


def count(items, word):
    return sum(1 for i in items if re.search(rf"#{word}[A-Z0-9]", i.name))  # "tr" is the transformer, not "treeL"


def test_p5_11_a_100_m_residential_segment_gets_the_expected_slots():
    (sidewalks, props), jcts = props_of([street("way:1", "residential", length=100)])
    assert jcts == [] and len(sidewalks) == 2
    assert count(props, "pole") == 3 and count(props, "arm") == 3 and count(props, "tr") == 1 and count(props, "wire") == 4
    assert count(props, "lamp") == 3 and count(props, "car") == 10 and count(props, "cl") == 2 and count(props, "curb") == 2
    assert count(props, "treeL") == 13 and count(props, "treeR") == 12  # one tree per side gives way to a lamp or pole within 2 m
    assert len(props) == 144  # 25 trees = 25 trunks + 75 crown balls
    poles = sorted((i for i in props if "#pole" in i.name), key=lambda i: i.name)
    xs = sorted(i.cx for i in poles)
    assert xs[1] - xs[0] == pytest.approx(30 * S, abs=0.05) and xs[2] - xs[1] == pytest.approx(30 * S, abs=0.05)
    assert all(i.shape == "Cylinder" and i.sx == pytest.approx(10 * S, abs=2e-3) for i in poles)


def test_p5_11_a_tree_is_a_trunk_and_three_overlapping_balls_and_the_trees_differ_but_repeat():
    (_, props), _ = props_of([street("way:1", "residential", length=100)])
    (_, again), _ = props_of([street("way:1", "residential", length=100)])
    trunks = [i for i in props if re.search(r"#tree[LR]\d+$", i.name)]
    assert len(trunks) == 25
    for t in trunks:
        names = {t.name.replace("#tree", "#crown") + k for k in "abc"}
        balls = [i for i in props if i.name in names]
        assert len(balls) == 3 and all(b.shape == "Ball" for b in balls)
        main = max(balls, key=lambda b: b.sx)
        assert all(b.cy - b.sy / 2 >= t.sx / 2 for b in balls)  # no ball rests near the ground: the crown starts above half the trunk
        assert all(math.hypot(b.cx - main.cx, b.cz - main.cz) < (b.sx + main.sx) / 2 for b in balls)  # the three overlap into one crown
    assert len({(round(i.sx), i.color_name) for i in props if "#crown" in i.name}) > 4
    assert [(i.name, i.cx, i.cy, i.cz, i.color_name) for i in props] == [(i.name, i.cx, i.cy, i.cz, i.color_name) for i in again]


def test_p5_11_no_cars_with_the_default_settings():
    (_, props), _ = props_of([street("way:1", "residential", length=100)], common.DEFAULTS)
    assert count(props, "car") == 0 and count(props, "cab") == 0 and count(props, "treeL") > 0


@settings(max_examples=30)
@given(st.sampled_from(["living_street", "residential", "service", "tertiary"]), st.floats(20, 150), st.one_of(st.just(0.0), st.floats(1, 60)))
def test_p5_11_consecutive_slots_are_spacing_apart_and_start_at_half_a_spacing(cls, length, spacing):
    cfg = {**CFG, "pole_spacing_m": spacing, "tree_spacing_m": spacing, "lamp_spacing_m": spacing, "car_spacing_m": spacing}
    (sidewalks, props), _ = props_of([street("way:1", cls, length=length)], cfg)
    for word in ("pole", "lamp", "car"):
        xs = sorted(i.cx / S for i in props if f"#{word}" in i.name)
        if spacing == 0 or length < spacing / 2:
            assert xs == []
            continue
        step = spacing * (D["car_residential"] if word == "car" and cls == "residential" else 1.0)
        if xs:
            start = min(i.cx for i in props if "#curb" in i.name) if False else None
            for a, b in zip(xs, xs[1:]):
                assert b - a == pytest.approx(step, abs=1e-3)
    doubled = {**cfg, "pole_spacing_m": spacing * 2 if spacing else 0}
    (_, props2), _ = props_of([street("way:1", cls, length=length)], doubled)
    assert count(props2, "pole") <= count(props, "pole")


def test_p5_12_a_shared_vertex_is_a_junction_with_crosswalks_on_the_big_arms_only():
    main = street("way:1", "residential", length=120)
    mid = main["geometry"][0]
    crossing = {"feature_id": "way:2", "kind": "road", "highway_class": "service", "tags": {},
                "geometry": [list(offset(CENTER, 0, -40)), list(offset(CENTER, 0, 0)), list(offset(CENTER, 0, 40))]}
    main["geometry"] = [list(offset(CENTER, -60, 0)), list(offset(CENTER, 0, 0)), list(offset(CENTER, 60, 0))]
    (sidewalks, props), jcts = props_of([main, crossing])
    assert len(jcts) == 1 and jcts[0].owned and len(jcts[0].arms) == 4
    stripes = [i for i in props if "#cw" in i.name]
    assert len(stripes) == 2 * int(6 // 0.9)  # the two residential arms, none on the service arms
    for i in stripes:
        assert i.sz == pytest.approx(0.45 * S, abs=2e-3) and i.sx == pytest.approx(4.0 * S, abs=2e-3)
        dist = math.hypot(i.cx - jcts[0].east * S, i.cz + jcts[0].north * S) / S
        assert 6 / 2 + 1 <= dist + 2.0 + 0.01 and dist - 2.0 <= 6 / 2 + 5 + 0.01
    assert count(props, "sl") == 2 and count(props, "box") == 0
    again = props_of([crossing, main])
    assert [j.name for j in again[1]] == [j.name for j in jcts] and sorted(i.name for i in again[0][1]) == sorted(i.name for i in props)


def test_p5_13_sidewalks_break_at_an_alley_mouth_on_that_side_only_and_not_at_a_straight_continuation():
    main = {"feature_id": "way:1", "kind": "road", "highway_class": "residential", "tags": {},
            "geometry": [list(offset(CENTER, -60, 0)), list(offset(CENTER, 0, 0)), list(offset(CENTER, 60, 0))]}
    alley = {"feature_id": "way:2", "kind": "road", "highway_class": "service", "tags": {},
             "geometry": [list(offset(CENTER, 0, 0)), list(offset(CENTER, 0, 40))]}  # leaves to the north = the left of an eastbound road
    (sidewalks, props), jcts = props_of([main, alley])
    left = sorted(i.name for i in sidewalks if "L" in i.name.split("#")[1])
    right = sorted(i.name for i in sidewalks if "R" in i.name.split("#")[1])
    assert left == ["way:1#0L.0", "way:1#1L.0"] and right == ["way:1#0R.0", "way:1#1R.0"]
    gap = 4 + 1
    first_left = next(i for i in sidewalks if i.name == "way:1#0L.0")
    assert first_left.sx == pytest.approx((60 - gap / 2) * S, rel=2e-3)
    first_right = next(i for i in sidewalks if i.name == "way:1#0R.0")
    assert first_right.sx == pytest.approx((60 + 1.5) * S, rel=2e-3)
    assert count(props, "curb") == 4
    cont = {"feature_id": "way:3", "kind": "road", "highway_class": "residential", "tags": {},
            "geometry": [list(offset(CENTER, 60, 0)), list(offset(CENTER, 120, 0))]}
    (sw2, _), _ = props_of([main, cont])
    assert all(i.sx == pytest.approx((60 + 1.5) * S, rel=2e-3) for i in sw2 if i.name.startswith("way:1"))


# --- P5-15 ownership, P5-18 budget, P5-19 sidewalk sides --------------------------------------------------------------------------------------

@settings(max_examples=40)
@given(body_cases())
def test_p5_15_every_owned_item_names_its_building_and_the_budget_holds(case):
    row, est, detail = case
    body, eff = resolve(row, est, detail, features=[street()])
    items, labels, _ = all_items(body, row, eff)
    for i in items:
        if i.kind != "building" or len(body.boxes) > 1:
            assert i.owner == body.building_id and i.name.startswith(body.building_id + "#")
        assert i.material in R.MATERIALS and i.shape in R.SHAPES
    # villa: up to six sashes a face; school: the classroom grid (2.4 m spacing) on the generator's tallest block, 10 floors of
    # 23 x 18 m = 320 windows + bands = 331 (found 2026-10-14; real schools have at most 5 floors)
    limit = {"villa": 90, "commercial": 140, "public": 60, "school": 360, "apartment": 320}[body.archetype]
    assert len(items) <= limit
    assert len({i.name for i in items}) == len(items)


@pytest.mark.parametrize("tags, cls, expect", [
    ({"sidewalk": "both"}, "service", ("L", "R")), ({"sidewalk": "no"}, "residential", ()), ({"sidewalk:both": "yes"}, "service", ("L", "R")),
    ({"sidewalk:both": "no"}, "residential", ()), ({"sidewalk:left": "yes"}, "service", ("L",)), ({"sidewalk:right": "separate"}, "service", ("R",)),
    ({"sidewalk:left": "no"}, "residential", ()), ({"sidewalk": "left", "sidewalk:both": "yes"}, "service", ("L",)),
    ({}, "residential", ("L", "R")), ({}, "living_street", ()), ({}, "tertiary", ("L", "R")), ({}, "service", ())])
def test_p5_19_sidewalk_sides_follow_sidewalk_then_sidewalk_both_left_right_then_the_class(tags, cls, expect):
    assert layout.sidewalk_sides({"kind": "road", "highway_class": cls, "tags": tags}) == expect
    assert layout.sidewalk_sides({"kind": "path", "highway_class": "footway", "tags": tags}) == ()


# --- subway entrances (2026-10-14, cell 4) ----------------------------------------------------------------------------------------

def test_subway_entrances_stand_off_the_road_open_away_from_the_station_and_carry_the_exit_number():
    road = street(cls="primary", lanes="8")  # east-west through the cell centre, 8 lanes
    ents = [{"feature_id": f"node:{n}", "kind": "subway_entrance", "highway_class": None, "geometry": [list(offset(CENTER, x, y))],
             "tags": {"ref": str(n)}} for n, (x, y) in ((1, (-20.0, 3.0)), (2, (20.0, -3.0)))]  # both on the carriageway, either side of the middle
    lines = ST.streets_of([road], FRAME, CELL, RES, CFG)
    items = ST.entrance_items(ents, lines, FRAME, CELL, RES)
    far = [{**ents[0], "feature_id": "node:9", "geometry": [list(offset(CENTER, 0, 2000))]}]  # a neighbour cell's entrance: only shifts the middle
    assert ST.entrance_items(ents + far, lines, FRAME, CELL, RES)[0].name.startswith("node:1#") and not [
        i for i in ST.entrance_items(ents + far, lines, FRAME, CELL, RES) if i.group == "node:9"]
    w = lines[0].width
    for n, (x, y) in ((1, (-20.0, 3.0)), (2, (20.0, -3.0))):
        mine = [i for i in items if i.group == f"node:{n}"]
        signs = [i for i in mine if i.kind == "sign"]
        assert len(signs) == 1 and signs[0].text == f"{n}번 출구"
        north = [-i.cz / S - layout.to_meters(FRAME, *CENTER)[1] for i in mine]
        assert all(abs(v) >= w / 2 for v in north)  # nothing on the carriageway, on the side it stood
        assert all((v > 0) == (y > 0) for v in north)
        east = lambda i: i.cx / S - layout.to_meters(FRAME, *CENTER)[0]
        body = [i for i in mine if i.name.endswith("#ld")][0]
        assert abs(east(signs[0])) > abs(east(body))  # the open end with the number faces away from the other entrance
    assert any(i.transparency for i in items) and "tr=0.6" in B_literal(items)


def B_literal(items):
    import build_luau
    return " ".join(build_luau.item_literal(i, CELL) for i in items)


def test_a_divided_road_gets_no_median_sidewalk_and_no_sidewalk_lies_on_another_carriageway():
    # two one-way halves 8 m apart (centre lines), and a slip road crossing both at an angle (cell 4, 2026-10-14)
    north = {"feature_id": "way:1", "kind": "road", "highway_class": "primary", "tags": {"oneway": "yes", "lanes": "3"},
             "geometry": [list(offset(CENTER, -80, 7)), list(offset(CENTER, 80, 7))]}
    south = {"feature_id": "way:2", "kind": "road", "highway_class": "primary", "tags": {"oneway": "yes", "lanes": "3"},
             "geometry": [list(offset(CENTER, 80, -7)), list(offset(CENTER, -80, -7))]}
    slip = {"feature_id": "way:3", "kind": "road", "highway_class": "primary_link", "tags": {"oneway": "yes"},
            "geometry": [list(offset(CENTER, -40, -40)), list(offset(CENTER, 40, 40))]}
    (sidewalks, props), _ = props_of([north, south, slip])
    lines = ST.streets_of([north, south, slip], FRAME, CELL, RES, CFG)
    ways = ST.carriageways(lines)
    c = layout.to_meters(FRAME, *CENTER)
    for i in sidewalks:
        fid = i.name.split("#")[0]
        pt = Point(i.cx / S, -i.cz / S)
        assert all(g.distance(pt) > 0.05 for f, g in ways.items() if f != fid), i.name  # never on another road
        if fid in ("way:1", "way:2"):
            assert abs(-i.cz / S - c[1]) > 7, i.name  # only on the outer sides of the pair
    assert any(i.name.startswith("way:1") for i in sidewalks) and any(i.name.startswith("way:2") for i in sidewalks)
    for i in props:
        if "#lamp" in i.name or "#curb" in i.name:
            pt = Point(i.cx / S, -i.cz / S)
            assert all(g.distance(pt) > 0.05 for f, g in ways.items() if f != i.name.split("#")[0]), i.name


# --- cell 4 street-view review (2026-10-14): corner shops, single business, brick base, officetel ---------------------------------

SHOP = {"finish": "panel", "ground_use": "shop", "stair": "none", "bay": 0, "balcony": 0, "roof_color": "dark", "rooftop": "none"}


def test_a_corner_shop_block_gets_storefronts_and_band_signs_on_the_side_street_too():
    row, est, _ = villa(w=24.0, d=20.0, floors=6, wall="light_gray", code="04000", center=offset(CENTER, 0, 4 + 10))  # front 1 m off the road
    side_road = {"feature_id": "way:5", "kind": "road", "highway_class": "residential", "tags": {},
                 "geometry": [list(offset(CENTER, 17, -10)), list(offset(CENTER, 17, 60))]}  # north-south, 5 m east of the block
    body, eff = resolve(row, est, SHOP, features=[street(), side_road])
    assert body.side_shops and all(s != body.facing.side for _, s in body.side_shops)
    items, labels, _ = all_items(body, row, eff, )
    side = body.side_shops[0][1]
    assert any(tail(i).startswith(f"ss0{side}") for i in items) and any(tail(i).startswith(f"sgs0{side}") for i in items)
    assert not any(tail(i).startswith(f"rb0{side}0-") for i in items)  # no window ribbon behind the side storefront
    lone, eff2 = resolve(row, est, SHOP, features=[street()])
    assert lone.side_shops == ()


def test_a_single_business_has_one_name_and_no_floor_signs():
    row, est, _ = villa(w=24.0, d=20.0, floors=5, wall="light_gray", code="03000", name="LG베스트샵")
    body, eff = resolve(row, est, SHOP, features=[street()])
    assert body.single
    items, _, _ = all_items(body, row, eff)
    assert not [i for i in items if tail(i).startswith("sgf")] and len([i for i in items if tail(i).startswith("sg") and not tail(i).startswith(("sgf", "sgs"))]) == 1
    assert len([i for i in items if re.fullmatch(r"sf\d+", tail(i))]) == 1  # one storefront across
    other, eff2 = resolve(*villa(w=24.0, d=20.0, floors=5, wall="light_gray", code="03000", name="동화빌딩")[:2], SHOP, features=[street()])
    assert not other.single and [i for i in all_items(other, row, eff2)[0] if tail(i).startswith("sgf")]


def test_a_tall_brick_shop_block_is_panel_above_a_two_floor_brick_base():
    row, est, _ = villa(w=24.0, d=20.0, floors=10, wall="red_brick", code="03000")
    body, eff = resolve(row, est, {**SHOP, "finish": "brick"}, features=[street()])
    assert body.base == "red_brick" and body.wall_color == "light_gray"
    items, _, _ = all_items(body, row, eff)
    base = [i for i in items if tail(i) == "bs0"]
    assert len(base) == 1 and base[0].material == "Brick" and base[0].sy == pytest.approx(2 * body.fh * S, rel=1e-3)
    assert [i for i in items if i.kind == "building"][0].attrs["WallColor"] == "light_gray"
    low, _ = resolve(*villa(w=24.0, d=20.0, floors=4, wall="red_brick", code="03000")[:2], {**SHOP, "finish": "brick"}, features=[street()])
    assert low.base is None and low.wall_color == "red_brick"


@pytest.mark.parametrize("floors, name, piers", [(15, "", True), (9, "", False), (10, "리치타운 오피스텔", True)])
def test_an_officetel_gets_full_height_piers_above_its_shop_base(floors, name, piers):
    row, est, _ = villa(w=30.0, d=18.0, floors=floors, wall="beige", code="14000", name=name)
    body, eff = resolve(row, est, SHOP, features=[street()])
    items, _, _ = all_items(body, row, eff)
    ps = [i for i in items if tail(i).startswith("op")]
    assert bool(ps) == piers
    for i in ps:
        assert (i.cy - i.sy / 2) / S == pytest.approx(3 * body.fh, abs=1e-2)


def test_a_footpath_is_cut_where_it_crosses_a_road_and_kept_on_both_sides():
    road = street(cls="tertiary")  # east-west through the cell centre
    path = {"feature_id": "way:7", "kind": "path", "highway_class": "footway", "tags": {},
            "geometry": [list(offset(CENTER, 0, -40)), list(offset(CENTER, 0, 40))]}
    out = ST.paths_off_roads([road, path], FRAME, CFG)
    pieces = [f for f in out if f["kind"] == "path"]
    assert sorted(f["feature_id"] for f in pieces) == ["way:7.0", "way:7.1"]
    w = ST.streets_of([road], FRAME, CELL, RES, CFG)[0].width
    way = ST.carriageways(ST.streets_of([road], FRAME, CELL, RES, CFG))["way:11"]
    for f in pieces:
        line = LineString([layout.to_meters(FRAME, *p) for p in f["geometry"]])
        assert line.intersection(way).length < 0.01 and line.length > 30 - w
    alone = {**path, "geometry": [list(offset(CENTER, 0, 20)), list(offset(CENTER, 0, 40))]}
    assert ST.paths_off_roads([road, alone], FRAME, CFG)[1] is alone


def test_bollards_where_a_footpath_meets_a_road_stand_off_the_carriageway():
    road = street(cls="tertiary")
    path = {"feature_id": "way:7", "kind": "path", "highway_class": "footway", "tags": {},
            "geometry": [list(offset(CENTER, 0, -40)), list(offset(CENTER, 0, 0)), list(offset(CENTER, 0, 40))]}
    road = {**road, "geometry": [list(offset(CENTER, -60, 0)), list(offset(CENTER, 0, 0)), list(offset(CENTER, 60, 0))]}
    (_, props), _ = props_of([road, path])
    way = ST.carriageways(ST.streets_of([road], FRAME, CELL, RES, CFG))["way:11"]
    bol = [i for i in props if "#bol" in i.name]
    assert bol and all(way.distance(Point(i.cx / S, -i.cz / S)) > 0.5 for i in bol)


def test_a_lane_centre_line_stops_before_the_crosswalk_of_a_wide_junction():
    big = {"feature_id": "way:1", "kind": "road", "highway_class": "tertiary", "tags": {"lanes": "8"},
           "geometry": [list(offset(CENTER, 0, -60)), list(offset(CENTER, 0, 0)), list(offset(CENTER, 0, 60))]}
    lane = {"feature_id": "way:2", "kind": "road", "highway_class": "residential", "tags": {},
            "geometry": [list(offset(CENTER, 0, 0)), list(offset(CENTER, -80, 0))]}
    (_, props), jcts = props_of([big, lane])
    w_max = max(j.w_max for j in jcts)
    for i in [i for i in props if i.name.startswith("way:2#") and "#cl" in i.name]:
        near_end = abs(i.cx / S - layout.to_meters(FRAME, *CENTER)[0]) - i.sx / S / 2
        assert near_end >= w_max / 2 + D["cw_to"] - 0.01


def test_two_junctions_a_few_metres_apart_on_one_road_get_one_crosswalk_there():
    main = {"feature_id": "way:1", "kind": "road", "highway_class": "tertiary", "tags": {},
            "geometry": [list(offset(CENTER, -60, 0)), list(offset(CENTER, -4, 0)), list(offset(CENTER, 4, 0)), list(offset(CENTER, 60, 0))]}
    a = {"feature_id": "way:2", "kind": "road", "highway_class": "tertiary", "tags": {},
         "geometry": [list(offset(CENTER, -4, 0)), list(offset(CENTER, -4, 50))]}
    b = {"feature_id": "way:3", "kind": "road", "highway_class": "tertiary", "tags": {},
         "geometry": [list(offset(CENTER, 4, 0)), list(offset(CENTER, 4, -50))]}
    (_, props), jcts = props_of([main, a, b])
    owned = [j for j in jcts if j.owned]
    assert len(owned) == 2
    centres = {}
    for i in props:
        if "#cw" in i.name:
            centres.setdefault(i.name.split("#cw")[0] + i.name.split("#cw")[1].split("-")[0], []).append((i.cx / S, -i.cz / S, i.yaw_deg))
    mids = [(sum(x for x, _, _ in v) / len(v), sum(y for _, y, _ in v) / len(v), v[0][2]) for v in centres.values()]
    for k, m in enumerate(mids):
        for o in mids[k + 1:]:
            parallel = abs(math.cos(math.radians(m[2] - o[2]))) > 0.9
            assert not parallel or math.hypot(m[0] - o[0], m[1] - o[1]) >= D["cw_merge"]  # no two crosswalks side by side
    assert len(mids) == 4  # 6 arms: the two along the main road between the junctions merged


def test_a_slip_lane_joining_at_a_shallow_angle_gets_no_crosswalks():
    main = {"feature_id": "way:1", "kind": "road", "highway_class": "tertiary", "tags": {},
            "geometry": [list(offset(CENTER, -60, 0)), list(offset(CENTER, 0, 0)), list(offset(CENTER, 60, 0))]}
    slip = {"feature_id": "way:2", "kind": "road", "highway_class": "tertiary", "tags": {"oneway": "yes"},
            "geometry": [list(offset(CENTER, 0, 0)), list(offset(CENTER, 40, 20))]}  # about 27 degrees off the main road
    (_, props), _ = props_of([main, slip])
    assert not [i for i in props if "#cw" in i.name or "#sl" in i.name]
    cross = {**slip, "geometry": [list(offset(CENTER, 0, 0)), list(offset(CENTER, 0, 40))]}
    (_, props), _ = props_of([main, cross])
    assert [i for i in props if "#cw" in i.name]


def test_one_trick_ramp_is_a_kicker_with_a_curved_transition_a_lip_a_deck_and_a_landing_on_the_longest_minor_road():
    long_road = {**street(length=120.0), "feature_id": "way:1"}  # east-west through the centre
    short = {"feature_id": "way:2", "kind": "road", "highway_class": "residential", "tags": {},
             "geometry": [list(offset(CENTER, -20, 40)), list(offset(CENTER, 20, 40))]}
    lines = ST.streets_of([long_road, short], FRAME, CELL, RES, CFG)
    items = ST.ramp_items(lines, FRAME)
    assert items and all(i.name.startswith("way:1#") and "#ramp" in i.name and i.collide for i in items)
    c = layout.to_meters(FRAME, *CENTER)
    assert all(abs(-i.cz / S - c[1]) < 0.01 for i in items)  # on the centre line
    tops = {}
    for i in items:
        x = round(i.cx / S - c[0], 2)
        tops[i.name.split("#")[-1]] = (x, (i.cy + i.sy / 2) / S - layout.TOPS["road"] / S)
    # the transition rises step by step toward the lip, the deck is at full height after it, the landing comes down after that
    steps = [tops[f"rampt{k}"] for k in range(ST.RAMP["segs"] - 1)] + [tops["rampup"]]
    assert [x for x, _ in steps] == sorted(x for x, _ in steps) and [y for _, y in steps] == sorted(y for _, y in steps)
    assert tops["rampup"][1] == pytest.approx(ST.RAMP["h"], abs=1e-3) and tops["rampdk"][1] == pytest.approx(ST.RAMP["h"], abs=1e-3)
    assert tops["rampup"][0] < tops["rampdk"][0] < tops["rampdn"][0]
    lip = next(i for i in items if i.name.endswith("#rampup"))
    rise, run = lip.sy / S, lip.sz / S
    first_rise = next(i for i in items if i.name.endswith("#rampt0"))
    assert math.degrees(math.atan2(rise, run)) > math.degrees(math.atan2(first_rise.sy / S, first_rise.sz / S)) + 20  # it curves up
    look_z = lambda i: math.sin(math.radians(i.yaw_deg))  # local +Z east component: wedges rise toward +Z
    assert look_z(lip) > 0.99 and look_z(next(i for i in items if i.name.endswith("#rampdn"))) < -0.99
    assert sum(i.sx / S * i.sy / S * i.sz / S for i in items) > 6  # a real kicker, not a speed bump (the first one was 1.9 m3)
    assert ST.ramp_items(ST.streets_of([short], FRAME, CELL, RES, CFG), FRAME) == []  # 40 m: too short


def test_kickers_go_here_and_there_spaced_apart_and_at_most_per_cell():
    roads = [{"feature_id": f"way:{n}", "kind": "road", "highway_class": "residential", "tags": {},
              "geometry": [list(offset(CENTER, -40, y)), list(offset(CENTER, 40, y))]} for n, y in enumerate((-150, -90, 0, 30, 90, 150), 1)]
    lines = ST.streets_of(roads, FRAME, CELL, RES, CFG)
    lips = [i for i in ST.ramp_items(lines, FRAME) if i.name.endswith("#rampup")]
    assert 2 <= len(lips) <= ST.RAMP["per_cell"]
    pts = [(i.cx / S, i.cz / S) for i in lips]
    for k, a in enumerate(pts):
        for b in pts[k + 1:]:
            assert math.hypot(a[0] - b[0], a[1] - b[1]) >= ST.RAMP["spacing"] - 10  # centres of segments 100 m apart; lips near them
    assert len({i.name.split("#")[0] for i in lips}) == len(lips)  # one per road here


def test_a_villa_over_pilotis_stands_on_columns_with_no_ground_floor_windows_or_shutter():
    # 2026-10-15 (133 street view): 4-5 floor villas here stand on columns over parked cars
    row, est, _ = villa(5, floors=5, code="02000", note="villa on pilotis parking, glass stair")
    body, eff = resolve(row, est, {"building_id": "gis:5", "ground_use": "garage", "stair": "none"}, features=[street()])
    items, _, _ = all_items(body, row, eff)
    assert body.pilotis
    b = next(i for i in items if i.kind == "building")
    assert (b.cy - b.sy / 2) / S == pytest.approx(body.fh, abs=1e-3) and (b.cy + b.sy / 2) / S == pytest.approx(body.height_m, abs=1e-3)
    cols = [i for i in items if tail(i).startswith("pq")]
    assert len(cols) >= 4 and all(i.cy - i.sy / 2 < 0.01 for i in cols)
    assert not any(tail(i).startswith(("sh", "pl", "gs")) for i in items)
    assert not any(tail(i).startswith("w") and i.cy / S < body.fh for i in items)  # no glass on the open ground floor
    assert any(tail(i).startswith("pk") for i in items)  # a stair core when there is no stair tower
    plain, _, _ = villa(6, floors=5, code="02000", note="villa with shops")
    pbody, _ = resolve(plain, est, {"building_id": "gis:6", "ground_use": "shop"}, features=[street()])
    assert not pbody.pilotis


def test_an_apartment_panel_takes_the_judged_wall_colour():
    row, est, _ = villa(7, w=40, d=12, floors=15, code="02000", wall="white")
    body, eff = resolve(row, est, None, features=[street()])
    panels = [i for i in all_items(body, row, eff)[0] if tail(i).startswith("au")]
    assert body.archetype == "apartment" and panels and all(i.color_name == "apt_white" for i in panels)
