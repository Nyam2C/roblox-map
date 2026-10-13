"""U7 J school ground kit: the ground found in a drawn photo, the parts it makes, the fields.json rows the build takes."""
from __future__ import annotations

import json
import math

import h3
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image, ImageDraw

import common
import fields
import layout
from trees import Georef

CFG = dict(common.DEFAULTS)
FRAME = layout.Frame.from_cfg(CFG)
S = FRAME.studs_per_m
ORIGIN = (FRAME.origin_lat, FRAME.origin_lon)
SAND, TURF, GRASS, ROAD = (215, 200, 165), (110, 122, 90), (60, 105, 50), (95, 95, 98)


def geo_and_photo(size=900):
    n = 2 ** 19
    tx = (ORIGIN[1] + 180) / 360 * n
    ty = (1 - math.asinh(math.tan(math.radians(ORIGIN[0]))) / math.pi) / 2 * n
    geo = Georef(int(tx) - 1, int(ty) - 1)  # the origin sits about 256 px in
    img = Image.new("RGB", (size, size), ROAD)
    return geo, img


def px(geo, east, north):
    return geo.to_px(*layout.from_studs(FRAME, east * S, -north * S))


def quad(geo, cx, cy, w, d, yaw):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return [px(geo, cx + u * c - v * s, cy + u * s + v * c) for u, v in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))]


def school_of(geo, cx, cy, w, d, yaw):
    return [layout.from_studs(FRAME, e * S, -n * S) for e, n in
            [(cx + u * math.cos(math.radians(yaw)) - v * math.sin(math.radians(yaw)), cy + u * math.sin(math.radians(yaw)) + v * math.cos(math.radians(yaw)))
             for u, v in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))]]


def draw(geo, img, cx, cy, w, d, yaw, color, lines=True):
    dr = ImageDraw.Draw(img)
    dr.polygon(quad(geo, cx, cy, w + 30, d + 30, yaw), fill=GRASS)
    dr.polygon(quad(geo, cx, cy, w, d, yaw), fill=color)
    if lines:  # white pitch lines the closing must swallow
        for v in (-d / 2 + 3, d / 2 - 3):
            dr.line([px(geo, cx - (w / 2 - 3) * math.cos(math.radians(yaw)) - v * math.sin(math.radians(yaw)),
                         cy - (w / 2 - 3) * math.sin(math.radians(yaw)) + v * math.cos(math.radians(yaw))),
                     px(geo, cx + (w / 2 - 3) * math.cos(math.radians(yaw)) - v * math.sin(math.radians(yaw)),
                         cy + (w / 2 - 3) * math.sin(math.radians(yaw)) + v * math.cos(math.radians(yaw)))], fill=(245, 245, 245), width=1)


@settings(max_examples=8, deadline=None)
@given(st.floats(30, 90), st.floats(20, 50), st.floats(0, 179), st.sampled_from(["sand", "turf"]))
def test_the_ground_of_a_drawn_photo_is_found_within_a_metre_and_a_degree(w, d, yaw, surface):
    d = min(d, w * 0.9)
    geo, img = geo_and_photo()
    cx, cy = 5.0, -8.0
    draw(geo, img, cx, cy, w, d, yaw, SAND if surface == "sand" else TURF)
    g = fields.find_ground(np.asarray(img), geo, school_of(geo, cx, cy, w + 24, d + 24, yaw), [], [], FRAME)
    assert g is not None and g["surface"] == surface
    assert math.hypot(g["x"] / S - cx, -g["z"] / S - cy) < 1.0
    assert abs(g["w"] / S - w) < 1.5 and abs(g["d"] / S - d) < 1.5
    diff = (g["yaw"] - yaw + 90) % 180 - 90
    assert abs(diff) < 1.0 or (w - d < 2 and abs(abs(diff) - 90) < 1.0)


