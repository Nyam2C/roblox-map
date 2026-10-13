"""U7 F anchors: P7-10 the same outline gives the same anchor whatever the box split; the prelude's box picking."""
from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

import anchors
import judgement as J
import layout
import layout_details as LD
from test_layout_u5 import CFG, FRAME, l_shape, villa, CENTER

RECT = ("x", "z", "yaw", "w", "d")


def anchor(row, est, detail=None):
    return anchors.anchor_of(row, J.effective_building(row, est, None, CFG), detail, est.get("note"), FRAME, CFG)


def test_p7_10_the_anchor_rectangle_does_not_follow_the_box_split(monkeypatch):
    row, est, _ = villa()
    row = {**row, "outline": [list(p) for p in l_shape(CENTER)]}
    split = anchor(row, est)
    assert len(split["boxes"]) == 2
    one = layout.outline_to_box([(p[0], p[1]) for p in row["outline"]], FRAME)
    monkeypatch.setattr(LD, "outline_to_boxes", lambda outline, frame, cfg, archetype: [one])
    whole = anchor(row, est)
    assert len(whole["boxes"]) == 1
    assert {k: split[k] for k in RECT} == {k: whole[k] for k in RECT}
    assert split["top"] == whole["top"]


@settings(max_examples=40)
@given(st.floats(-60, 60), st.floats(-60, 60), st.booleans())
def test_p7_10_the_anchor_ignores_vertex_order_and_start(dx, dy, reverse):
    row, est, _ = villa(center=layout.from_studs(FRAME, dx * 3.6, dy * 3.6))
    outline = row["outline"][:-1] if row["outline"][0] == row["outline"][-1] else row["outline"]
    turned = outline[2:] + outline[:2]
    if reverse:
        turned = turned[::-1]
    a, b = anchor(row, est), anchor({**row, "outline": turned}, est)
    assert {k: a[k] for k in RECT} == {k: b[k] for k in RECT}


def test_a_flat_roof_anchor_puts_the_walkable_roof_on_the_cap_and_a_gable_on_the_wall_top():
    flat, gable = anchor(*villa(roof="flat")[:2]), anchor(*villa(roof="gable")[:2])
    assert flat["flat"] and flat["roof"] > flat["top"]
    assert not gable["flat"] and gable["roof"] == gable["top"]


def test_the_prelude_carries_the_anchors_as_json():
    a = {"gis:1": anchor(*villa()[:2])}
    text = anchors.prelude("r", a)
    body = text.split("[==[", 1)[1].split("]==]", 1)[0]
    assert json.loads(body) == a
    assert "function A.box(" in text and "]==]" not in json.dumps(a)
