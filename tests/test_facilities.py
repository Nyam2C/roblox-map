"""Detailed facility models (src/facilities.py)."""
import dataclasses

import facilities as FA
import layout_details as LD
from test_layout_u5 import FRAME, villa, resolve, street


def body(floors=5):
    row, est, _ = villa(w=40.0, d=16.0, floors=floors, wall="light_gray", code="10000", name="중흥초등학교")
    b, _ = resolve(row, est, features=[street()])
    return dataclasses.replace(b, is_body=True)


SPEC = {"wall": {"material": "Brick", "rgb": [176, 84, 70]}, "windows": {"type": "grid", "w_m": 1.6, "h_m": 1.3, "pitch_m": 3.0},
        "bands": {"rgb": [120, 170, 110]}, "accents": [{"kind": "glass_strip", "face": "street", "width_m": 2.5, "from_floor": 1, "to_floor": 5}],
        "entrance": {"face": "street", "width_m": 4.0, "canopy": True, "steps": True}, "sign": {"text": "중흥초등학교", "floor": 4},
        "roof": {"features": ["stair_box", "solar"]}}


def test_a_facility_is_its_wall_mass_with_windows_bands_accents_a_named_sign_and_a_roof():
    b = body()
    items = FA.Maker(FRAME, b, SPEC, main=True).make()
    tails = [i.name.split("#", 1)[1].split("-")[0] for i in items]
    assert tails.count("m") == len(b.boxes) and tails.count("bd") == 4 * len(b.boxes)
    assert {"w", "wf", "ac", "dr", "cn", "stp", "sg", "tp", "pp", "sb", "sl"} <= set(tails)
    sign = [i for i in items if i.text]
    assert len(sign) == 1 and sign[0].text == "중흥초등학교" and sign[0].kind == "sign"
    assert all(i.owner == b.building_id for i in items)
    assert len(items) < 1500


def test_front_follows_the_compass_side_of_the_photos_and_a_brand_sign_is_refused():
    b = body()
    for side in "NESW":
        fb = FA.Maker(FRAME, b, {**SPEC, "front": side}, main=True)._fronted()
        f = FA.LD.face_of(fb.boxes[fb.front], fb.facing.side)
        e0, n0 = FA.LD._world(fb.boxes[fb.front], 0, 0)
        e1, n1 = FA.LD._world(fb.boxes[fb.front], *f.n)
        want = FA.Maker.COMPASS[side]
        assert (e1 - e0) * want[0] + (n1 - n0) * want[1] > 0.7
    try:
        FA.Maker(FRAME, b, {**SPEC, "sign": {"text": "<script>"}}, main=True).make()
        raise AssertionError("bad sign text accepted")
    except ValueError:
        pass


def test_a_rooftop_court_is_turf_lines_and_a_net_inside_the_roof():
    b = body()
    items = FA.Maker(FRAME, b, {**SPEC, "roof": {"features": ["court"], "court": {"w_m": 99, "d_m": 12}}}, main=True).make()
    tails = [i.name.split("#", 1)[1].split("-")[0] for i in items]
    assert tails.count("ct") == 1 and tails.count("cl") == 5 and tails.count("cf") == 4
    turf = next(i for i in items if "#ct-" in i.name)
    assert max(turf.sx, turf.sz) <= max(b.boxes[b.front].width_m, b.boxes[b.front].depth_m) * FRAME.studs_per_m


def test_a_stripe_on_floor_n_stays_on_the_wall():
    b = body(floors=5)
    items = FA.Maker(FRAME, b, {**SPEC, "accents": [{"kind": "stripe", "face": "all", "from_floor": 5, "to_floor": 5}]}, main=True).make()
    stripes = [i for i in items if "#sp-" in i.name]
    assert stripes and all(i.cy + i.sy / 2 <= b.height_m * FRAME.studs_per_m + 0.01 for i in stripes)


def test_a_skin_panel_sits_under_the_windows():
    b = body()
    acc = {"kind": "panel", "face": "street", "width_m": 20.0, "from_floor": 1, "to_floor": 4, "material": "Plaster", "rgb": [235, 200, 90]}
    raised = FA.Maker(FRAME, b, {**SPEC, "accents": [acc]}, main=True).make()
    flush = FA.Maker(FRAME, b, {**SPEC, "accents": [{**acc, "skin": True}]}, main=True).make()
    thick = lambda items: [min(i.sx, i.sz) for i in items if "#ac-" in i.name]
    assert max(thick(flush)) < max(thick(raised))


def test_a_bell_tower_stands_from_the_ground_with_a_cross_on_top():
    b = body()
    items = FA.Maker(FRAME, b, {**SPEC, "accents": [{"kind": "tower", "face": "roof", "at": -0.45, "size_m": 5.0, "height_m": 26.0}]},
                     main=True).make()
    tw = [i for i in items if "#tw-" in i.name]
    assert len(tw) == 1 and abs(tw[0].sy - 26.0 * FRAME.studs_per_m) < 0.01 and any("#xv-" in i.name for i in items)


def test_a_long_face_with_a_small_annex_in_front_of_its_middle_still_gets_windows():
    from layout import Box
    b = body()
    main = b.boxes[0]
    f = LD.face_of(main, "f")
    e, n = LD._world(main, f.c[0] + f.n[0] * 2.0, f.c[1] + f.n[1] * 2.0)
    annex = Box(e, n, 8.0, 4.0, main.yaw_deg, 1.0)  # small box in front of the middle of the long face
    b2 = dataclasses.replace(b, boxes=(main, annex), occluded=(frozenset({"f"}), frozenset({"b"})))
    assert not FA.Maker.hidden(b2, 0, "f")
    assert FA.Maker.hidden(b2, 1, "b")  # the annex's face against the main box is mostly inside it