def test_a_thin_strip_round_a_court_does_not_widen_the_ground_and_the_grid_snaps_the_yaw():
    geo, img = geo_and_photo()
    draw(geo, img, 0, 0, 60, 45, 12.0, SAND)
    dr = ImageDraw.Draw(img)
    dr.polygon(quad(geo, -42, 0, 20, 30, 12.0), fill=(90, 105, 130))           # a blue court west of it
    dr.polygon(quad(geo, -42, 16.5, 24, 2.0, 12.0), fill=SAND)                 # a 2 m sand strip along its north side
    g = fields.find_ground(np.asarray(img), geo, school_of(geo, -12, 0, 110, 70, 12.0), [], [14.5], FRAME)
    assert abs(g["w"] / S - 60) < 2.0
    assert g["yaw"] == 14.5  # within 6 degrees of the school's grid


def test_roofs_are_not_ground_and_a_small_patch_is_none():
    geo, img = geo_and_photo()
    draw(geo, img, 0, 0, 50, 40, 0.0, SAND, lines=False)
    roof = school_of(geo, 0, 0, 52, 42, 0.0)
    assert fields.find_ground(np.asarray(img), geo, school_of(geo, 0, 0, 70, 60, 0.0), [roof], [], FRAME) is None
    geo, img = geo_and_photo()
    draw(geo, img, 0, 0, 15, 12, 0.0, SAND, lines=False)
    assert fields.find_ground(np.asarray(img), geo, school_of(geo, 0, 0, 40, 40, 0.0), [], [], FRAME) is None


def ground(w=120.0, d=60.0, yaw=30.0, surface="sand"):
    return {"osm": "way:1", "made_by": "kit", "surface": surface, "x": 10.0, "z": -20.0, "yaw": yaw, "w": w * S, "d": d * S, "fit": 0.9}


def local(item, g):
    c, s = math.cos(math.radians(g["yaw"])), math.sin(math.radians(g["yaw"]))
    dx, dz = item.cx - g["x"], item.cz - g["z"]
    return dx * c - dz * s, dx * s + dz * c


@pytest.mark.parametrize("w, d, goals", [(120.0, 60.0, 6), (30.0, 18.0, 6), (18.0, 12.0, 0)])
def test_the_kit_parts_stay_on_the_slab_and_goals_stand_on_the_end_lines(w, d, goals):
    g = ground(w, d)
    items = fields.field_items(g, FRAME)
    slab = items[0]
    assert slab.name.endswith("#ground") and slab.collides and slab.material == "Sand"
    assert slab.cy + slab.sy / 2 == pytest.approx(fields.D["top"])
    for i in items[1:]:
        u, v = local(i, g)
        assert abs(u) <= g["w"] / 2 + 1e-6 and abs(v) <= g["d"] / 2 + 1e-6
        assert i.cy - i.sy / 2 >= fields.D["top"] - 1e-6  # nothing sinks into the slab
    posts = [i for i in items if "#g" in i.name and not i.name.endswith("#ground")]
    assert len(posts) == goals
    for p in posts:
        assert abs(abs(local(p, g)[0]) - (g["w"] / 2 - fields.D["line_in_m"] * S)) < 1e-3
    assert [i.name for i in fields.field_items(g, FRAME)] == [i.name for i in items]


def test_turf_is_grass_and_the_circle_closes():
    items = fields.field_items(ground(surface="turf"), FRAME)
    assert items[0].material == "Grass"
    circle = [i for i in items if "#c" in i.name]
    assert len(circle) == fields.D["circle_pieces"]
    assert sum(i.sz for i in circle) >= 2 * math.pi * min(fields.D["circle_m"] * S, 0.3 * (60 - 2 * fields.D["line_in_m"]) * S)


def test_only_kit_rows_are_built_and_a_bad_row_refuses(tmp_path):
    path = tmp_path / "fields.json"
    rows = [ground(), {**ground(), "osm": "way:2", "made_by": "manual"}]
    path.write_text(json.dumps({"fields": rows}), encoding="utf-8")
    assert [r["osm"] for r in fields.load_fields(path)] == ["way:1"]
    path.write_text(json.dumps({"fields": [{**ground(), "osm": 'way:1"); print("x'}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        fields.load_fields(path)
    assert fields.load_fields(tmp_path / "none.json") == []
