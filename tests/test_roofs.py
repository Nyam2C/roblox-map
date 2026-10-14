"""Roof tops read off the satellite photo: the nearest look, the shrunk footprint, the flat-roof cap colour, the file the build takes."""
from __future__ import annotations

import json
import math

import pytest
from PIL import Image, ImageDraw

import build_luau as B
import details_rules as R
import layout
import roofs
from test_fields import FRAME, S, geo_and_photo, quad
from test_layout_u5 import CELL, CFG, resolve, villa
import layout_details as LD


def test_every_look_has_a_studio_colour_and_its_own_photo_colour_is_nearest_to_it():
    for k, rgb in roofs.SAT_LOOKS.items():
        assert k in R.PALETTE and roofs.nearest_look(rgb) == k


def building_on(geo, img, cx, cy, w, d, color, floors=3, bid="gis:1"):
    ImageDraw.Draw(img).polygon(quad(geo, cx, cy, w, d, 0.0), fill=color)
    outline = [layout.from_studs(FRAME, (cx + u) * S, -(cy + v) * S) for u, v in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))]
    return {"building_id": bid, "outline": [list(p) for p in outline], "centroid": list(layout.from_studs(FRAME, cx * S, -cy * S)), "floors_above": floors}


def test_a_drawn_white_roof_reads_white_a_tall_one_and_a_tiny_one_are_left_to_the_rule():
    geo, img = geo_and_photo()
    a = building_on(geo, img, 0, 0, 20, 14, (212, 212, 208), bid="gis:1")
    b = building_on(geo, img, 40, 0, 20, 14, (212, 212, 208), floors=12, bid="gis:2")
    c = building_on(geo, img, -40, 0, 3.2, 3.2, (212, 212, 208), bid="gis:3")
    looks = roofs.roof_looks(img, geo, [a, b, c])
    assert looks == {"gis:1": "rtop_white"}


def test_the_cap_of_a_flat_roof_takes_the_roof_top_and_a_pitched_roof_ignores_it():
    row, est, _ = villa(wall="red_brick", roof="flat")
    body, eff = resolve(row, est)
    plain = [i for i in LD.body_items(body, 0, FRAME, CFG, []) if "#cap" in i.name]
    import dataclasses
    topped = dataclasses.replace(body, details={**body.details, "roof_top": "rtop_white"})
    caps = [i for i in LD.body_items(topped, 0, FRAME, CFG, []) if "#cap" in i.name]
    assert plain and caps and all(i.color == R.PALETTE["rtop_white"] and i.color_name == "rtop_white" for i in caps)
    assert all(i.color != R.PALETTE["rtop_white"] for i in plain)


def test_the_build_uses_roofs_json_and_refuses_an_unknown_look(tmp_path):
    row, est, _ = villa(roof="flat")
    plan = B.plan_cell(CELL, [row], [], CFG, {"gis:1": est}, roof_tops={"gis:1": "rtop_green"})
    assert any("#cap" in i.name and i.color_name == "rtop_green" for i in plan.items)
    path = tmp_path / "roofs.json"
    path.write_text(json.dumps({"roofs": {"gis:1": "purple"}}), encoding="utf-8")
    with pytest.raises(ValueError):
        roofs.load_roofs(path)
    assert roofs.load_roofs(tmp_path / "none.json") == {}
