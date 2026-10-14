"""Detailed facility models (src/facilities.py)."""
import dataclasses

import facilities as FA
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
