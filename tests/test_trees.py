"""Trees read off the satellite photo (trees.py) and made by layout_details.tree_items / build_luau (BR-11.4a)."""
from __future__ import annotations

import math

import json

import numpy as np
import pytest

import kits
import layout
import streets as ST
import trees as T
import build_luau as B
from test_build_luau import CELL, CFG, building, street

M = 0.474  # metres per pixel after the 2x reduction


def photo(h=200, w=200):
    img = np.full((h, w, 3), (120, 120, 118), dtype=np.uint8)  # grey ground
    img[20:60, 20:180] = (38, 74, 46)                          # a dark green crown strip, 40 x 160 px
    img[100:140, 20:80] = (111, 157, 111)                      # a bright green roof or lawn: not crown
    img[100:140, 120:180] = (90, 105, 79)                      # greenish gravel: not crown
    return img


def test_the_mask_takes_the_dark_green_strip_only():
    m = T.canopy_mask(photo())
    assert m[30:50, 40:160].all()
    assert not m[100:140, 20:80].any() and not m[100:140, 120:180].any() and not m[70:90, :].any()


def test_crowns_are_packed_along_the_strip_where_a_trunk_may_stand_and_nowhere_else():
    canopy = T.canopy_mask(photo())
    allowed = np.ones_like(canopy)
    found = T.pack_crowns(canopy, allowed, M)
    assert len(found) >= 4 and all(T.R_MIN <= r <= T.R_MAX for _, _, r in found)
    assert all(20 <= i <= 60 and 20 <= j <= 180 for i, j, _ in found)
    assert found == T.pack_crowns(canopy, allowed, M)  # the same photo gives the same trees
    allowed[:, :100] = False  # no trunk on the west half (a road)
    assert all(j >= 100 for _, j, _ in T.pack_crowns(canopy, allowed, M))
    assert T.pack_crowns(canopy, np.zeros_like(canopy), M) == []


def test_a_tree_is_a_trunk_and_a_crown_mesh_scaled_by_the_crown_diameter_and_repeatable():
    frame = layout.Frame.from_cfg(CFG)
    items = ST.tree_items(frame, [[-100.0, 50.0, 7.2], [-300.0, 80.0, 3.0], [10.0, 10.0, 20.0]])
    assert len(items) == 6 and items == ST.tree_items(frame, [[-100.0, 50.0, 7.2], [-300.0, 80.0, 3.0], [10.0, 10.0, 20.0]])
    assert [i.name for i in items[:2]] == ["sat#0#tree", "sat#0#crown"]
    trunk, crown = items[0], items[1]
    assert trunk.shape == "Cylinder" and trunk.cx == pytest.approx(-100.0, abs=0.01) and trunk.cz == pytest.approx(50.0, abs=0.01)
    assert trunk.cy - trunk.sx / 2 == pytest.approx(0.0, abs=0.01)  # a standing cylinder stands on the ground (its length is sx)
    assert crown.cy - crown.sy / 2 < trunk.cy + trunk.sx / 2  # the crown sits on the trunk, no gap
    assert crown.kit in kits.MESH_IDS and crown.collide is False and crown.material == "LeafyGrass"
    assert math.hypot(crown.cx - trunk.cx, crown.cz - trunk.cz) < crown.sx / 2  # the trunk stands under the crown
    # the 3 m and the 20 m crowns are limited to the scale range 0.55 .. 1.1
    small, big = items[3], items[5]
    assert small.sy < crown.sy < big.sy
    if small.kit == big.kit:
        assert big.sy / small.sy == pytest.approx(1.1 / 0.55, rel=0.01)
    many = ST.tree_items(frame, [[i * 10.0, 0.0, 7.0] for i in range(40)])
    assert len({i.color_name for i in many if "#crown" in i.name}) > 1 and len({i.kit for i in many if i.kit}) == len(kits.MESH_IDS)


def test_a_file_of_satellite_trees_replaces_the_rule_based_street_trees():
    feats = [street("way:1", "residential")]
    plain = B.plan_cell(CELL, [building(0)], feats, CFG)
    sat = B.plan_cell(CELL, [building(0)], feats, CFG, sat_trees=[[-500.0, -80.0, 6.0], [-520.0, -90.0, 8.0]])
    count = lambda plan, word: sum(1 for i in plan.items if word in i.name)
    assert count(plain, "#tree") > 0 and count(plain, "sat#") == 0
    assert count(sat, "#tree") == 2 and count(sat, "way:1#") > 0 and count(sat, "sat#") == 4  # street tree gone, other street props stay
    assert count(sat, "#crown") == 2
    empty = B.plan_cell(CELL, [building(0)], feats, CFG, sat_trees=[])
    assert count(empty, "#tree") == 0  # a file with no trees means no trees, not the rule


def test_load_trees_reads_the_rows_and_a_missing_file_means_the_rule_stays(tmp_path):
    assert ST.load_trees(tmp_path / "none.json") is None
    path = T.write_trees("8930e0af13bffff", [[1.0, 2.0, 6.5], [3.0, 4.0, 5.0]], tmp_path / "cells" / "x" / "trees.json")
    assert ST.load_trees(path) == [[1.0, 2.0, 6.5], [3.0, 4.0, 5.0]]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"trees": [[1, 2, 3], [1, 2], [1, 2, 4.0]]}))
    assert ST.load_trees(bad) == [[1.0, 2.0, 3.0], [1.0, 2.0, 4.0]]


def test_georef_round_trip():
    g = T.Georef(446774, 203141)
    lat, lon = 37.50438, 126.77791
    px, py = g.to_px(lat, lon)
    assert g.to_latlon(px, py) == pytest.approx((lat, lon), abs=1e-9)
    assert g.m_per_px(lat) == pytest.approx(0.2369, abs=1e-3)


def test_an_underground_car_park_outline_does_not_hide_the_trees_of_the_plaza_over_it():
    # 미관광장 (cell 10f, 2026-10-14): the car park under the plaza (1 floor up, 4 down) masked every crown of the plaza
    import h3
    cell = "8930e0af10fffff"
    lat, lon = h3.cell_to_latlng(cell)
    g0 = T.Georef(0, 0)
    px, py = g0.to_px(lat, lon)
    g = T.Georef(int(px // 256) - 1, int(py // 256) - 1)  # a 3 x 3 tile photo around the cell centre
    img = np.full((768, 768, 3), (120, 120, 118), dtype=np.uint8)
    cx, cy = g.to_px(lat, lon)
    img[int(cy) - 40:int(cy) + 40, int(cx) - 60:int(cx) + 60] = (38, 74, 46)
    box = [g.to_latlon(cx + dx, cy + dy) for dx, dy in ((-70, -50), (70, -50), (70, 50), (-70, 50))]
    over = {"outline": box, "floors_above": 1, "floors_below": 4}
    assert T.find_trees(img, g, cell, [over], [], CFG)
    assert not T.find_trees(img, g, cell, [{**over, "floors_below": 1}], [], CFG)
