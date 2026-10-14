"""Overpasses (src/bridges.py) and their lift onto the deck (terrain.lift)."""
import pytest

import bridges as B
import layout
import terrain as T
from test_layout_u5 import CFG, FRAME, CELL, CENTER, offset


def road(fid, pts, **tags):
    return {"feature_id": fid, "kind": "road", "highway_class": "tertiary", "tags": {"lanes": "4", **tags},
            "geometry": [list(offset(CENTER, e, n)) for e, n in pts]}


def studs(e, n):  # metres east and north of CENTER -> stud (x, z)
    return layout.to_studs(FRAME, *offset(CENTER, e, n))


def test_a_bridge_chain_ramps_up_from_an_at_grade_end_and_runs_on_at_full_height_off_the_map():
    feats = [road("way:1", [(-400, 0), (-100, 0)], bridge="yes", layer="1"), road("way:2", [(-100, 0), (200, 0)], bridge="viaduct", layer="1"),
             road("way:3", [(-500, 0), (-400, 0)]), road("way:4", [(0, -50), (0, 50)], bridge="yes", layer="-1")]
    d = B.Decks(feats, FRAME, CFG)
    assert d.fids == {"way:1", "way:2"}  # layer -1 is not an overpass
    s = FRAME.studs_per_m
    assert d.offset_studs("way:1", *studs(-400, 0)) == pytest.approx(0.0, abs=0.05)  # meets the at-grade way 3
    assert d.offset_studs("way:1", *studs(-400 + B.RAMP_M / 2, 0)) == pytest.approx(B.DECK_M * s / 2, rel=0.02)
    assert d.offset_studs("way:2", *studs(0, 0)) == pytest.approx(B.DECK_M * s)
    assert d.offset_studs("way:2", *studs(200, 0)) == pytest.approx(B.DECK_M * s)  # the far end meets nothing: off the map
    assert d.offset_studs("way:3", *studs(-450, 0)) == 0.0
    assert d.over(*studs(0, 3)) > 0 and d.over(*studs(0, 30)) == 0.0


def test_a_bridge_way_rises_onto_its_deck_drops_its_trees_and_the_rest_stays_on_the_ground():
    feats = [road("way:1", [(-300, 0), (300, 0)], bridge="yes", layer="1")]
    d = B.Decks(feats, FRAME, CFG)
    x, z = studs(10, 0)
    deck_road = layout._item("road", "way:1#0", "way:1", 0, (x, 0.1, z), (40.0, 0.2, 40.0), 0.0)
    tree = layout._item("prop", "way:1#0#crownL3a", "way:1", 1, (x, 10.0, z + 30), (8.0, 8.0, 8.0), 0.0, shape="Ball")
    lamp = layout._item("prop", "way:1#0#lamp3", "way:1", 2, (x, 16.0, z + 30), (32.0, 1.0, 1.0), 0.0, shape="Cylinder")
    other = layout._item("road", "way:9#0", "way:9", 0, (x, 0.1, z), (40.0, 0.2, 40.0), 0.0)
    out = {i.name: i for i in T.lift([deck_road, tree, lamp, other], None, d)}
    up = B.DECK_M * FRAME.studs_per_m
    assert out["way:1#0"].cy == pytest.approx(0.1 + up, abs=0.01)
    assert out["way:1#0#lamp3"].cy == pytest.approx(16.0 + up, abs=0.01)
    assert "way:1#0#crownL3a" not in out
    assert out["way:9#0"].cy == pytest.approx(0.1)
    piers = B.pier_items(d, feats, None, CELL, CFG["h3_res"], CFG)
    assert piers and all(p.cy - p.sy / 2 < 0 and p.cy + p.sy / 2 == pytest.approx((B.DECK_M - B.GIRDER_M) * FRAME.studs_per_m + 0.1, abs=0.01)
                         for p in piers)
